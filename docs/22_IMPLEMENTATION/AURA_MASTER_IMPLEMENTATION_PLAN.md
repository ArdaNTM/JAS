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
