"""Offline integration tests. No Google Drive/credentials/Git/extra packages required."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
import reposync as rs


class RepoSyncTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.home = Path(self.root.name) / "config"
        self.env = patch.dict(os.environ, {"REPOSYNC_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.source = Path(self.root.name) / "source"
        self.dest = Path(self.root.name) / "dest"
        self.source.mkdir()
        self.profile = {"name":"demo", "source":str(self.source), "destination":str(self.dest),
                        "preset":"review", "include":[], "exclude":[]}

    def write(self, rel, value="data"):
        path = self.source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def test_any_local_folder_no_git_and_mirror_exactly(self):
        self.write("a.txt", "a")
        self.write("sub/b.txt", "b")
        self.write(".claude/SKILL.md", "skill")
        self.write("assets/image.png", "image")
        self.write("node_modules/x.js", "excluded")
        self.write(".env", "DO_NOT_COPY")
        self.write("token.json", "DO_NOT_COPY")
        self.write(".git/HEAD", "DO_NOT_COPY")
        self.write("__pycache__/x.pyc", "excluded")
        self.write(".reposync/dont-copy.txt", "exclude")
        self.assertIsNone(rs.git_info(self.source))
        preview = rs.plan(self.profile)
        self.assertEqual(preview["owner"], "new")
        self.assertEqual(len(preview["copy"]), 4)
        out = rs.sync(self.profile, yes=True)
        self.assertTrue(out["ok"])
        self.assertEqual((self.dest / ".claude/SKILL.md").read_text(), "skill")
        self.assertTrue((self.dest / "assets/image.png").exists())
        for name in ("node_modules/x.js", ".env", "token.json", ".git/HEAD", "__pycache__/x.pyc", ".reposync/dont-copy.txt"):
            self.assertFalse((self.dest / name).exists(), name)
        self.assertTrue((self.dest / ".reposync/owner.json").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_deleted_and_excluded_files_really_disappear(self):
        self.write("keep.txt", "yes")
        self.write("remove.txt", "old")
        rs.sync(self.profile, yes=True)
        (self.source / "remove.txt").unlink()
        (self.dest / "stray.txt").write_text("unowned", encoding="utf-8")
        (self.dest / "node_modules").mkdir()
        (self.dest / "node_modules/stale.js").write_text("secret", encoding="utf-8")
        preview = rs.plan(self.profile)
        self.assertIn("remove.txt", preview["delete_files"])
        self.assertIn("stray.txt", preview["delete_files"])
        rs.sync(self.profile, yes=True)
        self.assertFalse((self.dest / "remove.txt").exists())
        self.assertFalse((self.dest / "stray.txt").exists())
        self.assertFalse((self.dest / "node_modules").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_edited_same_size_same_timestamp_detected_by_hash(self):
        original = self.write("same.txt", "hello")
        rs.sync(self.profile, yes=True)
        st = original.stat()
        original.write_text("world", encoding="utf-8")
        os.utime(original, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertIn("same.txt", rs.plan(self.profile)["copy"])
        rs.sync(self.profile, yes=True)
        self.assertEqual((self.dest / "same.txt").read_text(), "world")

    def test_empty_dirs_and_dir_removal(self):
        (self.source / "empty/subempty").mkdir(parents=True)
        self.write("a.txt")
        rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / "empty/subempty").is_dir())
        (self.source / "empty/subempty").rmdir()
        (self.source / "empty").rmdir()
        rs.sync(self.profile, yes=True)
        self.assertFalse((self.dest / "empty").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_default_hidden_project_content_preserved(self):
        self.write(".github/workflows/ci.yml", "x")
        self.write(".claude/agents/worker.md", "x")
        self.write(".claude/settings.local.json", "secret")
        rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / ".github/workflows/ci.yml").is_file())
        self.assertTrue((self.dest / ".claude/agents/worker.md").is_file())
        self.assertFalse((self.dest / ".claude/settings.local.json").exists())

    def test_include_patterns_and_user_excludes(self):
        self.write("src/a.py")
        self.write("docs/readme.md")
        self.write("docs/no.txt")
        self.write("assets/movie.mp4")
        self.profile["include"] = ["src/**", "docs/**"]
        self.profile["exclude"] = ["*.txt"]
        rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / "src/a.py").exists())
        self.assertTrue((self.dest / "docs/readme.md").exists())
        self.assertFalse((self.dest / "docs/no.txt").exists())
        self.assertFalse((self.dest / "assets").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_code_preset_excludes_media(self):
        self.write("main.py")
        self.write("data/clip.mp4")
        self.profile["preset"] = "code"
        rs.sync(self.profile, yes=True)
        self.assertFalse((self.dest / "data/clip.mp4").exists())
        self.assertTrue((self.dest / "main.py").exists())

    def test_refuses_nested_paths_and_roots(self):
        with self.assertRaises(rs.RepoSyncError):
            rs.validate_paths(self.source, self.source / "nested")
        with self.assertRaises(rs.RepoSyncError):
            rs.validate_paths(self.source, self.source.parent)
        with self.assertRaises(rs.RepoSyncError):
            rs.validate_paths(self.source, Path(self.source.anchor))

    def test_refuses_adoption_without_explicit_flag(self):
        self.write("a.txt")
        self.dest.mkdir()
        (self.dest / "foreign.txt").write_text("foreign")
        self.assertEqual(rs.plan(self.profile)["owner"], "unmanaged-populated")
        with self.assertRaises(rs.RepoSyncError):
            rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / "foreign.txt").exists())
        rs.sync(self.profile, yes=True, adopt=True)
        self.assertFalse((self.dest / "foreign.txt").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_refuses_owner_mismatch(self):
        self.write("keep.txt")
        rs.sync(self.profile, yes=True)
        other = {**self.profile, "name": "other"}
        with self.assertRaises(rs.RepoSyncError):
            rs.sync(other, yes=True)
        self.assertTrue((self.dest / "keep.txt").exists())

    def test_unauthorized_noninteractive_sync_no_changes(self):
        self.write("a.txt")
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(rs.RepoSyncError, "--yes"):
                rs.sync(self.profile)
        self.assertFalse(self.dest.exists())

    def test_verify_detects_extra_missing_and_modified(self):
        self.write("a.txt")
        self.write("b.txt")
        rs.sync(self.profile, yes=True)
        (self.dest / "a.txt").unlink()
        (self.dest / "b.txt").write_text("changed")
        (self.dest / "extra.txt").write_text("bad")
        report = rs.verify(self.profile)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], ["a.txt"])
        self.assertEqual(report["extra"], ["extra.txt"])
        self.assertEqual(report["different"], ["b.txt"])

    def test_symlink_in_source_skipped_and_destination_refused(self):
        outside = Path(self.root.name) / "outside.txt"
        outside.write_text("private")
        try:
            (self.source / "link.txt").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted")
        self.write("a.txt")
        report = rs.sync(self.profile, yes=True)
        self.assertTrue(report["warnings"])
        self.assertFalse((self.dest / "link.txt").exists())
        (self.dest / "unsafe.txt").symlink_to(outside)
        with self.assertRaisesRegex(rs.RepoSyncError, "unsafe link"):
            rs.plan(self.profile)
        self.assertEqual(outside.read_text(), "private")

    def test_file_and_directory_type_changes(self):
        self.write("old/file.txt", "x")
        self.write("new", "just a file")
        rs.sync(self.profile, yes=True)
        (self.source / "old/file.txt").unlink()
        (self.source / "old").rmdir()
        self.write("old", "converted to file")
        (self.source / "new").unlink()
        self.write("new/child.txt", "converted to folder")
        preview = rs.plan(self.profile)
        self.assertEqual(set(preview["type_conflicts"]), {"new", "old"})
        rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / "old").is_file())
        self.assertTrue((self.dest / "new/child.txt").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_profiles_persist_and_cli_json(self):
        self.write("a.txt")
        args = ["add", "demo", "--source", str(self.source), "--destination", str(self.dest), "--json"]
        def run_cli(*a):
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                code = rs.main(list(a))
            return code, json.loads(capture.getvalue())
        code, result = run_cli(*args)
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        code, result = run_cli("preview", "demo", "--json")
        self.assertEqual(result["copy"], ["a.txt"])
        code, result = run_cli("sync", "demo", "--yes", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        code, result = run_cli("status", "demo", "--json")
        self.assertEqual(result["last_sync"]["source_files"], 1)
        code, result = run_cli("verify", "demo", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        code, result = run_cli("update", "demo", "--exclude", "a.txt", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(result["profile"]["exclude"], ["a.txt"])
        code, result = run_cli("preview", "demo", "--json")
        self.assertEqual(result["delete_files"], ["a.txt"])

    def test_source_changes_during_copy_prevents_deletion(self):
        self.write("one.txt", "first")
        self.write("two.txt", "second")
        rs.sync(self.profile, yes=True)
        (self.source / "two.txt").unlink()
        self.write("one.txt", "changed")
        original_copy = rs.shutil.copy2
        def mutating_copy(src, dst):
            res = original_copy(src, dst)
            (self.source / "new.txt").write_text("late", encoding="utf-8")
            return res
        with patch.object(rs.shutil, "copy2", side_effect=mutating_copy):
            with self.assertRaisesRegex(rs.RepoSyncError, "Source changed"):
                rs.sync(self.profile, yes=True)
        self.assertTrue((self.dest / "two.txt").exists(), "old files must not be deleted on changed source")


if __name__ == "__main__":
    unittest.main()
