"""Regression tests for read-only destinations (Windows FILE_ATTRIBUTE_READONLY).

Google Drive for desktop marks mirrored directories read-only and shutil.copy2
propagates a read-only source file's attribute onto the destination copy. Windows
then refuses to delete a read-only file, refuses to remove a read-only directory
and refuses to overwrite a read-only target with os.replace -> PermissionError
[WinError 5] Access is denied.

The engine must clear the read-only attribute ONLY on the exact path it is about
to mutate, immediately before that mutation, with a bounded retry. It must never
unlock files it does not mutate, it must never make a mirrored copy writable, it
must never modify the source, and it must never force-delete on a genuine
non-permission failure.

Product policy (README-DRIVE-TEMP-FIX.txt lines 36-38): "If Windows still reports
WinError 5/145 for any OTHER obsolete directory, RepoSync must still stop; do
not manually delete files to force a pass. It may be a lock/race on genuine stale
content; send exact path and error for review." Only the read-only ATTRIBUTE may
be worked around - a genuine lock (another process holding an open handle) and a
genuinely non-empty directory must still abort the sync with an error that names
the exact path.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
import reposync as rs


def set_readonly(path):
    """Mark a file or directory read-only using the native mechanism."""
    if os.name == "nt":
        os.chmod(str(path), stat.S_IREAD)
    else:
        os.chmod(str(path), 0o444)


def clear_readonly(path):
    """Restore write access so the test itself can edit or remove the entry."""
    if os.name == "nt":
        os.chmod(str(path), stat.S_IWRITE)
    else:
        os.chmod(str(path), 0o644)


def is_readonly(path):
    """True when the entry carries the read-only attribute (or has no write bit)."""
    st = os.stat(str(path))
    if os.name == "nt":
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
    return not (st.st_mode & stat.S_IWUSR)


def mark_readonly_windows_only(path):
    """Apply the Windows read-only attribute, and only there.

    POSIX has no read-only attribute: a mode without the write bit blocks the
    removal of a directory's children, which is a different failure mode than
    the Windows attribute this suite is about. Cross-platform tests therefore
    only mark entries read-only on Windows.
    """
    if os.name == "nt":
        set_readonly(path)


def make_oserror(errno_value, message="simulated error"):
    """Build an OSError that carries an explicit errno on any platform.

    Some builds refuse keyword arguments on OSError, so the positional form is
    used as a fallback. The caller checks the resulting errno.
    """
    try:
        return OSError(errno=errno_value, strerror=message)
    except TypeError:
        return OSError(errno_value, message)


def make_win_error(winerror, message="simulated Windows error"):
    """Build an OSError that carries a Windows error code (errno, strerror, filename, winerror).

    This is the four argument form Windows itself uses; it is the only way to
    attach a winerror to an OSError instance.
    """
    return OSError(0, message, None, winerror)


class ReadOnlyDestinationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.root_path = Path(self.root.name)
        self.source = self.root_path / "source"
        self.dest = self.root_path / "dest"
        self.source.mkdir()
        self.profile = {"name": "readonly", "source": str(self.source),
                        "destination": str(self.dest), "preset": "review",
                        "include": [], "exclude": []}
        # Isolate the profile store: the real %LOCALAPPDATA%\RepoSync is never
        # read or written by these tests.
        self.home = self.root_path / "home"
        self._old_home = os.environ.get("REPOSYNC_HOME")
        os.environ["REPOSYNC_HOME"] = str(self.home)
        self.addCleanup(self.restore_home)
        # A read-only attribute blocks the temporary directory's own cleanup on
        # Windows, so every entry is made writable again before the tree goes.
        # Registered last, so it runs before the directory removal.
        self.addCleanup(self.unlock_temp_tree)

    def restore_home(self):
        if self._old_home is None:
            os.environ.pop("REPOSYNC_HOME", None)
        else:
            os.environ["REPOSYNC_HOME"] = self._old_home

    def unlock_temp_tree(self):
        """Remove the read-only attribute from every entry of the temp tree."""
        for path in sorted(self.root_path.rglob("*"), reverse=True):
            try:
                if os.name == "nt":
                    os.chmod(str(path), stat.S_IWRITE)
                elif path.is_dir():
                    os.chmod(str(path), 0o755)
                else:
                    os.chmod(str(path), 0o644)
            except OSError:
                pass

    # -- helpers -------------------------------------------------------
    def write_source(self, rel, value="data"):
        path = self.source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def write_dest(self, rel, value="data"):
        path = self.dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def sync_once(self):
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        return out

    def snapshot(self, root):
        """Recursive listing of a tree: relative path -> type/size/mtime_ns/read-only/digest.

        The read-only bit and the content digest belong into the snapshot:
        clearing a file's read-only attribute changes ctime but not mtime, so a
        snapshot that only records mtime would happily accept a source tree that
        was silently unlocked, and it would not notice a rewritten file either.
        """
        entries = {}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root).as_posix()
            st = path.stat()
            is_dir = path.is_dir()
            if os.name == "nt":
                readonly = bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_READONLY)
            else:
                readonly = bool(st.st_mode & 0o222)
            entry = {"type": "dir" if is_dir else "file",
                     "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                     "readonly": readonly}
            if not is_dir:
                entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            entries[rel] = entry
        return entries

    # -- 1. stale read-only FILE in the destination is deleted ---------
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute blocks deletion of files")
    def test_stale_readonly_file_in_destination_is_deleted(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        stale = self.write_dest("stale-ro.txt", "stale")
        set_readonly(stale)
        self.assertTrue(is_readonly(stale))
        self.assertIn("stale-ro.txt", rs.plan(self.profile)["delete_files"])
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertFalse(stale.exists(), "stale read-only file must be deleted")
        self.assertTrue((self.dest / "keep.txt").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 2. stale read-only DIRECTORY in the destination is removed -----
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute blocks removal of directories")
    def test_stale_readonly_directory_in_destination_is_removed(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        inner = self.write_dest("stale/inner.txt", "stale")
        set_readonly(self.dest / "stale")
        set_readonly(inner)
        self.assertTrue(is_readonly(self.dest / "stale"))
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertFalse((self.dest / "stale").exists(),
                         "stale read-only directory must be removed")
        self.assertTrue((self.dest / "keep.txt").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 3. read-only bit may sit on the CHILD, not only on the top -----
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute blocks removal of files")
    def test_readonly_directory_with_readonly_child_is_fully_removed(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        # Only the child file carries the read-only bit.
        child_only = self.write_dest("child-ro/inner.txt", "x")
        set_readonly(child_only)
        # A nested tree where every level is read-only.
        leaf = self.write_dest("deep/tree/leaf.txt", "y")
        set_readonly(self.dest / "deep")
        set_readonly(self.dest / "deep/tree")
        set_readonly(leaf)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertFalse((self.dest / "child-ro").exists(),
                         "directory with a read-only child must be removed")
        self.assertFalse((self.dest / "deep").exists(),
                         "nested read-only tree must be removed")
        self.assertTrue((self.dest / "keep.txt").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 4. existing read-only destination file is UPDATED ------------
    @unittest.skipUnless(os.name == "nt",
                         "Windows refuses to overwrite a read-only target")
    def test_existing_readonly_destination_file_is_updated(self):
        self.write_source("doc.txt", "old")
        self.sync_once()
        target = self.dest / "doc.txt"
        set_readonly(target)
        self.assertTrue(is_readonly(target))
        self.write_source("doc.txt", "new content")
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertEqual(target.read_text(encoding="utf-8"), "new content")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 5. attribute fidelity: a read-only source stays read-only -----
    def test_readonly_source_file_copies_as_readonly(self):
        src = self.write_source("locked.txt", "locked")
        set_readonly(src)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        copied = self.dest / "locked.txt"
        self.assertTrue(copied.is_file())
        self.assertTrue(is_readonly(copied),
                        "mirroring must not make a read-only source writable")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 6. a read-only file stays manageable in later syncs -----------
    def test_readonly_source_file_can_still_be_updated_and_deleted(self):
        src = self.write_source("locked.txt", "v1")
        set_readonly(src)
        self.sync_once()
        copied = self.dest / "locked.txt"
        self.assertTrue(is_readonly(copied))
        # The user edits the source; it stays read-only afterwards.
        clear_readonly(src)
        src.write_text("v2 updated", encoding="utf-8")
        set_readonly(src)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertEqual(copied.read_text(encoding="utf-8"), "v2 updated")
        self.assertTrue(is_readonly(copied),
                        "the mirrored copy keeps the source read-only attribute")
        # The user removes the source; the mirror must drop the stale copy.
        clear_readonly(src)
        src.unlink()
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertFalse(copied.exists(),
                         "a stale read-only copy must still be deletable")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 7. no gratuitous unlocking of untouched paths -----------------
    def test_up_to_date_readonly_destination_file_stays_readonly(self):
        self.write_source("same.txt", "same")
        self.sync_once()
        target = self.dest / "same.txt"
        set_readonly(target)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["copied"], 0, "an up-to-date file must not be rewritten")
        self.assertTrue(is_readonly(target),
                        "the fix must only unlock the exact path it mutates")
        self.assertEqual(target.read_text(encoding="utf-8"), "same")

    # -- 8. genuine non-permission failure aborts the sync ------------
    def test_genuine_removal_failure_aborts_with_reposync_error(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        # A directory the plan wants to remove that still holds content the
        # plan never sees (a Drive-managed scratch object): removal fails with
        # a genuine ENOTEMPTY / WinError 145, not a permission problem.
        busy = self.write_dest("stale/.tmp.drivedownload/busy.tmp", "Google Drive owns this")
        with self.assertRaises(rs.RepoSyncError) as ctx:
            rs.sync(self.profile, yes=True)
        self.assertIn("stale", str(ctx.exception))
        self.assertTrue(busy.is_file(), "surviving content must be untouched")
        self.assertEqual(busy.read_text(encoding="utf-8"), "Google Drive owns this")
        self.assertTrue((self.dest / "stale").is_dir(),
                        "the sync must abort, not force-delete the directory")
        self.assertTrue((self.dest / "keep.txt").is_file())

    def test_simulated_removal_failure_aborts_without_force_delete(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        busy = self.write_dest("stale/.tmp.drivedownload/busy.tmp", "busy")

        def refuse(*args, **kwargs):
            raise OSError(errno.ENOTEMPTY, "Directory not empty")

        with patch.object(Path, "rmdir", side_effect=refuse), \
                patch.object(rs.shutil, "rmtree", side_effect=refuse):
            with self.assertRaises(rs.RepoSyncError):
                rs.sync(self.profile, yes=True)
        self.assertTrue(busy.is_file(), "surviving content must be untouched")
        self.assertTrue((self.dest / "stale").is_dir(),
                        "the sync must abort, not force-delete the directory")

    # -- 9. error message quality -------------------------------------
    def test_delete_failure_message_names_path_and_mirror_state(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        self.write_dest("stale/.tmp.drivedownload/busy.tmp", "busy")
        with self.assertRaises(rs.RepoSyncError) as ctx:
            rs.sync(self.profile, yes=True)
        message = str(ctx.exception)
        low = message.lower()
        self.assertIn("stale", message, "the message must name the offending path")
        self.assertNotIn("PermissionError", message)
        self.assertNotIn("Traceback", message)
        self.assertTrue("not fully verified" in low or "not verified" in low, message)
        self.assertIn("preview", low)

    # -- 10. the read-only unlock really works (deterministic) ---------
    # Replaces the former try/except/else test, which also passed when the
    # unlock did nothing at all. The success is now the only possible outcome.
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute blocks deletion of files")
    def test_readonly_stale_destination_file_is_deleted_and_sync_succeeds(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        stale = self.write_dest("stale-ro.txt", "stale")
        set_readonly(stale)
        self.assertTrue(is_readonly(stale))
        self.assertIn("stale-ro.txt", rs.plan(self.profile)["delete_files"])
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertFalse(stale.exists(),
                         "a read-only stale file must be unlocked and deleted")
        self.assertTrue((self.dest / "keep.txt").is_file(),
                        "the mirror must still hold the expected file")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 11. a deletion that fails for another reason is reported ------
    # The read-only unlock is irrelevant here: the directory really holds
    # content (WinError 145 / ENOTEMPTY), so the sync must stop and report.
    def test_delete_dirs_failure_message_pins_readonly_and_concurrent_wording(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        busy = self.write_dest("stale/.tmp.drivedownload/busy.tmp", "busy")
        with self.assertRaises(rs.RepoSyncError) as ctx:
            rs.sync(self.profile, yes=True)
        message = str(ctx.exception)
        low = message.lower()
        self.assertIn("stale", message, "the message must name the offending path")
        self.assertIn("read-only attribute", low,
                      "the message must mention the read-only attribute")
        self.assertIn("concurrent", low,
                      "the message must mention the concurrent-process possibility")
        self.assertTrue("not fully verified" in low or "not verified" in low, message)
        self.assertIn("preview", low)
        self.assertNotIn("PermissionError", message)
        self.assertNotIn("Traceback", message)
        self.assertTrue(busy.is_file(), "surviving content must be untouched")
        self.assertTrue((self.dest / "stale").is_dir(),
                        "the sync must abort, not force-delete the directory")

    # -- 12. a genuine lock is not a read-only problem ------------------
    # The destination file is held open by another handle, so Windows denies
    # the delete with WinError 32 (ERROR_SHARING_VIOLATION). The read-only
    # attribute is irrelevant and the file must not be force-deleted.
    @unittest.skipUnless(os.name == "nt",
                         "Windows denies deletion of a file that another handle has open")
    def test_genuine_locked_destination_file_aborts_sync_and_is_not_deleted(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        locked = self.write_dest("locked.txt", "locked")
        handle = open(str(locked), "rb")  # kept open on purpose
        try:
            with self.assertRaises(rs.RepoSyncError) as ctx:
                rs.sync(self.profile, yes=True)
        finally:
            handle.close()
        message = str(ctx.exception)
        low = message.lower()
        self.assertIn("locked.txt", message,
                      "the message must name the offending path")
        self.assertTrue("not fully verified" in low or "not verified" in low, message)
        self.assertNotIn("Traceback", message)
        self.assertTrue(locked.exists(),
                        "a locked file must not be force-deleted")
        self.assertEqual(locked.read_text(encoding="utf-8"), "locked")
        self.assertTrue((self.dest / "keep.txt").is_file())

    # -- 13. DriveFS re-applies the read-only attribute asynchronously --
    # The attribute is cleared just in time, but DriveFS puts it back before
    # the retry. The sync must give up after the bounded retries and report
    # the exact path instead of looping forever or deleting the file.
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute blocks deletion of files")
    def test_drivefs_readonly_reapplied_between_retries_aborts_sync(self):
        self.write_source("keep.txt", "keep")
        self.sync_once()
        stale = self.write_dest("stale-ro.txt", "stale")
        set_readonly(stale)
        # The delete is the only thing this sync does: no copy may run while
        # the patched helper is installed.
        self.assertEqual(rs.plan(self.profile)["copy"], [],
                         "this test must isolate the delete path")
        real_clear = rs.clear_readonly

        def clear_then_reapply(path):
            """Clear the attribute like the engine does, then re-apply it like DriveFS."""
            result = real_clear(path)
            try:
                os.chmod(str(path), stat.S_IREAD)
            except OSError:
                pass
            return result

        with patch.object(rs, "clear_readonly", side_effect=clear_then_reapply):
            with self.assertRaises(rs.RepoSyncError) as ctx:
                rs.sync(self.profile, yes=True)
        message = str(ctx.exception)
        low = message.lower()
        self.assertIn("stale-ro.txt", message,
                      "the message must name the offending path")
        self.assertTrue("not fully verified" in low or "not verified" in low, message)
        self.assertNotIn("Traceback", message)
        self.assertTrue(stale.exists(),
                        "the file that could not be unlocked must not be deleted")

    # -- 14. type conflict: source FILE vs destination DIRECTORY -------
    def test_type_conflict_file_replaces_destination_directory(self):
        self.write_source("thing.txt", "file content")
        self.write_source("keep.txt", "keep")
        self.sync_once()
        # The mirror holds a file; replace it with a colliding directory that
        # carries a read-only child file and a read-only directory.
        (self.dest / "thing.txt").unlink()
        (self.dest / "thing.txt" / "sub").mkdir(parents=True)
        (self.dest / "thing.txt" / "child.txt").write_text("child")
        (self.dest / "thing.txt" / "sub" / "leaf.txt").write_text("leaf")
        mark_readonly_windows_only(self.dest / "thing.txt" / "child.txt")
        mark_readonly_windows_only(self.dest / "thing.txt" / "sub")
        mark_readonly_windows_only(self.dest / "thing.txt")
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertTrue((self.dest / "thing.txt").is_file(),
                        "the colliding directory must be replaced by the file")
        self.assertFalse((self.dest / "thing.txt").is_dir())
        self.assertEqual((self.dest / "thing.txt").read_text(encoding="utf-8"),
                         "file content")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 15. type conflict with Google Drive managed content -----------
    def test_type_conflict_with_drive_scratch_directory_aborts_and_keeps_scratch(self):
        self.write_source("thing.txt", "file content")
        self.write_source("keep.txt", "keep")
        self.sync_once()
        (self.dest / "thing.txt").unlink()
        (self.dest / "thing.txt" / ".tmp.drivedownload").mkdir(parents=True)
        busy = self.dest / "thing.txt" / ".tmp.drivedownload" / "busy.tmp"
        busy.write_text("Google Drive owns this")
        with self.assertRaises(rs.RepoSyncError) as ctx:
            rs.sync(self.profile, yes=True)
        message = str(ctx.exception)
        low = message.lower()
        self.assertIn("thing.txt", message,
                      "the message must name the offending path")
        self.assertTrue("not fully verified" in low or "not verified" in low, message)
        self.assertNotIn("Traceback", message)
        self.assertTrue(busy.is_file(),
                        "Drive managed content must never be removed")
        self.assertEqual(busy.read_text(encoding="utf-8"), "Google Drive owns this")
        self.assertTrue((self.dest / "thing.txt").is_dir(),
                        "the colliding directory must be left in place")

    # -- 16. type conflict: source DIRECTORY vs destination FILE -------
    def test_type_conflict_directory_replaces_readonly_destination_file(self):
        self.write_source("thing/inner.txt", "inner")
        self.write_source("keep.txt", "keep")
        self.sync_once()
        # The mirror holds a directory; replace it with a colliding read-only file.
        shutil.rmtree(self.dest / "thing")
        (self.dest / "thing").write_text("i am a file")
        set_readonly(self.dest / "thing")
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        self.assertTrue((self.dest / "thing").is_dir(),
                        "the colliding file must be replaced by the directory")
        self.assertEqual((self.dest / "thing" / "inner.txt").read_text(encoding="utf-8"),
                         "inner")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- 17. the error classifier itself is pinned ----------------------
    def test_is_permission_error_rejects_directory_not_empty_errno(self):
        exc = make_oserror(errno.ENOTEMPTY, "Directory not empty")
        self.assertEqual(exc.errno, errno.ENOTEMPTY)
        self.assertFalse(rs.is_permission_error(exc),
                         "a non-empty directory is never a permission problem")

    @unittest.skipUnless(os.name == "nt",
                         "Windows error codes")
    def test_is_permission_error_rejects_windows_directory_not_empty(self):
        exc = make_win_error(145, "The directory is not empty.")
        self.assertEqual(getattr(exc, "winerror", None), 145)
        self.assertFalse(rs.is_permission_error(exc),
                         "WinError 145 is a genuine content conflict, not a permission problem")

    @unittest.skipUnless(os.name == "nt",
                         "Windows error codes")
    def test_is_permission_error_accepts_windows_access_denied(self):
        exc = make_win_error(5, "Access is denied.")
        self.assertEqual(getattr(exc, "winerror", None), 5)
        self.assertTrue(rs.is_permission_error(exc),
                        "WinError 5 is the read-only attribute case and may be unlocked")

    def test_is_permission_error_accepts_posix_permission_errnos(self):
        for number in (errno.EACCES, errno.EPERM):
            exc = make_oserror(number, "Permission denied")
            self.assertEqual(exc.errno, number)
            self.assertTrue(rs.is_permission_error(exc),
                            "errno %s is an access denied style error" % number)

    # -- 18. the read-only helpers themselves are pinned ----------------
    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute")
    def test_is_readonly_detects_the_windows_readonly_attribute(self):
        path = self.write_source("probe.txt", "probe")
        self.assertFalse(rs.is_readonly(path),
                         "a normal file does not carry the attribute")
        set_readonly(path)
        self.assertTrue(rs.is_readonly(path),
                        "the attribute must be detected on a read-only file")
        clear_readonly(path)
        self.assertFalse(rs.is_readonly(path))

    @unittest.skipUnless(os.name == "nt",
                         "Windows read-only attribute")
    def test_clear_readonly_clears_the_attribute_and_reports_success(self):
        path = self.write_source("probe.txt", "probe")
        set_readonly(path)
        self.assertTrue(rs.is_readonly(path))
        self.assertTrue(rs.clear_readonly(path),
                        "clear_readonly must report that the attribute was cleared")
        self.assertFalse(rs.is_readonly(path),
                         "the attribute must be gone afterwards")
        self.assertFalse(rs.clear_readonly(self.source / "does-not-exist.txt"),
                         "a missing path is tolerated and reported as not cleared")

    @unittest.skipUnless(os.name != "nt",
                         "POSIX only: the read-only helpers must be no-ops")
    def test_helpers_are_no_ops_off_windows(self):
        path = self.write_source("probe.txt", "probe")
        os.chmod(str(path), 0o444)
        before = os.stat(str(path)).st_mode
        self.assertFalse(rs.is_readonly(path),
                         "the read-only attribute is a Windows concept")
        self.assertFalse(rs.clear_readonly(path),
                         "clear_readonly must be a no-op off Windows")
        self.assertEqual(os.stat(str(path)).st_mode, before,
                         "the mode must be left untouched off Windows")

    # -- 19. idempotence ----------------------------------------------
    def test_sync_is_idempotent(self):
        self.write_source("a.txt", "a")
        self.write_source("sub/b.txt", "b")
        first = rs.sync(self.profile, yes=True)
        self.assertTrue(first["ok"], first)
        second = rs.sync(self.profile, yes=True)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["copied"], 0, "the second sync must copy nothing")
        self.assertEqual(second["deleted_files"], 0, "the second sync must delete nothing")
        self.assertEqual(second["deleted_dirs"], 0, "the second sync must delete nothing")
        self.assertTrue(rs.verify(self.profile)["ok"])

    # -- the source tree is never modified ----------------------------
    def test_sync_never_modifies_the_source_tree(self):
        self.write_source("keep.txt", "keep")
        self.write_source("sub/other.txt", "other")
        locked = self.write_source("locked.txt", "locked")
        set_readonly(locked)
        # The snapshot is taken BEFORE the first sync, so a source mutation
        # done by either sync (attributes, content or timestamps) is caught.
        before = self.snapshot(self.source)
        self.sync_once()
        stale = self.write_dest("stale.txt", "stale")
        set_readonly(stale)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"], out)
        after = self.snapshot(self.source)
        self.assertEqual(json.dumps(before, sort_keys=True),
                         json.dumps(after, sort_keys=True),
                         "the source tree must be byte-identical after a sync")
        self.assertFalse(stale.exists(), "the sync must delete the stale entry")
        # The snapshot compares attributes and content, but the two facts that
        # matter are also asserted directly.
        self.assertTrue(is_readonly(locked),
                        "the source file must keep its read-only attribute")
        self.assertEqual(locked.read_text(encoding="utf-8"), "locked")


if __name__ == "__main__":
    unittest.main()
