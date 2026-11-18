# AURA implementation architecture decisions

## ADR-ENG-001 — 2026-11-15: non-executing, fail-closed acceptance ledger

Decision: track all 117 user goals in `AURA_FEATURE_TRACKER.json` and validate structure, dependency cycles and completion evidence with a deterministic standard-library script. The tracker has no Runtime, Tool, Owner, Docker or MCP execution authority.

Rationale: JAS already has a Kernel, registries, PermissionEngine and MCP Gateway; adding a parallel orchestration authority or rewriting modules for planning would violate the single-source-of-truth and least-privilege constraints.

Status semantics: `NOT_STARTED` reflects that **this program has not established feature acceptance evidence**. It is not a claim that JAS lacks that function. `assessment=NOT_ASSESSED` distinguishes existing-but-unverified code. Never mark `COMPLETED` based solely on a PR being opened.

Release governance: no merge without owner approval; draft F2.7 remains draft. Security/physical-hardware results require separate evidence.

## ADR-ENG-002 — 2026-11-15: Branch-specific release-lock inventory must be regenerated after authorized integration

Each independent feature PR uses the JAS deterministic source lock and tests its *own* current source set. The `release-manifest.final.json` file is intentionally shared; its aggregate hash cannot simply be cherry-picked from several branches. Never auto-resolve it or disable the verifier. An owner-approved merge requires re-evaluating the combined source inventory, recomputing all selected hashes, running final lock verification and full CI on the integrated tree. Open PRs remain review-only and `main` stays unchanged.

## ADR-ENG-003 — 2026-11-15: Storage confirmation is not authenticated authorization

Flags such as `confirmed=True` or `consented=True` in low-level local stores are only fail-closed preconditions, not Owner signatures or principal validation. Do not expose destructive storage methods as model tools without a separately reviewed, authenticated PermissionEngine/MCP Gateway + human approval workflow.

## ADR-ENG-004 — 2026-11-16: external HMAC checkpoints are evidence, never authority

Feature #107 uses the existing in-memory Gateway-connected `HashChainAuditLedger` and canonical SHA-256 record format. A read-only helper verifies a frozen snapshot and generates a scope-bound HMAC checkpoint with a caller-held secret and previous-checkpoint chain. It does not insert a second audit/security engine, mutate PermissionEngine, authorize execution or silently grant Owner approval. A separate durable verifier and independently protected key/receipt repository are prerequisites to any WORM/prod audit claim.

## ADR-ENG-005 — 2026-11-16: pure report serialization has no filesystem authority

Feature #112 isolated XLSX report generation takes already-authorized bounded data, returns memory bytes and treats formula-looking values only as inline strings. PermissionEngine and MCP Gateway remain the only execution authority; this primitive cannot read/write files or send mail. Other document types and end-to-end authorization are separate acceptance gates.

## ADR-ENG-006 — 2026-11-16: approval list and decision are separately policy-governed

Feature #100 security hardening uses current authenticated principal + existing Core PermissionEngine. Requester can see their pending records but cannot self-approve. Cross-principal enumeration and decisions require distinct explicit policy ALLOW with exact record scope; absent registry/policy is DENY. Approver identity is not authenticated merely by a client header; real Owner credential assurance and fully wired Gateway approval lifecycle remain acceptance gaps.

## ADR-ENG-007 — legacy authentication must never have a shipped default secret

Existing compatibility WebSocket credential comparison now requires explicitly configured strong secret and uses constant-time UTF-8 comparison. It deliberately does not change one-time WebSocket ticket ownership or create an Owner identity. Real device-bound principal authentication remains independent.

## ADR-ENG-008 — sandbox output safety requires post-drain status and a combined budget

DockerPythonRunner uses one capture byte budget over both pipes under a synchronization lock. A job must not be recorded as completed before reader threads finish and output overflow has been observed; invalid option-looking image references are denied before a container can start. Neither check substitutes for actual Docker/kernel isolation or Gateway authorization.

## ADR-ENG-009 — bounded voice profiles belong under registered MCP tools

Existing Kokoro MCP provider, not another local AI runtime, remains the synthesis execution path. Validate voice/rate/text before model loading, stream all chunks into bounded output, return sanitized MCP errors. Continue to use existing Gateway permission and capability mapping. Lock executable provider code as well as Core helper. Real model licensing/hardware tests and Owner approval are separate gates.

## ADR-ENG-010 — research coordination may not bypass Gateway or trust source text

Multiple source queries are permitted only by calling existing MCPResearchSource.search with authenticated principal, exact scope and unique request ID through MCPGateway. Any non-ALLOW reply aborts without partial output being called complete. Third-party URLs and text are untrusted observations, not privileged instructions.

## ADR-ENG-011 — human-review research dossier cannot assert model-generated truth

A deterministic evidence packet can group source references and flag subquestion gaps but must not equate source host counts to independent verified publications. Full deep research needs distinct governed LLM planning, source truth verification and Owner acceptance. Stack the dossier PR on the verified query coordinator, not a second authorization or fetch runtime.

## ADR-ENG-011 — POSIX safe file read and Windows separate gate
Pin test-data root inode and walk descriptors with O_NOFOLLOW on POSIX. This is read-only and does not prove Windows handle/reparse race safety. MCP Gateway retains execution authority.
## ADR-ENG-012 — bound memory identity and deny unapproved store operations
Trusted Core composition binds the authenticated principal; every read/write/forget requires an explicit Core PermissionEngine ALLOW. The adapter does not authenticate identity, grant Owner approval, encrypt stored data or replace MCP Gateway tool authorization.

