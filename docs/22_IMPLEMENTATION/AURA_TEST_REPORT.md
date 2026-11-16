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

## Exact-head independent CI evidence — PR #107–#108

| PR | Head | Core Assurance + Release Lock | Remote Persistence |
| --- | --- | --- | --- |
| [#107](https://github.com/ArdaNTM/JAS/pull/107) | `02f0ab2f2421` | [600 passed, 6 skipped; lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43779626496) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43779626363) |
| [#108](https://github.com/ArdaNTM/JAS/pull/108) | `46b1660bc95f` | [598 passed, 6 skipped; lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43780300467) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43780300516) |

#107 isolated local 8-pass + openpyxl load validation is not CI. #108 Core tests include real PermissionEngine and registry, approval store, FastAPI TestClient checks. These runs are isolated branches, not cumulative acceptance or proof of trustworthy Owner identity.

## PR #109–#110 exact-head evidence

| PR | Head | Core and Final Release Lock | Persistence |
| --- | --- | --- | --- |
| [#109](https://github.com/ArdaNTM/JAS/pull/109) | `da5e2948079c` | [601 passed, 6 skipped; lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43781476118) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43781476157) |
| [#110](https://github.com/ArdaNTM/JAS/pull/110) | `019b62e327b2` | [605 passed, 6 skipped; lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43781719023) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43781719040) |

#109 initial head failed manifest byte digest (subsequently corrected); final CI PASS. #110 tests use a fake process, not real Docker; no physical isolation claims. Independent PR-head passes are not merged acceptance.

## PR #111 final-head multi-platform proof (feature #18 partial)

| Exact head | Core and source lock | Persistence | Windows launcher |
| --- | --- | --- | --- |
| [#111 / `595215246cf6`](https://github.com/ArdaNTM/JAS/pull/111) | [618 passed, 6 skipped; lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43782633134) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43782633127) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43782633130) |

Earlier head Core failed two MCP v2 test model naming assertions; fixed in the final head. Tests use fake KPipeline and fake soundfile; no hardware model synthesis claim. Release lock includes both guard and executable provider script.

## PR #112 + dependent PR #114 exact-head proof

| PR | Head | Core and Final Release Lock | Persistence | Merge dependency |
| --- | --- | --- | --- | --- |
| [#112](https://github.com/ArdaNTM/JAS/pull/112) | `dcc4efd85446` | [618 passed 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43783579312) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43783579268) | main baseline, Owner review |
| [#114](https://github.com/ArdaNTM/JAS/pull/114) | `e8e971ff4909` | [628 passed 6 skipped; Lock PASS](https://github.com/ArdaNTM/JAS/actions/runs/43784049881) | [PASS](https://github.com/ArdaNTM/JAS/actions/runs/43784049895) | stacked on #112, Owner review |

Fake provider/Gateway test fixture is not real SearXNG/web proof; per-query authorization is tested with real JAS registries and PermissionEngine. #114 dossier always flags untrusted evidence and requires human review.

## PR #116 and #117 exact-head CI
| PR | Core Assurance | Final Release Lock | Persistence |
|---|---|---|---|
| #116 (2020122bd0e2) | 598 passed, 6 skipped (run 43785154055) | PASS | PASS (43785154014) |
| #117 (f9ea0abb2cf1) | 602 passed, 6 skipped (run 43785548012) | PASS | PASS (43785547988) |
Sources: https://github.com/ArdaNTM/JAS/actions/runs/43785154055 and https://github.com/ArdaNTM/JAS/actions/runs/43785548012
Runs are isolated PR head checks, not merged integration or production/hardware acceptance.

## PR #118 and #119 exact-head CI evidence
| PR | Core Assurance | Release Lock | Remote Persistence |
|---|---|---|---|
| #118 (cd1a98e195d5) | 605 passed, 6 skipped (run 43786822015) | PASS sha256:021868bed33dbb9bf75a8c9fcb0de675b288c049b894aa50d43cdc66c521051a | PASS (43786822032) |
| #119 (2cace2cc4927) | 619 passed, 6 skipped (run 43787305752) | PASS sha256:713f7063f04f322f8ecafc9a5a3ddcb60504dab7bf3f7a1e57015343a5fba3ea | PASS (43787305867) |
Run URLs: https://github.com/ArdaNTM/JAS/actions/runs/43786822015 and https://github.com/ArdaNTM/JAS/actions/runs/43787305752
Neither run establishes hardware/Owner acceptance. #119 is stacked on unmerged #117.

## Exact-head PR #120 Core and Release Lock
PR #120 head 74aa91567bc561f3c884c19e3d6b00336e42f976 Core Assurance [run 43788402100](https://github.com/ArdaNTM/JAS/actions/runs/43788402100) 597 passed / 6 skipped, Release Lock PASS sha256:5258fbba7743aee83f74de39661cba4c2b2a7965f05770a916a3c4575bf596ca; Remote Persistence [run 43788402101](https://github.com/ArdaNTM/JAS/actions/runs/43788402101) PASS. Async fake-recognizer/player race fixtures, not real audio hardware proof.

## PR #121/#122 independent exact-head Core and release lock
| PR | HEAD | Core Assurance | Final Lock | Other CI |
|---|---|---|---|---|
| #121 | 59be3ffc0fb0 | 620 passed, 6 skipped (43788533848) | PASS | Persistence PASS (43788533895) |
| #122 | 5224ac9f97d3 | 616 passed, 6 skipped (43788947660) | PASS | Persistence PASS (43788947692); Windows launcher PASS (43788947683) |
Evidence: https://github.com/ArdaNTM/JAS/actions/runs/43788533848 and https://github.com/ArdaNTM/JAS/actions/runs/43788947660. Neither CI run tests actual microphones/model files or combined PR integration.

## PR #123–#126 exact-head independent evidence
- PR #124 HEAD 58c1b6bef2cf21ff2ef362b6a1a1760e2b1c8011: feature #20 PARTIAL; Core 618 passed/6 skipped, Final Release Lock PASS, Persistence PASS; No actual environmental sound model, hardware microphone/consent UI or production wiring. https://github.com/ArdaNTM/JAS/actions/runs/43789297469
- PR #125 HEAD 52e9bba04363c8f1f76ad3374866a9d9af85fbac: feature #28 PARTIAL; Core 622 passed/6 skipped, Final Release Lock PASS, Persistence PASS; No real Electron/native display bridge, DPI hardware or HUD windows. https://github.com/ArdaNTM/JAS/actions/runs/43789685660
- PR #126 HEAD b7f8509436755620163504ec23a2ad1d2a90b1df: feature #92 PARTIAL; Core 648 passed/6 skipped, Final Release Lock PASS, Persistence PASS; No real HUD window rendering, OS input or device/hotplug acceptance. https://github.com/ArdaNTM/JAS/actions/runs/43790466164
- PR #123 HEAD c395721dcc0a3b5743b8ae74f87b01d11d7911fc: feature #93 PARTIAL; Core 601 passed/6 skipped, Final Release Lock PASS, Persistence PASS; No production app composition wiring, live HUD widget or hardware telemetry acceptance. https://github.com/ArdaNTM/JAS/actions/runs/43789150380
All tests run in separate GitHub branches; none proves live audio/desktop hardware or combined merge state.

## PR #127 exact-head verification — feature #54 PARTIAL
Core run https://github.com/ArdaNTM/JAS/actions/runs/43791155108: 618 passed / 6 skipped; Final Release Lock PASS digest sha256:2292eb093fd99515f9b9a763f5fc813472ad13aa5845db57a35431bb8f8b6a30. Persistence https://github.com/ArdaNTM/JAS/actions/runs/43791155045: PASS. Networkless fake MCP transport, real registry/PermissionEngine/Gateway. No live provider acceptance.

## PR #128–129 exact-head CI evidence
- Draft PR #128, HEAD 12a08718d42b4f26593b099a2b87152f86803a4d, #85 TESTING/PARTIAL: Core 609 passed/6 skipped, lock PASS, Persistence PASS. No real Home Assistant/Matter/Zigbee/HomeKit bridge, authenticated household ownership, physical device tests or Owner approval. https://github.com/ArdaNTM/JAS/actions/runs/43792527756
- Draft PR #129, HEAD 82e4883bb0ef3ab855a42e004f9ae26f531a425f, #86 TESTING/PARTIAL: Core 629 passed/6 skipped, lock PASS, Persistence PASS. No live HA integration, authenticated token, actual device sensor trust, physical control/Owner action or end-to-end production acceptance. https://github.com/ArdaNTM/JAS/actions/runs/43792885209
#128 final lock sha256:cfc508ab7888e7ec095145e0e30a86eb3c6923a9e6a9db74495d88f4cd674df4; #129 stacked full 235-source lock sha256:dea49a6e3e51ce01311cfe2f49f7eda394cbd5792a04d9e99eeb7e64fd4629a2. No real home devices tested.

## PR #130 exact-head verification
Core run https://github.com/ArdaNTM/JAS/actions/runs/43793662855: 633 passed, 6 skipped, Final Release Lock PASS digest sha256:fc6280614c58cb575e44a9cb8163d0d8a63df62142f392300f07a88160859468. Persistence run https://github.com/ArdaNTM/JAS/actions/runs/43793662847 PASS. Tests cover real registries and NO_PROVENANCE SkillValidator denial. No real provider call, execution, sandbox or hardware.

## Exact-head #135 hotfix and #136 multi-PR integration CI

| PR | Exact head | Core | Final Release Lock | Other workflows |
| --- | --- | --- | --- | --- |
| [#135](https://github.com/ArdaNTM/JAS/pull/135) | `7e10ca4500ff` | 599 passed / 6 skipped | PASS (234 source files, sha256:6af648fb50b923cfb05111286f1754dd0b23eea1adfd09471aac0cccfaf48870) | Persistence, Windows PASS |
| [#136](https://github.com/ArdaNTM/JAS/pull/136) | `91afeb0298ce` | 969 passed / 6 skipped ([run 43798715015](https://github.com/ArdaNTM/JAS/actions/runs/43798715015)) | PASS (253 sources, sha256:9ea3b86ab4e8a777adaacd8f824e626c426ced250389314c30e9c30f1a0cccca) | [Persistence 43798715007](https://github.com/ArdaNTM/JAS/actions/runs/43798715007) PASS, [Windows 43798715049](https://github.com/ArdaNTM/JAS/actions/runs/43798715049) PASS |

#136 adds four actual cross-module tests covering SQLite+PermissionEngine, two separate Gateway-authorized Home reads, display EventBus->HUD plan and WAV prosody DSP->generation-safe speech session. Existing integrated 969 tests exclude 6 skipped and cannot prove real microphones, Owner identity, hardware, earlier PR #64–#111 or production acceptance.

## PR #137/#138/#139 exact-head model/OCR evidence

- Draft PR #137, #77, HEAD `b07d37b240a15b837b8362be253633643a0894c0`: 628 passed / 6 skipped (Core [43799634157](https://github.com/ArdaNTM/JAS/actions/runs/43799634157)), Final Release Lock **PASS** sha256:479a81bf6cedba045074fbbee5192e842d905b3b588d680b760b99c16312ea62, Persistence [43799634160](https://github.com/ArdaNTM/JAS/actions/runs/43799634160) **PASS**. No real Qwen-VL model weights/GPU throughput, image parser hardening, signed Owner consent/device UI or live model hardware evidence.
- Draft PR #139, #79, HEAD `7c1aa87b73fc0ea8000870a8ca7e44a7ba523134`: 646 passed / 6 skipped (Core [43800598686](https://github.com/ArdaNTM/JAS/actions/runs/43800598686)), Final Release Lock **PASS** sha256:35cd8317518abdedac16879a3f2f498614bb4bac5a84a053855d304a917f1d1b, Persistence [43800598856](https://github.com/ArdaNTM/JAS/actions/runs/43800598856) **PASS**. Model-generated boxes not calibrated, ground-truth checked or measured on real camera/screen; no actionable target or hardware acceptance.
- Draft PR #138, #80, HEAD `c239a5d29e097474f7f2cfa06f1433abc745d92f`: 656 passed / 7 skipped (Core [43800651799](https://github.com/ArdaNTM/JAS/actions/runs/43800651799)), Final Release Lock **PASS** sha256:bf8ae8ede65609510437afe986a0997e42b0812e737543a6632f317b79e56712, Persistence [43800651766](https://github.com/ArdaNTM/JAS/actions/runs/43800651766) **PASS**. Optional live OCR smoke skipped when Tesseract/English traineddata/font are missing; no deployed Windows trusted binary and Turkish traineddata/hardware/Owner quality evidence.

#137 real local Ollama HTTP client under Gateway tested with `httpx.MockTransport`; #138 real Tesseract `create_subprocess_exec` contract and optional live CLI smoke (one more skip overall); #139 strict model JSON box evidence. CI PASS does **not** imply model weights/devices available in production. Source-lock branches independent, #138/#139 both depend on #137.
