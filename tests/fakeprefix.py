"""A fake Termux prefix for exercising openclaw-termux without touching a real install.

Layout under ``root``::

    usr/                                   $PREFIX
      bin/{sv,npm}                         stubs from tests/stubs/
      bin/openclaw -> ../lib/node_modules/openclaw/openclaw.mjs
      lib/node_modules/openclaw/           installed fake package (real patcher anchors)
      var/service/openclaw-gateway/{run,log/run}
      var/log/sv/openclaw-gateway/current
      tmp/
    home/                                  $HOME
      .openclaw/openclaw.json
      .openclaw/state/openclaw.sqlite
      .openclaw/agents/<agent>/agent/openclaw-agent.sqlite
      .openclaw/npm/projects/<plugin>/node_modules/@openclaw/<plugin>/package.json
    .fake/
      control.json                         steers the stubs (see each stub's docstring)
      calls.jsonl                          every stub invocation
      releases/<version>/                  package trees the fake npm serves
      sv/openclaw-gateway.json             fake runit state

Each fake package is built from ``tests/fixtures/openclaw-package``: synthetic JavaScript that
contains the vendored patcher's real anchor strings, so the real patcher can check and patch it.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

from openclaw_termux.patcher import patcher_path, sha256_file

TESTS = Path(__file__).resolve().parent
FIXTURE = TESTS / "fixtures" / "openclaw-package"
STUBS = TESTS / "stubs"

SERVICE = "openclaw-gateway"
AGENTS = ("proving-ground", "main", "openclaw")
PLUGINS = ("codex",)
JS_PATCH_TYPES = ("service", "dashboard", "fs-safe", "loader", "proc", "migrate", "birth", "owner", "ancestor", "lifecycle")


def patcher_constants(names: Iterable[str]) -> dict:
    """Read string constants from the vendored patcher's embedded Python, without running it."""
    text = patcher_path().read_text(encoding="utf-8")
    start = text.index("<< 'PYEOF'\n") + len("<< 'PYEOF'\n")
    end = text.rindex("\nPYEOF")
    wanted, values = set(names), {}
    for node in ast.parse(text[start:end]).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted):
            values[node.targets[0].id] = ast.literal_eval(node.value)
    missing = wanted - set(values)
    if missing:
        raise KeyError(f"patcher constants not found: {sorted(missing)}")
    return values


def _install_stub(name: str, dest: Path) -> None:
    source = (STUBS / f"{name}.py").read_text(encoding="utf-8")
    dest.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
    dest.chmod(0o755)


