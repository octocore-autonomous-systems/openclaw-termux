"""Fake ``npm`` for openclaw-termux tests.

Serves package trees from ``$OPENCLAW_TERMUX_FAKE_ROOT/.fake/releases/<version>/``. Like the real
``npm install -g``, ``install`` replaces the target package directory in place. Behaviour is steered
by the ``npm`` section of ``.fake/control.json``:

- ``latest``: the version ``npm view openclaw version`` reports (default: highest release).
- ``install_exit``: make ``install`` fail before it touches anything.
"""

import json
import os
import shutil
import sys
import tarfile
import time

ROOT = os.environ["OPENCLAW_TERMUX_FAKE_ROOT"]
FAKE = os.path.join(ROOT, ".fake")
RELEASES = os.path.join(FAKE, "releases")


def log_call(argv):
    with open(os.path.join(FAKE, "calls.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"tool": "npm", "argv": argv, "time": time.time()}) + "\n")


def control():
    try:
        with open(os.path.join(FAKE, "control.json"), encoding="utf-8") as f:
            return json.load(f).get("npm", {})
    except FileNotFoundError:
        return {}


def version_key(version):
    return tuple(int(p) if p.isdigit() else p for p in version.replace("-", ".").split("."))


def releases():
    return sorted(os.listdir(RELEASES), key=version_key) if os.path.isdir(RELEASES) else []


def resolve(spec, settings):
    name, _, version = spec.partition("@")
    if name != "openclaw":
        return None
    if not version or version == "latest":
        return settings.get("latest") or (releases()[-1] if releases() else None)
    return version if version in releases() else None


def option(argv, name):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else None
    for arg in argv:
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return None


def positional(argv):
    out, skip = [], False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("--prefix", "--pack-destination", "--os", "--cpu", "--nodedir"):
            skip = True
            continue
        if not arg.startswith("-"):
            out.append(arg)
    return out


def main(argv):
    log_call(argv)
    settings = control()
    args = positional(argv)
    if not args:
        return 0
    command, rest = args[0], args[1:]
    if command == "view" and rest:
        version = resolve(rest[0], settings)
        if version is None:
            print(f"npm error code E404\nnpm error 404 '{rest[0]}' is not in this registry.", file=sys.stderr)
            return 1
        print(version)
        return 0
    if command in ("install", "i") and rest:
        if settings.get("install_exit"):
            print("npm error fake install failure", file=sys.stderr)
            return int(settings["install_exit"])
        version = resolve(rest[0], settings)
        if version is None:
            print(f"npm error code ETARGET\nnpm error No matching version found for {rest[0]}.", file=sys.stderr)
            return 1
        prefix = option(argv, "--prefix") or os.environ["PREFIX"]
        target = os.path.join(prefix, "lib", "node_modules", "openclaw")
        if os.path.lexists(target):
            shutil.rmtree(target)
        shutil.copytree(os.path.join(RELEASES, version), target, symlinks=True)
        os.makedirs(os.path.join(prefix, "bin"), exist_ok=True)
        link = os.path.join(prefix, "bin", "openclaw")
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink("../lib/node_modules/openclaw/openclaw.mjs", link)
        print(f"added 1 package (openclaw@{version}) in 1s")
        return 0
    if command == "pack" and rest:
        version = resolve(rest[0], settings)
        if version is None:
            print(f"npm error code E404\nnpm error 404 '{rest[0]}' is not in this registry.", file=sys.stderr)
            return 1
        dest = option(argv, "--pack-destination") or os.getcwd()
        name = f"openclaw-{version}.tgz"
        with tarfile.open(os.path.join(dest, name), "w:gz") as tar:
            tar.add(os.path.join(RELEASES, version), arcname="package")
        print(name)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
