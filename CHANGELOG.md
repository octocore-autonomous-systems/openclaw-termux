# Changelog

All notable changes to this project are documented here. Version 1 has no tagged releases.

## Unreleased

### Added

- Design document for v1 ([docs/design.md](docs/design.md)): paths, command surface and exit codes,
  staged update, health gate, rollback, snapshots and state pairing, doctor, and testing.
- The Android patch set `patch/openclaw-patch-android`, moved in byte-for-byte (sha256
  `47522583f17ec9472a9065bb7874c03193e97699f94b120b7675a27821661661`), with a verifying wrapper that
  refuses to run a modified copy.
- CLI skeleton `bin/openclaw-termux`. Every command currently reports "not implemented yet".
- Fake-prefix test harness: stub `sv`, `openclaw` and `npm` over a synthetic OpenClaw package that
  carries the patcher's real anchors.
- Tests: patcher integrity, check, apply, idempotency and fail-closed behaviour, CLI, harness, an
  opt-in check against a real OpenClaw release, and a Termux-only test that applies the full patch
  set, including the native relink, to a staged copy of a real release.
- CI: shellcheck, unit and fake-prefix tests, and the real-release patch check, alongside the existing
  secret scan, Markdown lint and LICENSE check.
- README, MPL-2.0 `LICENSE`.
