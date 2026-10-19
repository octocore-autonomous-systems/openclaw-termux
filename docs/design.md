# openclaw-termux design

Status: **accepted for v1** (milestone M1). This document is the contract that the M2 to M4 code is
written and tested against. Change it by pull request before changing behaviour.

## 1. Goals and non-goals

Goals:

- Never modify the live OpenClaw package until a fully patched and validated candidate exists.
- Swap packages with `rename(2)` on one filesystem, keeping exactly one previous version.
- Snapshot OpenClaw's state before anything that can migrate it, and pair each package version with
  the snapshot that matches it.
- Health-gate every restart and roll back automatically, in seconds, when the gate fails.
- Own the Android patch set (`patch/openclaw-patch-android`) and run it only against staged trees.

Non-goals for v1:

- Installing, rewriting or replacing the gateway's runit service. The manager only drives it with
  `sv`, and never runs `openclaw gateway install`.
- Tagged releases, auto-publishing or a release runbook.
- Platforms other than Termux on Android (arm64).

## 2. Paths

| Name          | Path                                                       | Notes                                                     |
| ------------- | ---------------------------------------------------------- | --------------------------------------------------------- |
| Live package  | `$PREFIX/lib/node_modules/openclaw`                        | `$PREFIX/bin/openclaw` links to its `openclaw.mjs`        |
| Manager root  | `$PREFIX/lib/node_modules/.openclaw-termux/`               | Same filesystem as the live package, so swaps are renames |
| Staging       | `<manager root>/staging/<version>/`                        | An `npm install -g --prefix` target                       |
| Previous      | `<manager root>/previous/<version>/`                       | Exactly one entry after a successful update               |
| Failed        | `<manager root>/failed/<version>-<timestamp>/`             | Kept for inspection after a failed rollback               |
| Service       | `$PREFIX/var/service/openclaw-gateway/`                    | Read-only to the manager apart from `sv` commands         |
| State         | `~/.local/state/openclaw-termux/{lock,logs/,receipts/}`    | Logs and receipts named `<YYYYmmdd_HHMMSS>.<command>.*`   |
| Host config   | `~/.config/openclaw-termux/config.json`                    | Host-specific expectations (§ 9); never in this repo      |
| Snapshots     | `~/.openclaw/backups/pre-openclaw-<op>-<YYYYmmdd_HHMMSS>/` | Same convention as earlier manual upgrades                |
| Patch backups | `~/.cache/openclaw-patch-android/backups/<version>/`       | The patcher's own convention, kept unchanged              |

Scratch space comes from `$TMPDIR` (Termux: `$PREFIX/tmp`), never `/tmp`.

## 3. Command surface and exit codes

| Command            | Gateway                  | Summary                                                                                                   |
| ------------------ | ------------------------ | --------------------------------------------------------------------------------------------------------- |
| `status`           | untouched                | Versions, gateway state and PID, patch status, previous version, latest snapshot, plugins, pending update |
| `check [VERSION]`  | untouched                | Stage the release in scratch space and run the patcher's `--check`                                        |
| `snapshot [LABEL]` | stopped, then restarted  | Stops the gateway, or with `--stopped` refuses unless it is already down                                  |
| `update [VERSION]` | restarted once           | § 4                                                                                                       |
| `rollback`         | restarted once           | § 6                                                                                                       |
| `doctor`           | stopped; doctor restarts | § 8                                                                                                       |

| Exit | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| 0    | Success                                                                                 |
| 1    | Failed before any change to the live install; nothing to undo                           |
| 2    | Usage error                                                                             |
| 3    | Not implemented in this version                                                         |
| 4    | Refused: a precondition failed (lock held, unknown leftover state, preflight)           |
| 5    | `update` failed after the swap and the automatic rollback succeeded                     |
| 6    | A rollback failed; the gateway may be down. Reported loudly; the `failed/` tree is kept |

Every command writes `~/.local/state/openclaw-termux/logs/<YYYYmmdd_HHMMSS>.<command>.log`, with ANSI
escapes stripped. Secrets are never printed: subprocess output passes through a redactor for tokens,
keys and `Authorization` headers before it reaches the log or the terminal.

## 4. Staged update

