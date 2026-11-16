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

## Verified CI evidence for continuation PRs #68–#75

| PR | Head commit | Core result | Core CI link |
| --- | --- | --- | --- |
| #68 | `8aef48301a6d` | 600 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43749348883) |
| #69 | `c8d2b859b9ad` | 613 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43749688578) |
| #70 | `82a01dc3ec23` | 602 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43749934249) |
| #71 | `e8b7db8beef8` | 599 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43750327501) |
| #72 | `fb76d221381e` | 613 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43750536172) |
| #73 | `a1568cdcf248` | 600 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43750908801) |
| #74 | `e297f62a6bcc` | 601 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43751487746) |
| #75 | `67a6a57bc2e2` | 620 passed, 6 skipped; release lock PASS | [Actions](https://github.com/ArdaNTM/JAS/actions/runs/43751913526) |

All documented PR heads passed their Core Assurance workflow and release-lock verifier. Each has a separate Remote Persistence Integration workflow (successful at the time of this update). Test counts are **per isolated branch**, not cumulative; unmerged code from other branches is not in each run. No physical/hardware testing or production merge is inferred.

## Verified GitHub Actions — follow-up PRs #76–#83

Each entry records Core Assurance success, full pytest and Final Release Lock on the PR's independent head. These are **not cumulative test counts**.

| PR | Actions | Core result |
| --- | --- | --- |
| #76 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43752921155) | PASS |
| #77 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43753417472) | PASS |
| #78 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43753581818) | PASS |
| #79 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43753780847) | PASS |
| #80 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43754154784) | PASS |
| #81 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43754964413) | PASS |
| #82 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43755206129) | PASS |
| #83 | [Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/43755492865) | PASS |

Detailed observed counts: #77 606 passed/6 skipped, #79 602/6, #80 603/6, #81 603/6, #82 603/6, #83 610/6. #76 and #78 CI success verified; count omitted when not separately extracted.
No real physical hardware attestation, external API validity or production release is inferred.

## Verified Core Assurance — PRs #84–#86

| PR | Exact head | Full Core test result | Core actions |
| --- | --- | --- | --- |
| #84 | `6533e49a915b` | 606 passed, 6 skipped; Release Lock PASS | https://github.com/ArdaNTM/JAS/actions/runs/43756314062 |
| #85 | `923118435ca0` | 601 passed, 6 skipped; Release Lock PASS | https://github.com/ArdaNTM/JAS/actions/runs/43756823784 |
| #86 | `a4a156b42ae8` | 605 passed, 6 skipped; Release Lock PASS | https://github.com/ArdaNTM/JAS/actions/runs/43757162780 |

Remote Persistence PR workflows: #84 run 43756314100 PASS; #85 run 43756823780 PASS; #86 run 43757162764 PASS. These test counts are independent branches, NOT cumulative. No hardware/real-owner acceptance.

## PR #87 DOCX extraction verified on exact branch head

