# #1 / #99 — Scoped Memory and Authorization Acceptance Notes

Status: **reviewable integration only**. This is a scoped engineering security review, **not** Owner/security-board sign-off. Neither PR #64 F2.7 nor privileged runtime paths are modified.

## Tested boundaries
- Real AURA Kernel bootstrap, Service/Capability/Provider Registries, PermissionEngine, EventBus, MCPGateway, SQLiteApprovalStore and EpisodicMemoryStore.
- New MCP adapter uses **existing** SQLite memory. Principal comes only from Gateway DispatchGrant, never caller JSON.
- SQLite reopen confirms durability. Recalled records have untrusted=true; saved prompt injection is data, not policy.
- Default deny, foreign principal/scope, deny precedence, revocation, schema rejection, direct-provider rejection, fingerprint tamper, approve/consume and replay denial.
- Low-risk remember/recall need explicit policies; HIGH-risk forget requires consumed approval. Provider registration creates no policies.
- SQLiteApprovalStore.decide cannot authenticate a human approver. Unit tests use *test identities* only; no production Owner assurance is implied.

## Acceptance blockers
1. Independent security review, Owner approval authentication, production policy enrollment and protected audit receipt evidence.
2. Full user conversation, embeddings/long-horizon retention and deletion lifecycle, multi-process recovery, real PostgreSQL migration.
3. Windows NTFS directory ACL and memory content-at-rest protection; logical deletion is not physical-media secure erasure.
4. End-to-end integration with unmerged canonical PRs on a single reconciled source tree, independently verified live remote persistence.
5. End-user session acceptance and production release approval.

## Invariant
Kernel → Registries → PermissionEngine → MCPGateway → ScopedEpisodicMemoryMCP → SQLite.

No model output or memory record grants tool authority. Neither feature is COMPLETED without these gates.
