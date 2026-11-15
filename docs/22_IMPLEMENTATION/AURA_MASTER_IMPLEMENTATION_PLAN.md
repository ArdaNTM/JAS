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
