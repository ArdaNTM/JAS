# AURA 117-feature implementation program

Status: **INITIAL AUDIT / NOT A PRODUCTION RELEASE** (2026-11-15).

JAS and its existing architecture remain authoritative. Baseline: `main` commit `b1ffe6f534ced0d329dae273a4b949a634cb8bfa`. Existing F2.7 draft PR #64 is **not merged** and must not be represented as production-ready; no SCM or broker privilege expansion is authorized by this program.

## Architecture invariant

`Kernel → registries → PermissionEngine → MCP Gateway → provider`.

No independent alternative authority system, unapproved tool execution, self-granted permissions, or automatic security-kernel mutations. Existing memory, task, voice, HUD and OSWorld components must be assessed before adding duplicates.

## Execution dependencies

- Phase 0: verify existing JAS modules, tests, CI and PR graph; maintain truthful evidence ledger.
- Phase 1: permission boundaries, durable scoped memory, task/goals, local/offline operations and observability; security controls remain mandatory throughout all phases.
- Phase 2: voice/KWS/ASR/TTS, interruption and multilingual speech.
- Phase 3: governed computer interaction; no direct unapproved filesystem, shell or UI access.
- Phase 4: source-aware local web/academic research and document processing.
- Phase 5: coding and multiple specialist agents under an independent verifier.
- Phase 6: vision and HUD; permissions for screen/camera; keep local inputs local by default.
- Phase 7: numerical science, CAD and reproducible research; real lab hardware requires approval.
- Phase 8: smart home/robot/sensors with device-specific identity, emergency stop and human approval.
- Phase 9: calendar, email, media, reporting, games and integrated acceptance.

Phase ordering is provisional and reflects the user-supplied objectives, not an already-verified dependency graph. Update it only with reviewed code evidence.

## Acceptance definition

Status `COMPLETED` requires a reviewed commit, PR, executable tests, security result and acceptance evidence. CI, simulation and real-hardware acceptance are distinct; network isolation and benchmark scores must never be inferred from boot-only smoke.

## Near-term handoff

Current work is a **real validator** and an explicitly unverified 117-entry tracking ledger, not implementation of all 117 capabilities. Current candidates: #8, #29 and new partial implementations #2, #3, #4, #5, #9, #15, #36, #42, #44, #67, #73 across open PRs #66–#75. Every candidate is partial pending independent acceptance, integration and owner merge approval. Continue by current code dependencies rather than treating the numbered phases as stopping points. Keep PR #64 Draft until independent live acceptance.

## Latest implementation continuation checkpoint (2026-11-15)

Additional scoped partial features tracked: #12, #30, #37, #38, #40,
#41, #48, #56 and #111 via PRs #76–#83. Repository main and F2.7 security
authority are unchanged. Next dependency review should select one
non-overlapping existing JAS capability boundary, implement real tests, and
avoid introducing a new tool authority or auto-merging PRs.

## Latest scope checkpoint

