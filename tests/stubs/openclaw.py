"""Fake OpenClaw CLI for openclaw-termux tests.

Installed as each fake package's ``openclaw.mjs`` (``$PREFIX/bin/openclaw`` links to it, as on a real
Termux install), so ``--version`` reports the version of the package it belongs to. Gateway state
comes from the fake ``sv`` state; behaviour is steered by the ``openclaw`` section of
``.fake/control.json``:

- ``ready_after_polls``: health and status polls needed after a start before the gateway is ready.
- ``never_ready``: the gateway never becomes healthy.
- ``exit``: ``{"<command words>": exit_code}``, for example ``{"config validate": 1}``.
"""

import json
import os
import sys
import time

ROOT = os.environ["OPENCLAW_TERMUX_FAKE_ROOT"]
FAKE = os.path.join(ROOT, ".fake")
PACKAGE = os.path.dirname(os.path.realpath(__file__))
SERVICE_STATE = os.path.join(FAKE, "sv", "openclaw-gateway.json")


def log_call(argv):
    with open(os.path.join(FAKE, "calls.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"tool": "openclaw", "argv": argv, "package": PACKAGE, "time": time.time()}) + "\n")


def control():
    try:
        with open(os.path.join(FAKE, "control.json"), encoding="utf-8") as f:
            return json.load(f).get("openclaw", {})
    except FileNotFoundError:
        return {}


def package_version():
    with open(os.path.join(PACKAGE, "package.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def poll_gateway(settings):
    """Count one health poll and report (running, reachable, state)."""
    try:
        with open(SERVICE_STATE, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        return False, False, {}
    running = state.get("state") == "up"
    if running:
        state["polls"] = state.get("polls", 0) + 1
        with open(SERVICE_STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    ready = (
        running
        and not settings.get("never_ready")
        and state.get("polls", 0) > settings.get("ready_after_polls", 0)
    )
    return running, ready, state


def words(argv):
    return [a for a in argv if not a.startswith("-")][:2]


def main(argv):
    log_call(argv)
    settings = control()
    key = " ".join(words(argv))
    code = settings.get("exit", {}).get(key)
    if argv == ["--version"]:
        print(f"OpenClaw {package_version()} (fake)")
        return 0
    if code:
        print(f"fake openclaw: '{key}' failed", file=sys.stderr)
        return int(code)
    if key == "status":
        running, ready, state = poll_gateway(settings)
        status = {
            "runtimeVersion": state.get("running_version") if ready else None,
            "pid": state.get("pid") if running else None,
            "gateway": {
                "mode": "local",
                "reachable": ready,
                "error": None if ready else "connect ECONNREFUSED 127.0.0.1:18789",
            },
            "gatewayService": {
                "label": "runit/sv",
                "installed": True,
                "loaded": True,
                "runtime": {"status": "running" if running else "stopped", "pid": state.get("pid")},
            },
        }
        print(json.dumps(status) if "--json" in argv else f"gateway reachable: {ready}")
        return 0
    if key == "health":
        _running, ready, _state = poll_gateway(settings)
        if not ready:
            print("gateway closed (1006): connect ECONNREFUSED 127.0.0.1:18789", file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "ts": int(time.time() * 1000)}) if "--json" in argv else "OK")
        return 0
    if key == "models list":
        print("[]" if "--json" in argv else "no models")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
