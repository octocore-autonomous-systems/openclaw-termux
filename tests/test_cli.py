"""The command-line skeleton and its entry point."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from openclaw_termux import __version__, cli
from tests import REPO

ENTRY = REPO / "bin" / "openclaw-termux"


def run_entry(*args):
    return subprocess.run(["bash", str(ENTRY), *args], capture_output=True, text=True)


class CliTest(unittest.TestCase):
    def test_version_file_matches_package(self):
        self.assertEqual((REPO / "VERSION").read_text().strip(), __version__)

    def test_version_flag(self):
        result = run_entry("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"openclaw-termux {__version__}")

    def test_no_command_is_a_usage_error(self):
        result = run_entry()
        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertIn("usage: openclaw-termux", result.stderr)

    def test_unknown_command_is_a_usage_error(self):
        self.assertEqual(run_entry("frobnicate").returncode, cli.EXIT_USAGE)

    def test_planned_commands_say_they_are_not_implemented(self):
        for command, (_help, milestone) in cli.COMMANDS.items():
            with self.subTest(command=command):
                result = run_entry(command)
                self.assertEqual(result.returncode, cli.EXIT_NOT_IMPLEMENTED, result.stderr)
                self.assertIn(f"planned for {milestone}", result.stderr)

    def test_commands_match_the_readme(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for command in cli.COMMANDS:
            self.assertIn(f"`openclaw-termux {command}", readme)

    def test_entry_point_ignores_pythonpath_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            rogue = Path(tmp) / "openclaw_termux"
            rogue.mkdir()
            (rogue / "__init__.py").write_text("raise SystemExit('rogue module imported')\n")
            result = subprocess.run(
                ["bash", str(ENTRY), "--version"],
                capture_output=True, text=True, cwd=tmp, env={**os.environ, "PYTHONPATH": tmp},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"openclaw-termux {__version__}")


if __name__ == "__main__":
    unittest.main()
