"""The fake prefix behaves like the parts of Termux, runit, npm and OpenClaw the manager relies on."""

import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.fakeprefix import AGENTS, FakePrefix

# What the patched OpenClaw runit adapter parses out of `sv status` (see patch/openclaw-patch-android).
RUN_RE = re.compile(r"^run: [^:]+: \(pid (\d+)\) (\d+)s")
DOWN_RE = re.compile(r"^(down|finish): [^:]+: (\d+)s")


class FakePrefixTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fp = FakePrefix(self._tmp.name, releases=("2026.10.3", "2026.10.4"), installed="2026.10.3")

    def tearDown(self):
        self._tmp.cleanup()

    def sv(self, *args):
        return self.fp.run("sv", *args, str(self.fp.service_dir))

    def openclaw(self, *args):
        return self.fp.run("openclaw", *args)

    def test_layout(self):
        self.assertEqual(self.fp.installed_version(), "2026.10.3")
        self.assertEqual(Path(self.fp.prefix / "bin" / "openclaw").resolve(), (self.fp.package_dir / "openclaw.mjs").resolve())
        self.assertTrue((self.fp.service_dir / "run").is_file())
        self.assertTrue((self.fp.service_dir / "log" / "run").is_file())
        for plugin_link in (self.fp.home / ".openclaw" / "npm" / "projects").glob("*/node_modules/openclaw"):
            self.assertEqual(plugin_link.resolve(), self.fp.package_dir.resolve())

    def test_databases_are_real_sqlite(self):
        self.assertEqual(len(self.fp.databases()), 1 + len(AGENTS))
        for path in self.fp.databases():
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            db.close()

    def test_sv_status_matches_the_runit_format(self):
        up = self.sv("status")
        self.assertEqual(up.returncode, 0)
        self.assertRegex(up.stdout, RUN_RE)
        self.assertEqual(self.sv("-w", "60", "down").returncode, 0)
        self.assertRegex(self.sv("status").stdout, DOWN_RE)

    def test_sv_restart_gets_a_new_pid(self):
        before = self.fp.sv_state()["pid"]
        self.sv("-w", "60", "restart")
        self.assertNotEqual(self.fp.sv_state()["pid"], before)

    def test_sv_crash_loop_changes_pid_on_every_status(self):
        self.fp.control(sv={"crash_loop": True})
        pids = {RUN_RE.match(self.sv("status").stdout).group(1) for _ in range(3)}
        self.assertEqual(len(pids), 3)

    def test_sv_failure_injection(self):
        self.fp.control(sv={"fail": {"up": 1}})
        self.sv("down")
        result = self.sv("-w", "60", "up")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("timeout: "))

    def test_sv_refuses_a_missing_service(self):
        result = self.fp.run("sv", "status", str(self.fp.prefix / "var" / "service" / "nope"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("unable to change to service directory", result.stdout)

    def test_gateway_keeps_running_the_version_it_started_with(self):
        self.fp.install("2026.10.4")
        self.assertEqual(self.openclaw("--version").stdout.strip(), "OpenClaw 2026.10.4 (fake)")
        status = json.loads(self.openclaw("status", "--json").stdout)
        self.assertEqual(status["runtimeVersion"], "2026.10.3")
        self.sv("-w", "60", "restart")
        status = json.loads(self.openclaw("status", "--json").stdout)
        self.assertEqual(status["runtimeVersion"], "2026.10.4")

    def test_health_becomes_ready_after_configured_polls(self):
        self.fp.control(openclaw={"ready_after_polls": 2})
        self.sv("-w", "60", "restart")
        results = [self.openclaw("health", "--json").returncode for _ in range(3)]
        self.assertEqual(results, [1, 1, 0])

    def test_health_fails_while_the_gateway_is_down(self):
        self.sv("-w", "60", "down")
        self.assertEqual(self.openclaw("health", "--json").returncode, 1)
        status = json.loads(self.openclaw("status", "--json").stdout)
        self.assertFalse(status["gateway"]["reachable"])

    def test_openclaw_exit_injection(self):
        self.fp.control(openclaw={"exit": {"config validate": 1}})
        self.assertEqual(self.openclaw("config", "validate").returncode, 1)
        self.assertEqual(self.openclaw("models", "list", "--json").stdout.strip(), "[]")

    def test_npm_view_and_install_into_a_staging_prefix(self):
        self.assertEqual(self.fp.run("npm", "view", "openclaw", "version").stdout.strip(), "2026.10.4")
        self.assertEqual(self.fp.run("npm", "view", "openclaw@9.9.9", "version").returncode, 1)
        staging = self.fp.prefix / "lib" / "node_modules" / ".openclaw-termux" / "staging" / "2026.10.4"
        result = self.fp.run("npm", "install", "-g", "openclaw@2026.10.4", "--prefix", str(staging), "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        staged = json.loads((staging / "lib" / "node_modules" / "openclaw" / "package.json").read_text())
        self.assertEqual(staged["version"], "2026.10.4")
        self.assertEqual(self.fp.installed_version(), "2026.10.3", "staging must not touch the live package")

    def test_npm_install_failure_injection_leaves_the_package_alone(self):
        self.fp.control(npm={"install_exit": 1})
        self.assertEqual(self.fp.run("npm", "install", "-g", "openclaw@2026.10.4").returncode, 1)
        self.assertEqual(self.fp.installed_version(), "2026.10.3")

    def test_calls_are_recorded(self):
        self.openclaw("--version")
        self.sv("status")
        tools = [c["tool"] for c in self.fp.calls()]
        self.assertIn("openclaw", tools)
        self.assertIn("sv", tools)
        self.assertIn("npm", tools)


if __name__ == "__main__":
    unittest.main()
