# AURA test report — Phase 0

- Intended test command: `cd core && uv run pytest -q tests/test_feature_tracker_validation.py`.
- Intended CI: `AURA Core Assurance` (PR touching `core/tests/**`), which also executes the complete Core suite and release lock verifier.
- Status at initial commit: **PENDING**, not PASS. CI outcomes and local evidence must be recorded by a later reviewed commit or PR update.
- Hardware, voice, external services and OSWorld live benchmark: **NOT RUN** in this PR.

## Verified GitHub Actions — PR #65

- [AURA Core Assurance PR run](https://github.com/ArdaNTM/JAS/actions/runs/43745529567): **success** (initial commit).
- [Remote Persistence Integration PR run](https://github.com/ArdaNTM/JAS/actions/runs/43745529502): **success** (initial commit).
- The new schema extension above changes the validator and tests; its latest commit requires a **fresh CI run**. Previous green results do not automatically validate later commits.
- [Feature #8 PR #66 Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43746019527): **success**, 600 passed / 6 skipped, release-lock PASS. This is branch-specific evidence and does not merge #66 into #65 or main.

## Updated evidence — 2026-11-15

- PR #65 expanded tracker (previous commit `93222c7`): [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43746384078) PASS — **601 passed, 6 skipped**, Release Lock PASS; [Persistence Integration](https://github.com/ArdaNTM/JAS/actions/runs/43746384109) PASS.
- PR #66 latest exact-principal-scope fix `028a293`: [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43746729604) PASS — **601 passed, 6 skipped**, Release Lock PASS; [Persistence Integration](https://github.com/ArdaNTM/JAS/actions/runs/43746729566) PASS.
- The present new hardening commit updates the validator; its CI must complete before claiming a green final head.

## CI tracker gate and new telemetry candidate

- Added `python ../scripts/validate_aura_feature_tracker.py` to Core Assurance CI; documentation and validator edits now trigger the workflow.
- PR #67 disk telemetry feature is in test; do not claim real-hardware PASS from synthetic psutil probes.

## Verified telemetry feature CI

- [PR #67 AURA Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43747432323): **success** — 605 passed, 6 skipped; release lock `sha256:8e6d62146366aaf0416e2ef8fa3696289c54c713b16ff11b7a98548da60b6484` PASS.
- [PR #67 Remote Persistence Integration](https://github.com/ArdaNTM/JAS/actions/runs/43747432309): **success**.
- No physical-host disk accuracy test, system service activation, or production rollout in PR #67.