Only one mutating command runs at a time: `update`, `rollback`, `snapshot` and `doctor` take an
exclusive `flock` on `~/.local/state/openclaw-termux/lock` and exit 4 if it is held.

1. **Preflight.**
   - `cmake`, `patchelf`, `clang`, `sv` and `node` must be on `PATH`.
   - The service directory must exist, and its `run` and `log/run` must match the host config hashes.
   - The package filesystem needs at least 3× the live package size free.
   - The manager root must hold no `staging/` entry from an unfinished run. A leftover with a
     `phase: staged` receipt is deleted and the run continues; anything else exits 4.
   - The manager verifies the vendored patcher's sha256 before it runs it.
2. **Resolve.** `npm view openclaw@<VERSION or latest> version`. The same version is allowed, and it
   is how the live cycle test runs.
3. **Stage.** Run
   `npm install -g openclaw@<v> --prefix <staging> --force --os linux --cpu arm64 --nodedir=$PREFIX`
   with the inherited environment. Never set a bare-name `LD_PRELOAD`.
4. **Patch and validate in staging.**
   - Run `openclaw-patch-android --dist <staged>/dist --backup-dir <patch backups>/<v>`, then
     `--check`, which must exit 0.
   - `node --check` every file the patcher touched.
   - From the staged tree, `openclaw --version` must equal `<v>`, and `config validate` and
     `models list --json` must exit 0.
   - Any failure here exits 1. The live install has not been touched.
5. **Snapshot** (§ 7).
   - `sv -w 60 down openclaw-gateway` and confirm `down:`.
   - Take a snapshot labelled `update`.
   - Assume migrations may run whenever the version changes, and record that assumption.
6. **Swap.** Two renames:
   - Live package → `previous/<old>`. Any older `previous/` entry is deleted first.
   - `staging/<v>/lib/node_modules/openclaw` → live package.
   - Then `$PREFIX/bin/openclaw` must resolve into the new tree.
   - The receipt's `phase` is written before and after each rename, so an interrupted swap can be
     recognized and finished or reverted on the next run.
7. **Plugins.** `openclaw plugins update --all --dry-run`, then `openclaw plugins update --all`, run
   from the new tree. A plugin failure triggers rollback, like a failed health gate.
8. **Start and health-gate** (§ 5). If the gate fails, roll back automatically (§ 6) and exit 5 or 6.
9. **Record.** Write the receipt (§ 7.2), print a one-screen summary and remove `staging/<v>`.

## 5. Health gate

After `sv -w 60 up`, poll every 5 s until **ready** or until 180 s have passed. A cold start on a phone
takes 70 to 90 s.

**Ready** means all of the following:

- `openclaw health --json` exits 0 with `"ok": true`.
- `openclaw status --json` reports `gateway.reachable: true`.
- `status --json` reports `runtimeVersion` equal to the target version. That proves the restarted
  process runs the new code.

**Crash loop** means the PID in `sv status` changes two or more times inside the window. The gate fails
immediately and does not wait out the timeout.

The gate never sends signals or restarts the service itself; the caller decides what happens on failure.

## 6. Rollback

1. Refuse with exit 4 if `previous/` is empty.
2. `sv -w 60 down` and confirm `down:`.
3. If the receipt for the live version says migrations may have run since the paired snapshot, take
   a fresh safety snapshot labelled `rollback`. Then restore the four databases and `openclaw.json`
   from the paired snapshot, and check each with `PRAGMA integrity_check`.
4. Rename the live package to `failed/<version>-<timestamp>`, then rename `previous/<old>` to the live
   package.
5. `sv -w 60 up` and health-gate against `<old>`.
6. A failed rollback is reported loudly, exits 6 and leaves `failed/` in place. It never loops.

## 7. Snapshots and state pairing

### 7.1 Snapshot

A snapshot is taken only while the gateway is stopped. `openclaw backup create` cannot be used on
Android, because it fails on `link(2)`.

- **Databases:** `~/.openclaw/state/openclaw.sqlite` and
  `~/.openclaw/agents/{proving-ground,main,openclaw}/agent/openclaw-agent.sqlite`. Each is copied
  with SQLite's online backup API, the same mechanism as the `sqlite3 .backup` command, through
  Python's `sqlite3.Connection.backup`. Each copy must pass `PRAGMA integrity_check`. The agent list
  is discovered from `~/.openclaw/agents/*/agent/openclaw-agent.sqlite`, not hardcoded.
