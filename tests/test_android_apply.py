"""Apply the full Android patch set to a scratch copy of a real release (Termux only, opt-in).

Set ``OPENCLAW_TERMUX_RELEASE=<version>`` and ``OPENCLAW_TERMUX_ANDROID_APPLY=1`` on Termux. The
native step relinks the fs-safe musl prebuild for Bionic, so it needs ``npm``, ``patchelf`` and
``clang``. It never touches the installed OpenClaw package.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from openclaw_termux.patcher import CHECK_APPLIED, CHECK_NEEDED, PATCH_TYPES, run_patcher
from tests.test_release import RELEASE, release_view

ENABLED = RELEASE and os.environ.get("OPENCLAW_TERMUX_ANDROID_APPLY") == "1" and os.environ.get("TERMUX_VERSION")


@unittest.skipUnless(ENABLED, "set OPENCLAW_TERMUX_RELEASE and OPENCLAW_TERMUX_ANDROID_APPLY=1 on Termux")
class AndroidApplyTest(unittest.TestCase):
    def test_full_patch_set_applies_to_a_staged_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "openclaw"
            shutil.copytree(release_view(RELEASE), staged, symlinks=True)
            backups = Path(tmp) / "backups"

            before = run_patcher(staged / "dist")
            self.assertEqual(before.returncode, CHECK_NEEDED, before.stderr)
            self.assertEqual(before.needed, sorted(PATCH_TYPES))

            applied = run_patcher(staged / "dist", check=False, backup_dir=backups)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertIn("Patched OK.", applied.stdout)

            after = run_patcher(staged / "dist")
            self.assertEqual(after.returncode, CHECK_APPLIED, after.stdout + after.stderr)

            again = run_patcher(staged / "dist", check=False, backup_dir=backups)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already applied", again.stdout)


if __name__ == "__main__":
    unittest.main()
