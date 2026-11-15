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