- **Config:** `~/.openclaw/openclaw.json`.
- **Manifest:** `manifest.json` with the package version, plugin versions, sha256 of every file,
  and the operation.

### 7.2 Receipt

Every mutating command writes a receipt in `receipts/`:

```json
{
  "schema": "openclaw-termux.receipt.v1",
  "command": "update",
  "phase": "completed",
  "outcome": "success",
  "from_version": "2026.10.3",
  "to_version": "2026.10.4",
  "snapshot": "~/.openclaw/backups/pre-openclaw-update-20261018_201500",
  "migrations_may_have_run": true,
  "patcher_sha256": "<sha256>",
  "timings_s": {"stage": 0, "patch": 0, "down": 0, "swap": 0, "plugins": 0, "health": 0},
  "log": "~/.local/state/openclaw-termux/logs/20261018_201500.update.log"
}
```

`phase` moves through `preflight`, `staged`, `patched`, `stopped`, `snapshotted`, `swapping`,
`swapped`, `plugins`, `starting` and `completed`, or ends in `rolled-back` or `failed`.

**Pairing rule:** the receipt that installed version *N* names the snapshot taken just before *N*
replaced *N−1*. Rolling back from *N* restores that snapshot whenever `migrations_may_have_run` is
true. `doctor` and plugin updates set that flag too.

## 8. Doctor

1. Take a snapshot labelled `doctor`, and keep the gateway stopped.
2. Run `openclaw doctor --fix` with **no** short timeout; it has taken about 17 minutes. Doctor
   refuses with `OpenClawAgentDatabaseLeaseActiveError` while the gateway holds an agent database,
   which is why the gateway must be stopped.
3. Doctor starts the gateway itself through the runit entry. Then run the health gate,
   `PRAGMA quick_check` on each database and the patcher's `--check`.

## 9. Host config

`~/.config/openclaw-termux/config.json` holds host-specific expectations that must not live in a public
repo: the sha256 of the service's `run` and `log/run`, and any extra agents. Preflight refuses to
continue when the files on disk do not match. The manager never rewrites the service to "fix" a
mismatch.

## 10. Patcher ownership

`patch/openclaw-patch-android` is vendored byte-for-byte. Its sha256 is pinned in
`lib/openclaw_termux/patcher.py` and the README, and both are asserted by tests. The manager:

- refuses to run a patcher whose hash differs;
- runs it through `bash`, so its Termux-absolute shebang never matters;
- passes `--dist` pointing at a **staged** tree only, never at the live package;
- reads its `--check` exit status: 0 means all applied, 1 means some needed, 2 means an error, and a
  missing or duplicated anchor counts as an error;
- treats an anchor that disappears because an upstream fix landed as a patcher change. That change
  arrives through a reviewed PR that updates the pinned hash, never silently.

## 11. Testing

| Layer         | Runs on       | What it covers                                                                                                                                           |
| ------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit          | CI and Termux | Version resolution, receipt parsing, pairing and health-gate decisions                                                                                   |
| Fake prefix   | CI and Termux | `tests/fakeprefix.py`: stub `sv`, `openclaw` and `npm` over a fake package that carries the real patcher anchors. The real patcher checks and applies it |
| Real release  | CI (opt-in)   | `OPENCLAW_TERMUX_RELEASE=<v>`: the patcher's `--check` against the published release, including fail-closed edits                                        |
| Android apply | Termux only   | Applying the full patch set, including the native relink, to a staged real release                                                                       |
| Live cycle    | A real device | `update 2026.10.4` → `rollback` → `update 2026.10.4`. The snapshot comes first and the operator is told before each restart                              |

The fake-prefix scenarios M3 must cover:

- an update that succeeds;
- a patch failure before the swap, with the live package byte-identical afterwards;
- a health-gate timeout with automatic rollback;
- a crash loop with automatic rollback;
- a rollback with state restore;
- an interrupted swap recovered on the next run.

## 12. Open questions

- Should `check` also run on a schedule in CI against `latest`? W3's anchor-watch service covers this
  on the device; a CI schedule would add early warning without blocking pull requests.
