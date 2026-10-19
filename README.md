# openclaw-termux

A safe update and maintenance manager for [OpenClaw](https://openclaw.ai)
([GitHub](https://github.com/openclaw/openclaw)) running natively on Android under
[Termux](https://termux.dev) ([GitHub](https://github.com/termux/termux-app)).

> **Status: early development (milestone M1 of 4).** The repository holds the Android patch set,
> the CLI skeleton, the test harness and the [design](docs/design.md). The `install.sh` script and
> the `openclaw-termux` commands described below are the **planned v1 interface**. They are not
> implemented yet and currently exit with "not implemented yet".

## Introduction

OpenClaw runs well on an Android phone under Termux, but it needs Android-specific patches applied
to its installed npm package, and its built-in updater can take a working gateway down.
`openclaw-termux` replaces `openclaw update` on Termux with an update path that never touches the
live install until a fully patched, validated candidate exists:

1. Install the new version into a **staging** directory.
2. Apply and validate the **Android patch set** in staging.
3. **Snapshot** OpenClaw's state databases and config while the gateway is stopped.
4. **Swap** the staged package into place atomically, keeping the previous version.
5. Restart the gateway and **health-gate** it. If it does not become healthy, **roll back**
   automatically.

### Why the normal `openclaw update` fails on Termux

- **There is no real `systemd`.** Upstream OpenClaw installs and restarts its gateway through the
  host's service manager: `systemctl --user` on Linux and launchd on macOS. Android owns PID 1, and
  apps cannot run `systemd`. On Termux, services run under runit
  ([`termux-services`](https://wiki.termux.com/wiki/Termux-services), controlled with `sv`). Node
  also reports `process.platform` as `android`, not `linux`, so upstream's service code finds no
  usable service manager. The gateway install and restart steps that `openclaw update` relies on
  cannot work.
- **The update replaces the live package in place.** `openclaw update` runs `npm install -g` over
  the running installation. The running gateway notices that its installation was replaced and
  exits.
- **The reinstall discards the Android patches.** OpenClaw only runs on Android after patches to
  its `dist/` files. For example, SELinux denies `link(2)` and `FICLONE`, `/proc/net` is
  unreadable, and the f2fs filesystem has no file birth time. A fresh `npm install` brings back
  the unpatched code. If the gateway restarts before re-patching succeeds, the service supervisor
  keeps restarting unpatched code in a crash loop.

## Installation

Requirements:

- Termux from [F-Droid](https://f-droid.org/packages/com.termux/) or
  [GitHub releases](https://github.com/termux/termux-app/releases). The Google Play build is not
  supported.
- An existing OpenClaw installation managed by a runit service (`termux-services`).
- Packages: `pkg install git nodejs cmake clang patchelf sqlite termux-services`

Planned installation:

```sh
git clone https://github.com/octocore-autonomous-systems/openclaw-termux.git
cd openclaw-termux
./install.sh            # links openclaw-termux into ~/.local/bin and records what it installed
```

`./install.sh --uninstall` removes exactly what the installer added. The installer does not modify
your runit service definition.

## How to use

| Command                          | What it does                                                                                     |
| -------------------------------- | ------------------------------------------------------------------------------------------------ |
| `openclaw-termux status`         | Show the version, gateway state, patch status, latest snapshot and plugin versions. Read-only.   |
| `openclaw-termux check [VER]`    | Dry run: fetch a release into a scratch directory and check that every Android patch applies.    |
| `openclaw-termux update [VER]`   | Staged update to `VER` (default: latest), including plugins, with health gate and auto-rollback. |
| `openclaw-termux rollback`       | Restore the previous version, and the paired state snapshot if migrations ran since.             |
| `openclaw-termux snapshot [LBL]` | Back up OpenClaw's SQLite databases and config with the gateway stopped.                         |
| `openclaw-termux doctor`         | Snapshot, then run `openclaw doctor --fix` with no short timeout and verify the result.          |

A typical update:

```sh
openclaw-termux check     # will the patches apply to the latest release?
openclaw-termux update    # stage, patch, snapshot, swap, restart, health-gate
openclaw-termux status    # confirm the new version is healthy
```

Each command writes a log to `~/.local/state/openclaw-termux/logs/`, with secrets redacted.

### The Android patch set

[`patch/openclaw-patch-android`](patch/openclaw-patch-android) applies the Android patches to an
OpenClaw `dist/` tree. It knows 11 patch types: service, dashboard, fs-safe, native, loader, proc,
migrate, birth, owner, ancestor and lifecycle. It is content-addressed, idempotent and fail-closed:
a missing or duplicated code anchor aborts before anything is written. The manager runs it only
against staged trees, and only if its hash matches the pinned value:

```text
sha256  47522583f17ec9472a9065bb7874c03193e97699f94b120b7675a27821661661  patch/openclaw-patch-android
```

Changing the patch set means changing that file, this hash and `PATCHER_SHA256` in
[`lib/openclaw_termux/patcher.py`](lib/openclaw_termux/patcher.py) in one pull request. A test
fails otherwise.

## Contributing

Contributions are welcome. Please:

1. **Open an issue first** for anything larger than a small fix. Include your Android, Termux and
   OpenClaw versions, plus `openclaw-termux status` output with secrets removed.
2. **Work on a branch and open a pull request into `main`.** Nobody pushes directly to `main`.
3. **Keep CI green.** Every pull request must pass the checks in
   [`.github/workflows/ci.yml`](.github/workflows/ci.yml) before it is merged. Run the tests locally
   first. They use only the Python standard library, Node.js and Bash:

   ```sh
   python3 -m unittest discover -s tests -t .
   OPENCLAW_TERMUX_RELEASE=2026.10.4 python3 -m unittest tests.test_release   # needs npm and network
   OPENCLAW_TERMUX_RELEASE=2026.10.4 OPENCLAW_TERMUX_ANDROID_APPLY=1 \
     python3 -m unittest tests.test_android_apply                             # Termux only
   shellcheck bin/openclaw-termux patch/openclaw-patch-android
   ```

4. **Keep changes focused,** with a clear description of what changed and why. Changes to the
   Android patch set need a test against a real OpenClaw release.
5. **Never commit secrets,** tokens, API keys or personal OpenClaw config. CI runs a secret scan on
   every pull request.
6. **Send Android fixes upstream where you can.** A fix accepted upstream in OpenClaw lets the
   matching patch here be retired.

By submitting a contribution, you agree that it is licensed under the MPL-2.0 (see
[License](#license)).

## License

This project is licensed under the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/)
(MPL-2.0). See [`LICENSE`](LICENSE) for the full text.

OpenClaw and Termux are separate projects with their own licenses. This project is not affiliated
with or endorsed by either of them.
