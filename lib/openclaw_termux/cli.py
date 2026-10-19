"""Command-line interface. Commands land milestone by milestone; see docs/design.md."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3

# command -> (one-line help, milestone that implements it)
COMMANDS = {
    "status": ("show version, gateway, patch, snapshot and plugin state (read-only)", "M2"),
    "check": ("dry run: check that the Android patches apply to a release", "M2"),
    "snapshot": ("back up OpenClaw's databases and config with the gateway stopped", "M2"),
    "update": ("staged update with health gate and automatic rollback", "M3"),
    "rollback": ("restore the previous version and its paired state snapshot", "M3"),
    "doctor": ("snapshot, then run openclaw doctor --fix and verify the result", "M4"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openclaw-termux",
        description="Safe update and maintenance manager for OpenClaw on Termux.",
    )
    parser.add_argument("--version", action="version", version=f"openclaw-termux {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, (help_text, _milestone) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text, description=help_text)
        if name in ("check", "update"):
            cmd.add_argument("version", nargs="?", metavar="VERSION", help="OpenClaw version (default: latest)")
        elif name == "snapshot":
            cmd.add_argument("label", nargs="?", metavar="LABEL", help="label added to the snapshot name")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return EXIT_USAGE
    milestone = COMMANDS[args.command][1]
    print(
        f"openclaw-termux: '{args.command}' is not implemented yet (planned for {milestone}).",
        file=sys.stderr,
    )
    return EXIT_NOT_IMPLEMENTED
