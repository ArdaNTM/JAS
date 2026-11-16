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
