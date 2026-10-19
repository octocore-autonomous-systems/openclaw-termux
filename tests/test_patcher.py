"""The vendored patcher: integrity, and its real behaviour against the fake package."""

import re
import tempfile
import unittest
from pathlib import Path

from openclaw_termux import patcher
from openclaw_termux.patcher import CHECK_APPLIED, CHECK_NEEDED, PATCHER_ERROR, run_patcher, sha256_file
from tests import REPO
from tests.fakeprefix import JS_PATCH_TYPES, FakePrefix


def tree_hashes(root: Path) -> dict:
    return {p.relative_to(root): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


class PatcherIntegrityTest(unittest.TestCase):
    def test_vendored_patcher_matches_recorded_hash(self):
        self.assertEqual(sha256_file(patcher.patcher_path()), patcher.PATCHER_SHA256)

    def test_readme_records_the_same_hash(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn(patcher.PATCHER_SHA256, readme)

    def test_verify_refuses_a_modified_patcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "openclaw-patch-android"
            copy.write_bytes(patcher.patcher_path().read_bytes() + b"\n# tampered\n")
            with self.assertRaises(patcher.PatcherIntegrityError):
                patcher.verify_patcher(copy)


class PatcherBehaviourTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fp = FakePrefix(self._tmp.name, gateway_up=False)
        self.backups = Path(self._tmp.name) / "backups"

    def tearDown(self):
        self._tmp.cleanup()

    def check(self):
        return run_patcher(self.fp.dist, env=self.fp.env())

    def test_fresh_package_needs_every_js_patch(self):
        report = self.check()
        self.assertEqual(report.returncode, CHECK_NEEDED, report.stderr)
        self.assertEqual(report.needed, sorted(JS_PATCH_TYPES))
        self.assertIn("Patch status: needed:", report.stdout)

    def test_apply_then_check_reports_applied(self):
        applied = run_patcher(self.fp.dist, check=False, backup_dir=self.backups, env=self.fp.env())
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertIn("Patched OK.", applied.stdout)
        report = self.check()
        self.assertEqual(report.returncode, CHECK_APPLIED, report.stdout + report.stderr)
        self.assertEqual(report.needed, [])
        self.assertTrue(any(self.backups.iterdir()), "pristine originals were not backed up")

    def test_second_apply_changes_nothing(self):
        run_patcher(self.fp.dist, check=False, backup_dir=self.backups, env=self.fp.env())
        before = tree_hashes(self.fp.package_dir)
        again = run_patcher(self.fp.dist, check=False, backup_dir=self.backups, env=self.fp.env())
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("already applied", again.stdout)
        self.assertEqual(tree_hashes(self.fp.package_dir), before)

    def test_missing_native_addon_is_reported_needed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fp = FakePrefix(tmp.name, gateway_up=False, native_applied=False)
        report = run_patcher(fp.dist, env=fp.env())
        self.assertEqual(report.returncode, CHECK_NEEDED, report.stderr)
        self.assertIn("native", report.needed)

    def test_missing_anchor_fails_closed_without_writing(self):
        target = self.fp.dist / "sqlite-identity.mjs"
        target.write_text(target.read_text().replace("useDatabaseBirthtime", "useBirthtime"))
        before = tree_hashes(self.fp.package_dir)
        for check in (True, False):
            report = run_patcher(self.fp.dist, check=check, backup_dir=self.backups, env=self.fp.env())
            self.assertEqual(report.returncode, PATCHER_ERROR, report.stdout)
            self.assertIn("useDatabaseBirthtime anchor not found", report.error)
        self.assertEqual(tree_hashes(self.fp.package_dir), before)
        self.assertFalse(self.backups.exists())

    def test_duplicate_anchor_fails_closed_without_writing(self):
        target = self.fp.dist / "dashboard.mjs"
        text = target.read_text()
        target.write_text(re.sub(r"(\tif \(!options\.noOpen\) \{)", r"\1\n\t}\n\1", text, count=1))
        before = tree_hashes(self.fp.package_dir)
        report = run_patcher(self.fp.dist, check=False, backup_dir=self.backups, env=self.fp.env())
        self.assertEqual(report.returncode, PATCHER_ERROR, report.stdout)
        self.assertIn("must occur exactly once", report.error)
        self.assertEqual(tree_hashes(self.fp.package_dir), before)


if __name__ == "__main__":
    unittest.main()
