"""Fake runit ``sv`` for openclaw-termux tests.

Installed into a fake prefix by ``tests/fakeprefix.py``. Service state lives in
``$OPENCLAW_TERMUX_FAKE_ROOT/.fake/sv/<service>.json``; behaviour is steered by the ``sv`` section of
``.fake/control.json``:

- ``crash_loop``: while up, every ``status`` reports a new pid, as runit does for a crashing service.
- ``fail``: ``{"<command>": exit_code}`` makes that command fail.

Starting the service records the installed package version as ``running_version``: the gateway runs
the code that was on disk when it started, not whatever is installed later.
"""

import json
import os
import sys
import time

ROOT = os.environ["OPENCLAW_TERMUX_FAKE_ROOT"]
FAKE = os.path.join(ROOT, ".fake")
PREFIX = os.environ["PREFIX"]


def log_call(argv):
    with open(os.path.join(FAKE, "calls.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"tool": "sv", "argv": argv, "time": time.time()}) + "\n")


def control():
    try:
        with open(os.path.join(FAKE, "control.json"), encoding="utf-8") as f:
            return json.load(f).get("sv", {})
    except FileNotFoundError:
        return {}


def state_path(service_dir):
    return os.path.join(FAKE, "sv", os.path.basename(service_dir.rstrip("/")) + ".json")


def load_state(service_dir):
    try:
        with open(state_path(service_dir), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"state": "down", "since": time.time(), "pid": None, "starts": 0, "next_pid": 1000}


def save_state(service_dir, state):
    os.makedirs(os.path.dirname(state_path(service_dir)), exist_ok=True)
    with open(state_path(service_dir), "w", encoding="utf-8") as f:
        json.dump(state, f)


def installed_version():
    try:
        with open(os.path.join(PREFIX, "lib", "node_modules", "openclaw", "package.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return None


def start(state):
    state.update(
        state="up",
        pid=state["next_pid"],
        next_pid=state["next_pid"] + 1,
        since=time.time(),
        starts=state["starts"] + 1,
        polls=0,
        running_version=installed_version(),
    )


def describe(service_dir, state):
    age = int(time.time() - state["since"])
    log = "run: log: (pid 999) 100s"
    if state["state"] == "up":
        return f"run: {service_dir}: (pid {state['pid']}) {age}s; {log}"
    return f"down: {service_dir}: {age}s, normally up; {log}"


def main(argv):
    log_call(argv)
    if argv[:1] == ["-w"]:
        argv = argv[2:]
    if len(argv) != 2:
        print("usage: sv [-w sec] command service", file=sys.stderr)
        return 1
    command, service_dir = argv
    if not os.path.isfile(os.path.join(service_dir, "run")):
        print(f"fail: {service_dir}: unable to change to service directory: file does not exist")
        return 1
    settings = control()
    failure = settings.get("fail", {}).get(command)
    if failure:
        print(f"timeout: {describe(service_dir, load_state(service_dir))}")
        return int(failure)
    state = load_state(service_dir)
    if command == "status":
        if state["state"] == "up" and settings.get("crash_loop"):
            start(state)
    elif command in ("up", "start", "u"):
        if state["state"] != "up":
            start(state)
    elif command in ("restart", "t"):
        start(state)
    elif command in ("down", "stop", "d"):
        state.update(state="down", pid=None, since=time.time())
    else:
        print(f"sv: unsupported command in fake: {command}", file=sys.stderr)
        return 1
    save_state(service_dir, state)
    prefix = "" if command == "status" else "ok: "
    print(prefix + describe(service_dir, state))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