def _make_db(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT OR REPLACE INTO meta VALUES ('label', ?)", (label,))
    db.close()


class FakePrefix:
    def __init__(
        self,
        root: os.PathLike,
        *,
        releases: Iterable[str] = ("2026.10.4",),
        installed: Optional[str] = "2026.10.4",
        native_applied: bool = True,
        gateway_up: bool = True,
    ):
        self.root = Path(root)
        self.prefix = self.root / "usr"
        self.home = self.root / "home"
        self.fake = self.root / ".fake"
        self.service_dir = self.prefix / "var" / "service" / SERVICE
        for d in (self.prefix / "bin", self.prefix / "lib" / "node_modules", self.prefix / "tmp",
                  self.prefix / "var" / "log" / "sv" / SERVICE, self.home, self.fake / "releases", self.fake / "sv"):
            d.mkdir(parents=True, exist_ok=True)
        (self.fake / "control.json").write_text("{}\n", encoding="utf-8")
        (self.fake / "calls.jsonl").touch()
        for stub in ("sv", "npm"):
            _install_stub(stub, self.prefix / "bin" / stub)
        for version in releases:
            self.add_release(version, native_applied=native_applied)
        self._make_service()
        self._make_home()
        if installed is not None:
            self.install(installed)
            if gateway_up:
                self.run("sv", "up", str(self.service_dir), check=True)

    # ── construction ────────────────────────────────────────────────────────
    def add_release(self, version: str, *, native_applied: bool = True) -> Path:
        tree = self.fake / "releases" / version
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(FIXTURE, tree)
        (tree / "package.json").write_text(json.dumps({
            "name": "openclaw",
            "version": version,
            "bin": {"openclaw": "openclaw.mjs"},
            "dependencies": {"@openclaw/fs-safe": "0.24.2"},
        }, indent=2) + "\n", encoding="utf-8")
        _install_stub("openclaw", tree / "openclaw.mjs")
        if native_applied:
            self._make_native_addon(tree)
        return tree

    def _make_native_addon(self, tree: Path) -> None:
        """Fake an already-relinked fs-safe native addon, so the patcher never tries to build one."""
        c = patcher_constants(["NATIVE_PKG", "NATIVE_ID", "NATIVE_MARKER", "SHIM_NAME", "WRAPPER_NAME", "WRAPPER_SOURCE"])
        native = tree / "node_modules" / Path(*c["NATIVE_PKG"].split("/"))
        native.mkdir(parents=True, exist_ok=True)
        (native / "fs-safe-native.node").write_bytes(b"fake relinked addon\n")
        (native / c["SHIM_NAME"]).write_bytes(b"fake bionic shim\n")
        (native / c["WRAPPER_NAME"]).write_text(c["WRAPPER_SOURCE"], encoding="utf-8")
        (native / "package.json").write_text(json.dumps({"name": c["NATIVE_PKG"], "main": c["WRAPPER_NAME"]}) + "\n")
        (native / c["NATIVE_MARKER"]).write_text(json.dumps({
            "patch": c["NATIVE_ID"],
            "fsSafeVersion": "0.24.2",
            "nodeSha256": sha256_file(native / "fs-safe-native.node"),
            "shimSha256": sha256_file(native / c["SHIM_NAME"]),
            "wrapperSha256": sha256_file(native / c["WRAPPER_NAME"]),
        }, indent=2), encoding="utf-8")

    def _make_service(self) -> None:
        (self.service_dir / "log").mkdir(parents=True, exist_ok=True)
        run = self.service_dir / "run"
        run.write_text(
            f"#!{self.prefix}/bin/sh\nset -e\nexport HOME=\"${{PREFIX%/usr}}/home\"\nexec openclaw gateway run 2>&1\n",
            encoding="utf-8",
        )
        run.chmod(0o700)
        log_run = self.service_dir / "log" / "run"
        log_run.write_text(f"#!{self.prefix}/bin/sh\nexec svlogd -tt \"{self.prefix}/var/log/sv/{SERVICE}\"\n")
        log_run.chmod(0o700)
        (self.prefix / "var" / "log" / "sv" / SERVICE / "current").touch()

    def _make_home(self) -> None:
        oc = self.home / ".openclaw"
        oc.mkdir(parents=True, exist_ok=True)
        (oc / "openclaw.json").write_text(json.dumps({"gateway": {"mode": "local"}}, indent=2) + "\n")
        _make_db(oc / "state" / "openclaw.sqlite", "state")
        for agent in AGENTS:
            _make_db(oc / "agents" / agent / "agent" / "openclaw-agent.sqlite", agent)
        for plugin in PLUGINS:
            project = oc / "npm" / "projects" / plugin / "node_modules"
            pkg = project / "@openclaw" / plugin
            pkg.mkdir(parents=True, exist_ok=True)
            (pkg / "package.json").write_text(json.dumps({"name": f"@openclaw/{plugin}", "version": "2026.10.4"}) + "\n")
            peer = project / "openclaw"
            if not peer.is_symlink():
                peer.symlink_to(self.package_dir)

    # ── operations ──────────────────────────────────────────────────────────
    def install(self, version: str) -> None:
        """Install a release the way npm install -g does: in place, over whatever is there."""
        self.run("npm", "install", "-g", f"openclaw@{version}", check=True)

    def env(self, **extra: str) -> dict:
        env = {
            "PATH": f"{self.prefix / 'bin'}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "PREFIX": str(self.prefix),
            "TMPDIR": str(self.prefix / "tmp"),
            "LANG": "C.UTF-8",
            "OPENCLAW_TERMUX_FAKE_ROOT": str(self.root),
        }
        env.update(extra)
        return env

    def run(self, *argv: str, check: bool = False, **kwargs) -> subprocess.CompletedProcess:
        kwargs.setdefault("env", self.env())
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        exe = shutil.which(argv[0], path=kwargs["env"]["PATH"]) or argv[0]
        result = subprocess.run([exe, *argv[1:]], **kwargs)
        if check and result.returncode != 0:
            raise AssertionError(f"{argv} exited {result.returncode}: {result.stdout}{result.stderr}")
        return result

    def control(self, **sections: dict) -> None:
        path = self.fake / "control.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for name, values in sections.items():
            data.setdefault(name, {}).update(values)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def calls(self, tool: Optional[str] = None) -> list:
        lines = (self.fake / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        calls = [json.loads(line) for line in lines if line.strip()]
        return [c for c in calls if tool is None or c["tool"] == tool]

    # ── inspection ──────────────────────────────────────────────────────────
    @property
    def package_dir(self) -> Path:
        return self.prefix / "lib" / "node_modules" / "openclaw"

    @property
    def dist(self) -> Path:
        return self.package_dir / "dist"

    def installed_version(self) -> Optional[str]:
        try:
            return json.loads((self.package_dir / "package.json").read_text(encoding="utf-8"))["version"]
        except (OSError, ValueError, KeyError):
            return None

    def sv_state(self) -> dict:
        path = self.fake / "sv" / f"{SERVICE}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def databases(self) -> list:
        oc = self.home / ".openclaw"
        return [oc / "state" / "openclaw.sqlite"] + [
            oc / "agents" / a / "agent" / "openclaw-agent.sqlite" for a in AGENTS
        ]