| PR | Head | Core Assurance | Remote Persistence |
| --- | --- | --- | --- |
| [#87](https://github.com/ArdaNTM/JAS/pull/87) | `97d39e6c5736` | [PASS 611 passed / 6 skipped; Final Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43765869144) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43765869141) |

Real DOCX input was created as in-memory OOXML fixtures; no production-host/file authorization or hardware acceptance was run. Benchmarks and test counts from independent PR branches are not additive.

## Verified GitHub Actions — PR #88 and #89

| PR | Exact head commit | Core result | Remote Persistence |
| --- | --- | --- | --- |
| [#88](https://github.com/ArdaNTM/JAS/pull/88) | `03657e6f9d67` | [614 passed, 6 skipped; Release Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43766456114) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43766456072) |
| [#89](https://github.com/ArdaNTM/JAS/pull/89) | `dc98aede3a37` | [605 passed, 6 skipped; Release Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43766833934) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43766833912) |

These are per-branch isolated runs; they are not additive. Static Python inspection does not execute user code or certify security. ICS parsing does not authenticate calendar providers or support recurring/TZID expansion.

## Verified current GitHub Actions — PRs #90–#92

| PR | Exact head commit | Core Assurance and Final Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#90](https://github.com/ArdaNTM/JAS/pull/90) | `3279fe5238f5` | [609 passed / 6 skipped, Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43767731030) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43767731049) |
| [#91](https://github.com/ArdaNTM/JAS/pull/91) | `e7b08362dad8` | [609 passed / 6 skipped, Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43767935571) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43767935585) |
| [#92](https://github.com/ArdaNTM/JAS/pull/92) | `bb650fa3cc6c` | [612 passed / 6 skipped, Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43768319906) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43768319983) |

Counts belong to separate PR branch runs and do not add up to a cumulative integrated test count. All remain PARTIAL and no production or physical verification is inferred.

## Verified GitHub Actions — PRs #93 and #94

| PR | Exact head | Full Core Assurance and Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#93](https://github.com/ArdaNTM/JAS/pull/93) | `4f51ca9976d3` | [602 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770040681) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770040680) |
| [#94](https://github.com/ArdaNTM/JAS/pull/94) | `4c4a63553188` | [607 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770389240) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770389219) |

Independent PR heads, not combined/cumulative or real-provider acceptance.

## Verified GitHub Actions — PR #95–#96

| PR | Exact head | Full Core Assurance and Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#95](https://github.com/ArdaNTM/JAS/pull/95) | `4963b5b85b8a` | [602 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770863374) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43770863380) |
| [#96](https://github.com/ArdaNTM/JAS/pull/96) | `5721ec91e06b` | [607 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43771211785) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43771211803) |

These independent CI executions are not combined; no hardware, Owner or signed audit acceptance is inferred.

## PR #97 exact-head CI evidence

| PR | Commit | Core Assurance | Remote Persistence |
| --- | --- | --- | --- |
| [#97](https://github.com/ArdaNTM/JAS/pull/97) | `1e2980c16457` | [608 passed / 6 skipped; Release Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43771769354) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43771769447) |

No distributed task execution, Owner approval, real hardware or actual goal achievement is inferred.

## Verified exact-head CI — PRs #98–#101

| PR | Exact head | Core Assurance + Final Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#98](https://github.com/ArdaNTM/JAS/pull/98) | `f77b68f25c16` | [607 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774000863) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774000872) |
| [#99](https://github.com/ArdaNTM/JAS/pull/99) | `6a089da47024` | [606 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774156154) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774156162) |
| [#100](https://github.com/ArdaNTM/JAS/pull/100) | `1c04ffb4bc58` | [617 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774460559) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774460548) |
| [#101](https://github.com/ArdaNTM/JAS/pull/101) | `a01f8512232b` | [606 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774776859) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43774776881) |

Each branch is tested separately against old main; counts are not cumulative or integrated. There is no real Owner, model, signed execution, lab or hardware acceptance.

## Latest exact-head verified GitHub Actions — PR #102–#104

| PR | Head | Core Assurance / Final Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#102](https://github.com/ArdaNTM/JAS/pull/102) | `0c65a0409616` | [605 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43775435288) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43775435294) |
| [#103](https://github.com/ArdaNTM/JAS/pull/103) | `e5f4432142d0` | [605 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43775656063) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43775656036) |
| [#104](https://github.com/ArdaNTM/JAS/pull/104) | `1c3a201ba4db` | [615 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43776008643) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43776008617) |

The runs are independent branch checks, not an integrated combined acceptance.

## PR #105 independently verified exact-head CI

| PR | Commit | Core Assurance + Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#105](https://github.com/ArdaNTM/JAS/pull/105) | `6fa9f155a757` | [603 passed, 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43776433513) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43776433459) |

Registry health-state unit integration is not a signed Owner or real-world agent acceptance.

## PR #106 exact-head CI — independent audit checkpoint partial

| PR | Commit | Core Assurance + Final Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#106](https://github.com/ArdaNTM/JAS/pull/106) | `a145504a3ce80b496333169bb393b3ed42b1848b` | [599 passed, 6 skipped; Release Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43778641345) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43778641265) |

Negative security tests: wrong signing key/scope, forged checkpoint MAC, record tampering, re-chaining, rollback/truncation, invalid input. Local isolated harness 7 passed. This is a separate branch, **not** cumulative integration or independent external signer acceptance. Production custody and WORM tests remain missing.
