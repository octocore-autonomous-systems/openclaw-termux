"""Locate, verify and run the Android patcher (``patch/openclaw-patch-android``).

The patcher is vendored byte-for-byte. Changes to the patch set arrive only through pull requests that
also update ``PATCHER_SHA256`` and the hash recorded in the README; ``verify_patcher`` refuses to run
anything else.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

PATCHER_SHA256 = "47522583f17ec9472a9065bb7874c03193e97699f94b120b7675a27821661661"

# Patch types the patcher reports, in its own reporting order. "native" is the relinked fs-safe addon.
PATCH_TYPES = (
    "service",
    "dashboard",
    "fs-safe",
    "loader",
    "proc",
    "migrate",
    "birth",
    "owner",
    "ancestor",
    "lifecycle",
    "native",
)

# Exit codes of ``openclaw-patch-android --check``. Apply mode exits 0 on success and 2 on error.
CHECK_APPLIED = 0
CHECK_NEEDED = 1
PATCHER_ERROR = 2

_STATUS_LINE = re.compile(r"^(?P<name>[a-z-]+)\s+(?P<state>applied|needed)\s+(?P<path>\S.*)$")


class PatcherIntegrityError(RuntimeError):
    """The vendored patcher is missing or does not match ``PATCHER_SHA256``."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def patcher_path() -> Path:
    return repo_root() / "patch" / "openclaw-patch-android"


def sha256_file(path: os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_patcher(path: Optional[Path] = None) -> Path:
    path = path or patcher_path()
    if not path.is_file():
        raise PatcherIntegrityError(f"patcher not found: {path}")
    actual = sha256_file(path)
    if actual != PATCHER_SHA256:
        raise PatcherIntegrityError(
            f"patcher {path} has sha256 {actual}, expected {PATCHER_SHA256}; refusing to run it"
        )
    return path


@dataclass(frozen=True)
class PatchEntry:
    name: str
    state: str
    path: str


@dataclass
class PatchReport:
    returncode: int
    stdout: str
    stderr: str
    entries: list = field(default_factory=list)

    @property
    def status(self) -> str:
        """``applied``, ``needed`` or ``error`` (check mode); ``applied`` or ``error`` (apply mode)."""
        return {CHECK_APPLIED: "applied", CHECK_NEEDED: "needed"}.get(self.returncode, "error")

    @property
    def needed(self) -> list:
        return sorted({e.name for e in self.entries if e.state == "needed"})

    @property
    def error(self) -> str:
        lines = [line for line in self.stderr.splitlines() if line.startswith("ERROR:")]
        return lines[-1][len("ERROR:"):].strip() if lines else self.stderr.strip()


def parse_report(returncode: int, stdout: str, stderr: str) -> PatchReport:
    entries = []
    for line in stdout.splitlines():
        m = _STATUS_LINE.match(line)
        if m and m["name"] in PATCH_TYPES:
            entries.append(PatchEntry(m["name"], m["state"], m["path"]))
    return PatchReport(returncode, stdout, stderr, entries)


def run_patcher(
    dist: os.PathLike,
    *,
    check: bool = True,
    backup_dir: Optional[os.PathLike] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
) -> PatchReport:
    """Run the verified patcher against ``dist`` (a package's ``dist/`` directory).

    The patcher is started through ``bash`` so its Termux-absolute shebang never matters.
    """
    path = verify_patcher()
    cmd = ["bash", str(path)]
    if check:
        cmd.append("--check")
    cmd += ["--dist", str(dist)]
    if backup_dir is not None:
        cmd += ["--backup-dir", str(backup_dir)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=dict(env) if env is not None else None, timeout=timeout
    )
    return parse_report(proc.returncode, proc.stdout, proc.stderr)