## ADR-ENG-013 — deny-only attested Core registry guard is not hardware immutability
A read-only digest of existing PermissionEngine policies plus Service/Capability/Provider registry state may be HMAC-attested by an independent verifier. Optional wrapper can DENY on drift, but only existing MCPGateway authorizes/dispatches. No owner permission or kernel trust root is granted; all-path enforcement and protected signer remain future prerequisites.
## ADR-ENG-014 — personal knowledge must consume governed principal-bound storage
Bounded personal hub queries use the existing GovernedEpisodicMemory PermissionEngine policy per query, fail closed on revocation and treat memory text as UNTRUSTED. No raw SQLite identity override, direct model execution or new tool authorization. Full encrypted multi-source integration requires Owner acceptance.

## ADR-ENG-015 — voice session results require generation identity before mutation
Speech transcription and playback tasks must never mutate a newer or closed FullDuplexSessionManager session. Record generation and session ID under the existing lock, discard late STT results and register playback tasks atomically with interrupt/close. Existing MCPGateway remains the only tool dispatch authority; no microphone consent, user authentication or hardware trust is inferred from race tests.

## ADR-ENG-015 — wake phrase EventBus signals are never permissions
A text-only standalone offline speech phrase match under a confirmed session emits one EventBus marker and disarms. It is neither acoustic identity nor microphone consent authority. No MCP tool executes from the signal.
## ADR-ENG-016 — language route preview must match authoritative provider selection
Explicit local tr->Piper/en->Kokoro metadata previews reject missing/unhealthy or differently selected provider and never reconfigure CapabilityRegistry, authorize PermissionEngine or dispatch MCP. Live bilingual voice routing needs separately approved integration.

## ADR-ENG-017 — audio signal-level cues are not sound classification or voice authority
Feature #20 only computes bounded PCM energy/clipping from consented upstream audio; emits metadata-only EventBus notifications, no raw audio, tool action or permission.
## ADR-ENG-018 — monitor topology and HUD placement are metadata previews
Features #28 and #92 require trusted shell-supplied monitor metadata. Core validates bounded display geometry and non-overlapping HUD panel rectangles; OS windows, captures and actual input remain separately authorized outside this slice.
## ADR-ENG-019 — redacted live system status must remain authenticated
Feature #93 projects only allowlisted aggregate registry health and telemetry. No provider identifiers, raw diagnostics or secrets reach the optional bearer-protected HTTP router.

## ADR-ENG-020 — GitHub read-only evidence must pass the existing MCP Gateway
Scoped JAS pull request metadata retrieval binds a trusted principal and exact repo/PR number, dispatches exclusively through authorized MCPGateway and treats all returned metadata as UNTRUSTED. No GitHub mutations/merge grants, direct provider calls, credential leakage or automatic Owner approval.

## ADR-ENG-021 — physical device inventory never grants actuation
Generic home discovery uses exact Principal + PermissionEngine + MCPGateway authorization and returns only bounded untrusted safe-category device hints. The nested structured MCP failure flag is a fail-closed error. No network scanning, credential or physical write.

## ADR-ENG-022 — per-entity HA read is separately authorized
A device present in an approved inventory does not gain read or action authority. Home Assistant-style state reads require new exact entity-scope Gateway permission and matching registered provider identity. This stacked read-only layer never controls physical devices.

## ADR-ENG-023 — skill proposals are immutable data, never new authority
Skill proposals can reference only explicit low-risk read-oriented existing capabilities and operations. Generated candidates start disabled with no provenance; existing SkillValidator must deny promotion. No implicit PermissionEngine/Gateway authorization, ProviderRegistry registration, code evaluation, script execution or Owner consent.

## ADR-ENG-023 — combine review PR sources without relaxing Core permission boundaries

A separate Draft integration branch containing #112–#135 preserves authoritative deterministic Kernel registries, Core PermissionEngine, MCP Gateway and EventBus and rechecks a newly generated complete 253-file source lock. The shared full-duplex speech source must keep #120 generation-safe interruption while incorporating #131 advisory prosody only while the original session/generation remains active. This is **not** permission to execute tools, alter the F2.7 Owner security seal or merge any PR automatically.

## ADR-ENG-024 — local model vision and OCR must remain Gateway-executed

Real local Ollama/Qwen-VL image description (#77) and Tesseract stdin/stdout OCR (#80) are separately registered Core MCP capabilities, not direct agent calls. Explicit PermissionEngine ALLOW and current MCP DispatchGrant required; client-supplied capture consent is not automatically trusted Owner identity. A local model response and all OCR text are untrusted output.

## ADR-ENG-025 — object boxes are model hypotheses, not action targets

Feature #79 parses strict bounded normalized boxes produced by the same governed #77 local model and returns immutable UNTRUSTED evidence only. No automatic clicking, pointing, person identification or physical control may follow without independently verified geometry and newly approved Gateway capabilities.

## ADR-ENG-024 — local stereo computation is not a physical authorization source

Feature #81 real bounded SAD depth operates on rectified P5 pair bytes with trusted-composition numerical calibration, under existing Core registries and an exact MCP Gateway permission. Depth output is a sparse UNTRUSTED estimate, with no physical-action authority. Numerical consistency cannot replace calibrated camera evidence or human Owner approval.

## ADR-ENG-026 — dynamic SVG cannot confer action authority

Feature #95 is explicitly opt-in (`AURA_LIVE_CHART_ENABLED=1`), read-only and bound to real EventBus/RuntimeProfiler metrics, existing Core registries, PermissionEngine and MCPGateway exact-scope grants. HTTP bearer/principal authentication and Gateway ALLOW must independently succeed per SVG request; direct provider access remains denied. Only trusted numeric samples are converted to static SVG by Core, with CSP and no-store. In-process event attribution is not cryptographic provenance; output stays `REDACTED_UNTRUSTED_TELEMETRY`. Native desktop acceptance and full merged-source lock remain separate gates.
