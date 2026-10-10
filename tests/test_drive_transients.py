import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
import reposync as rs


class DriveManagedTempTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.source = Path(self.root.name) / "source"
        self.dest = Path(self.root.name) / "dest"
        self.source.mkdir()
        self.profile = {"name": "drive", "source": str(self.source),
                        "destination": str(self.dest), "preset": "review",
                        "include": [], "exclude": []}
        self.home = Path(self.root.name) / "home"
        self._old_home = rs.os.environ.get("REPOSYNC_HOME")
        rs.os.environ["REPOSYNC_HOME"] = str(self.home)
        self.addCleanup(self.restore_home)

    def restore_home(self):
        if self._old_home is None:
            rs.os.environ.pop("REPOSYNC_HOME", None)
        else:
            rs.os.environ["REPOSYNC_HOME"] = self._old_home

    def test_drive_scratch_directory_is_never_deleted_or_flagged_extra(self):
        (self.source / "project.txt").write_text("data")
        self.assertTrue(rs.sync(self.profile, yes=True)["ok"])
        transient = self.dest / ".tmp.driveupload"
        transient.mkdir()
        (transient / "busy.tmp").write_text("Google Drive owns this")
        (transient / "nested").mkdir()
        (transient / "nested" / "upload.tmp").write_text("open upload")
        p = rs.plan(self.profile)
        self.assertEqual(p["delete_dirs"], [])
        self.assertEqual(p["delete_files"], [])
        self.assertIn(".tmp.driveupload", p["destination_managed_exceptions"])
        self.assertTrue(rs.verify(self.profile)["ok"])
        self.assertTrue(rs.sync(self.profile, yes=True)["ok"])
        self.assertTrue((transient / "busy.tmp").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_drive_download_scratch_is_also_preserved(self):
        (self.source / "project.txt").write_text("data")
        rs.sync(self.profile, yes=True)
        transient = self.dest / ".tmp.drivedownload"
        transient.mkdir()
        (transient / "busy.part").write_text("Google Drive owns this")
        self.assertEqual(rs.plan(self.profile)["delete_dirs"], [])
        self.assertTrue(rs.sync(self.profile, yes=True)["ok"])
        self.assertTrue((transient / "busy.part").exists())

    def test_nested_drive_scratch_is_ignored_without_ignoring_real_stale(self):
        (self.source / "assets").mkdir()
        (self.source / "assets" / "keep.dat").write_text("yes")
        rs.sync(self.profile, yes=True)
        transient = self.dest / "assets" / ".tmp.driveupload"
        transient.mkdir()
        (transient / "busy.tmp").write_text("Google Drive owns this")
        (self.dest / "assets" / "obsolete.dat").write_text("old")
        p = rs.plan(self.profile)
        self.assertIn("assets/obsolete.dat", p["delete_files"])
        self.assertNotIn("assets/.tmp.driveupload", p["delete_dirs"])
        rs.sync(self.profile, yes=True)
        self.assertFalse((self.dest / "assets" / "obsolete.dat").exists())
        self.assertTrue((transient / "busy.tmp").is_file())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_source_drive_scratch_excluded_by_default(self):
        (self.source / "project.txt").write_text("yes")
        (self.source / ".tmp.driveupload").mkdir()
        (self.source / ".tmp.driveupload" / "upload.dat").write_text("runtime")
        rs.sync(self.profile, yes=True)
        self.assertFalse((self.dest / ".tmp.driveupload").exists())
        self.assertTrue(rs.verify(self.profile)["ok"])

    def test_similarly_named_project_dir_not_ignored(self):
        (self.source / "project.txt").write_text("data")
        rs.sync(self.profile, yes=True)
        (self.dest / ".tmp.driveupload2").mkdir()
        (self.dest / ".tmp.driveupload2" / "extra.dat").write_text("stale")
        self.assertIn(".tmp.driveupload2/extra.dat", rs.plan(self.profile)["delete_files"])
        self.assertFalse(rs.verify(self.profile)["ok"])
        self.assertTrue(rs.sync(self.profile, yes=True)["ok"])
        self.assertFalse((self.dest / ".tmp.driveupload2").exists())

    def test_drive_temp_file_variant_is_ignored_but_regular_extra_file_isnt(self):
        (self.source / "project.txt").write_text("data")
        rs.sync(self.profile, yes=True)
        (self.dest / ".tmp.driveupload").write_text("transient file")
        (self.dest / "extra.txt").write_text("ordinary stale")
        p = rs.plan(self.profile)
        self.assertEqual(p["delete_files"], ["extra.txt"])
        self.assertTrue(rs.sync(self.profile, yes=True)["ok"])
        self.assertTrue((self.dest / ".tmp.driveupload").is_file())


if __name__ == "__main__":
    unittest.main()
