"""The patcher against a real OpenClaw release from the npm registry (opt-in, needs network).

Set ``OPENCLAW_TERMUX_RELEASE=<version>`` to run. The release's patch view (``package.json``,
``dist/`` and its pinned ``@openclaw/fs-safe``) is assembled from two ``npm pack`` tarballs into
``OPENCLAW_TERMUX_RELEASE_CACHE`` (default ``~/.cache/openclaw-termux-tests``). Only ``--check`` runs:
applying the patches builds an Android-only native addon.
"""

import contextlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from openclaw_termux.patcher import CHECK_NEEDED, PATCH_TYPES, PATCHER_ERROR, run_patcher

RELEASE = os.environ.get("OPENCLAW_TERMUX_RELEASE")
CACHE = Path(os.environ.get("OPENCLAW_TERMUX_RELEASE_CACHE", Path.home() / ".cache" / "openclaw-termux-tests"))


def _extract(tgz: Path, dest: Path, members=None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz) as tar:
        chosen = []
        for m in tar.getmembers():
            if not m.name.startswith("package/"):
                continue
            rel = m.name[len("package/"):]
            if members and not any(rel == p or rel.startswith(p + "/") for p in members):
                continue
            m.name = rel
            chosen.append(m)
        tar.extractall(dest, members=chosen, filter="data")


def release_view(version: str) -> Path:
    """Return ``<cache>/<version>/openclaw``, building it with npm pack on first use."""
    root = CACHE / version
    view = root / "openclaw"
    if (view / ".complete").exists():
        return view
    shutil.rmtree(root, ignore_errors=True)
    downloads = root / "downloads"
    downloads.mkdir(parents=True)

    def pack(spec):
        out = subprocess.run(["npm", "pack", spec, "--pack-destination", str(downloads), "--silent"],
                             capture_output=True, text=True, check=True)
        return downloads / out.stdout.strip().splitlines()[-1]

    _extract(pack(f"openclaw@{version}"), view, members=("package.json", "dist"))
    fs_safe = json.loads((view / "package.json").read_text())["dependencies"]["@openclaw/fs-safe"]
    _extract(pack(f"@openclaw/fs-safe@{fs_safe}"), view / "node_modules" / "@openclaw" / "fs-safe")
    shutil.rmtree(downloads)
    (view / ".complete").touch()
    return view


@unittest.skipUnless(RELEASE, "set OPENCLAW_TERMUX_RELEASE=<version> to check a real release")
class RealReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = release_view(RELEASE)

    def test_every_patch_type_applies_to_the_release(self):
        report = run_patcher(self.view / "dist")
        self.assertEqual(report.returncode, CHECK_NEEDED, report.stderr)
        self.assertEqual(report.needed, sorted(PATCH_TYPES))

    def test_a_missing_anchor_in_the_release_fails_closed(self):
        with self._edited("sqlite-worker-identity", 'useDatabaseBirthtime = process.platform !== "linux";',
                          "useDatabaseBirthtime = true;", every=True):
            report = run_patcher(self.view / "dist")
        self.assertEqual(report.returncode, PATCHER_ERROR, report.stdout)
        self.assertIn("useDatabaseBirthtime anchor not found", report.error)

    def test_a_duplicated_anchor_in_the_release_fails_closed(self):
        anchor = "if (!options.noOpen) {"
        with self._edited("dashboard-", anchor, anchor + "}\n" + anchor):
            report = run_patcher(self.view / "dist")
        self.assertEqual(report.returncode, PATCHER_ERROR, report.stdout)
        self.assertIn("must occur exactly once", report.error)

    @contextlib.contextmanager
    def _edited(self, name_part, old, new, every=False):
        """Temporarily replace ``old`` with ``new`` in the release's dist files.

        ``every=True`` edits every file containing ``old``; otherwise only the first occurrence in
        files whose name contains ``name_part``.
        """
        saved = {}
        try:
            for path in sorted((self.view / "dist").rglob("*")):
                if not path.is_file() or path.suffix not in (".js", ".mjs"):
                    continue
                if not every and name_part not in path.name:
                    continue
                text = path.read_text(encoding="utf-8", errors="surrogateescape")
                if old in text:
                    saved[path] = text
                    path.write_text(text.replace(old, new, -1 if every else 1),
                                    encoding="utf-8", errors="surrogateescape")
            if not saved:
                raise AssertionError(f"anchor {old!r} not found in the release")
            yield
        finally:
            for path, text in saved.items():
                path.write_text(text, encoding="utf-8", errors="surrogateescape")


if __name__ == "__main__":
    unittest.main()