Additional reviewable partials: #115 offline vocabulary persistence (PR #84),
#58 all-steps swarm preflight (PR #85), #6/#102 bounded untrusted
context synthesis (PR #86). All required CI checks passed on reported heads.
No feature was promoted to COMPLETED and no automatic merging is authorized.

## Latest independently reviewable slices

PR #87 contains secure DOCX text extraction (#39).
PR #88 contributes offline Python architecture/Markdown API documentation
(#47/#53). PR #89 contributes offline, read-only ICS calendar observations
(#109). All have Core Assurance/Release Lock/Persistence PASS on individual
heads. Features remain TESTING/PARTIAL_VERIFIED, not COMPLETED.
No automatic merge or F2.7 activation is authorized.

## Latest verified development checkpoint (2026-11-15)

PR #90 implements a partial offline backup integrity envelope (#105);
PR #91 partial hypothesis/scientific study design (#65/#72);
PR #92 partial bounded RK4 mass–spring–damper simulation (#68/#71).
All current heads have Core Assurance, Remote Persistence and Release Lock PASS.
No feature marked COMPLETED; no production hardware or Owner acceptance.
Continue with independent reviewable branches and preserve JAS Kernel/
PermissionEngine/MCP Gateway/Owner boundaries.

## Additional scoped partials

PR #93: offline MIME read-only preview (#108). PR #94: PNG/GIF/WAV
header-only media inspection (#110). Both validated via Core Assurance,
Remote Persistence and release lock on their independent PR heads.
No Owner or physical acceptance, no direct main mutation or auto-merge.

## Latest independent engineering packages

PR #95 supports only scoped read-only action event explanations (#98/#117).
PR #96 supports bounded offline box/cylinder prototyping (#70/#74/#114)
and real STL binary serialization; it does not control 3D hardware.
Both have Core Assurance, Persistence and Release Lock PASS on their own
heads. No PR is auto-merged, no feature promoted to COMPLETED.

## Latest continuation checkpoint

PR #97 adds real bounded offline goal-DAG planning (#10/#62), Core
Assurance, Remote Persistence and Final Release Lock PASS. It neither
deploys an autonomous agent nor changes any authorization boundary.
No feature marked COMPLETED; main unchanged and all new PRs Draft.

## Next continuation checkpoint — 2026-11-16

Current independent partial components: #98 conversation-memory proposal review
(#7/#21), #99 specialist mailbox (#59), #100 scientific citation/material
evidence screening (#66/#69), #101 in-memory reversible transaction preview
(#34/#52). All exact-head Core Assurance, Persistence and Release Lock
workflow runs PASS. These seven feature IDs remain TESTING/PARTIAL_VERIFIED;
neither Owner acceptance nor physical execution is implied. No auto merge.

## Continuing partial features (2026-11-16)

PR #102: scoped offline SQLite scientific notes (#11/#76).
PR #103: read-only specialist response metrics (#63).
PR #104: static code red flags and explicit runnable pytest generation (#46/#50).
All exact heads Core Assurance, Remote Persistence and Release Lock PASS.
None is fully authorized/accepted or marked COMPLETED; no merge.

## PR #105 continuation note

Adds actual Core CapabilityRegistry health-based specialist **selection**
(#57/#64), but no specialist execution, tool capability, high-risk
authority or new registration. Exact-head CI and Release Lock PASS.
All newly tracked entries remain TESTING/PARTIAL_VERIFIED.

## PR #106 security-foundation continuation and remaining program groups

PR #106 implements #107 only **partially**: read-only independently keyable audit checkpoints over the existing Gateway audit metadata. Exact-head Core and Persistence CI plus Release Lock passed; durable independent custody, trusted audit completeness and Owner acceptance are missing. Tracker now has **59 TESTING, 2 RESEARCHING, 56 NOT_STARTED**; zero completed.

Next dependency-sensitive engineering groups (IDs are feature IDs, not PR numbers; existing code must be assessed before implementation):

1. **Security/authority prerequisite:** #100 explicit approver policy/identity; #103 authenticated principal/device identities; #101 sandbox isolation; #106 security-core immutability; #104 protected memory/key custody. Do not grant new permissions while closing these gaps.
2. **Voice foundations:** #13 wake word, #14 interruption, #16 speaker differentiation, #17 speech affect cues, #18 voice settings, #19 multilingual flow, #20 environmental sound events, #22 offline integration. Device permissions and actual microphones remain independent gates.
3. **Governed desktop:** read-only #23/#25/#28, then Owner/Gateway-gated #24/#26/#27, then #31/#32/#33. Avoid direct OS execution shortcuts.
4. **Research:** #35 multi-source authorized fetch precedes #43 deep-research orchestration.
5. **Development/agents:** #51 sandbox before #45/#49/#54, then verified #55/#60/#61 coordination.
6. **Perception + HUD:** #77/#79/#80/#78/#81/#82/#83/#84 source/observation chain; #91/#92/#93/#95/#96/#97 HUD/display; #94 authenticated voice UI.
7. **Laboratory:** #75 only after explicit device identity, safety approval and emergency stop.
8. **Physical systems:** #85/#86/#88 discovery/sensors, then #89/#90 verified automation, then #87 robot actuation with human emergency controls.
9. **User outputs:** #112 artifact production, #113 game-design integration, #116 personal knowledge index after secure storage/identity.

The tracker dependency arrays for unassessed goals remain conservative; these groups are review guides, not assertions that unmerged features already exist on main. Merge each reviewed PR only with Owner approval, then regenerate shared complete manifest and run cumulative CI.

## 2026-11-16 implementation continuation: PR #107/#108

- #112 bounded offline XLSX serializer implemented partially and tested on Draft PR #107; full document/presentation suite and authenticated export missing.
- #100 explicit PermissionEngine-gated cross-principal approval views/decisions implemented partially and tested on Draft PR #108; no new implicit review authority. Real operator identity/policy composition/Owner acceptance missing.
- Exact-head Core, Persistence and Release Lock PASS on each isolated PR, not a combined build. Tracker status **61 TESTING / 2 RESEARCHING / 54 NOT_STARTED**, zero COMPLETED. Continue priority review of identity (#103), core immutability (#106), sandbox (#101), secure memory (#104) and remaining phases without requiring any intermediate feature merge.

## Additional security boundary continuation — #101 and #103

Draft PR #109 closes the hardcoded legacy WS credential risk (#103 PARTIAL); Draft PR #110 fixes actual Docker runner output races and malformed image references (#101 PARTIAL). Both independently pass exact-head Core/Remote Persistence/Release Lock. Tracker counts **63 TESTING / 2 RESEARCHING / 52 NOT_STARTED** and zero COMPLETED. Continue voice #18 integration (PR #111 pending), then research #35 without direct fetch outside MCP Gateway, and remaining hardware-gated security #104/#106.

## Voice stage engineering proof — PR #111

#18 bounded English Kokoro voices and rate controls, complete chunk serialization and safe MCP error paths now implemented as partial code in independent Draft PR #111. Exact-head Core/Persistence/Windows/Release Lock PASS; model/device/Owner production acceptance outstanding. Tracker counts **64 TESTING / 2 RESEARCHING / 51 NOT_STARTED**, zero COMPLETED. Continue #35 through the existing governed MCP research provider and #43 only after #35 is safe; do not substitute provider network calls for Gateway execution authority.

## Research stage: #35 -> #43 dependency

PR #112 implements partial governed bounded multiquery (#35) with real JAS PermissionEngine/Gateway integration tests; PR #114 implements partial human-review research dossier (#43) stacked on #112. Each exact-head Core, Persistence and Release Lock PASS. Neither has authorized live internet, a vetted network fetch provider or trusted source verification. Tracker **66 TESTING / 2 RESEARCHING / 49 NOT_STARTED**, zero COMPLETED. Next safe independent group: #25 sandboxed filesystem path handling; maintain File MCP read authorization and prevent TOCTOU / symlink escape. Separate hardware/Owner acceptance later.

## 2026-11-16 verified PR #116/#117 continuation
Tracker 68 TESTING, 2 RESEARCHING, 47 NOT_STARTED (zero COMPLETED). Features #25 and #104 are PARTIAL_VERIFIED on Draft PRs #116/#117 with Core/Persistence/Release Lock PASS. Next security #106 requires tamper-evidence/deny-only tests; no claim of immutable hardware or secured memory. Continue dependency-sensitive phases without merging.

## Feature #106/#116 continuation through PR #119
#106 Core registry drift guard on Draft PR #118 and #116 principal-scoped personal knowledge view on stacked Draft PR #119 both pass exact-head Core, Release Lock, Persistence. Tracker now 70 TESTING / 2 RESEARCHING / 45 NOT_STARTED, 0 COMPLETED. External trust anchor and authenticated integration remain necessary. Next: #14 interruptible voice session concurrency or remaining read-only desktop/science tasks, preserving the Gateway and nonmerged PR architecture.

## Verified PR #120 interruptible voice continuation
#14 generation-safe voice session fixes passed exact-head Core/Lock/Persistence on Draft PR #120, still PARTIAL. Program now 71 TESTING, 2 RESEARCHING, 44 NOT_STARTED and zero COMPLETED. Future voice work: #13 wake word, #16 speaker identity and #19 multilingual quality, only after real microphone/privacy and owner authorization assessment.

## 2026-11-16 speech continuation #13/#19
PR #121 wake text gate and #122 local TTS language/provider preview passed independent exact-head CI and Final Release Lock; tracker now 73 TESTING, 2 RESEARCHING, 42 NOT_STARTED. Feature #20 energy signal and #28 read-only display metadata PRs require exact HEAD CI before tracker acceptance. Full audio/hardware acceptance and Owner consent remain separate.

## 2026-11-16 actual security/audio/HUD continuation
Feature #20 environmental PCM signal metadata, #28 display geometry, #92 stacked HUD placement, #93 authenticated redacted live status passed exact-head Core/Persistence/Release Lock. Tracker 77 TESTING / 2 RESEARCHING / 38 NOT_STARTED; zero COMPLETED. Prioritize real desktop/voice hardware and Owner authentication before any full acceptance.

## PR #127 verified — 2026-11-16
Feature #54 read-only JAS PR evidence passes independent Core/Persistence/Final Release Lock. Tracker 78 TESTING / 2 RESEARCHING / 37 NOT_STARTED (zero COMPLETED). Further implementation should prioritize real authenticated service integrations and hardware tests, not confuse preview-only slices with finished capabilities.

## Home integration dependency gate #85 → #86
PR #128 #85 and stacked PR #129 #86 pass exact-head Core/Persistence/Release Lock. Only read-only, policy-gated structured metadata, no HA hardware and no physical actions. Tracker 80 TESTING, 2 RESEARCHING, 35 NOT_STARTED; zero COMPLETED. Next #49 governed skill proposals pending CI before tracker update. Never merge without Owner approval.

## #49 skill workflow proposals — safe foundation
PR #130 tests and locks a nonpromotable declarative workflow preview, depending on #99/#100/#101/#103 for real authorization/identity/isolation. All CI PASS on separate head; 81 TESTING, 2 RESEARCHING, 34 NOT_STARTED, zero COMPLETED. Follow with real governed sandbox tests/Owner acceptances before autonomous agent features.

## 2026-11-16 — integrated PR #136, remaining actual capability work

Verified #135 Release Lock hotfix and #136 consolidated **22 Draft PRs #112–#135**, Core 969 passed / 6 skipped, Final Lock 253 sources PASS, Persistence and Windows PASS. Tracker remains **86 TESTING, 2 RESEARCHING, 29 NOT_STARTED, 0 COMPLETED**. Next dependency groups: desktop process/terminal and safe OS broker (#26,#27,#31–#33); live vision/OCR/camera with real local models (#77–#84); physical/robot/Home integration (#87–#90); multiagent development/parallel verification (#45,#51,#55,#60,#61); 3D HUD, audio interface and game workflows (#91,#94–#97,#113); autonomous lab (#75). No unsupported production acceptance or auto-merges.

## 2026-11-16 — local vision execution dependencies

Features #77 real Ollama Gateway provider, #79 bounded object hypotheses and #80 offline Tesseract OCR are implemented/tested in Draft PR #137/#139/#138 and pass exact-head Core/Persistence/Final Lock. Tracker now **89 TESTING, 2 RESEARCHING, 26 NOT_STARTED**, none COMPLETED. Next: real video frame isolation (#78), real pixel/screen integration, camera and hardware trust (#83/#84), with actual models, licenses and Owner acceptance before promotion. #136's consolidated source lock covers only PR #112–#135; must extend via new integration review for #137+.

## 2026-11-16 — local video #78 verified

Feature #78: FFmpeg frame sampling and per-frame local Ollama separately authorized via Core MCP Gateway; exact-head CI/Release Lock PASS PR #140; only PARTIAL_VERIFIED. Tracker 25 NOT_STARTED / 90 TESTING / 2 RESEARCHING. Next dependency chain #82 visual memory (SQLite/Principal/PermissionEngine), #83 camera (trusted device capture authorization), #84 visual task verification (independent evidence); never infer permission from computer vision text.

## 2026-11-16 — governed SQLite visual memory #82

PR #141 adds actual local SQLite metadata only with Core read/write/delete and model Gateway scope; exact-head CI and Lock PASS. Only partial: Windows ACL/privacy, live model/Owner UI missing. Tracker 24 NOT_STARTED / 91 TESTING / 2 RESEARCHING. Next #83 device camera, #84 independent visual state verification, then other dependent groups.
