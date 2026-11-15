# AURA implementation architecture decisions

## ADR-ENG-001 — 2026-11-15: non-executing, fail-closed acceptance ledger

Decision: track all 117 user goals in `AURA_FEATURE_TRACKER.json` and validate structure, dependency cycles and completion evidence with a deterministic standard-library script. The tracker has no Runtime, Tool, Owner, Docker or MCP execution authority.

Rationale: JAS already has a Kernel, registries, PermissionEngine and MCP Gateway; adding a parallel orchestration authority or rewriting modules for planning would violate the single-source-of-truth and least-privilege constraints.

Status semantics: `NOT_STARTED` reflects that **this program has not established feature acceptance evidence**. It is not a claim that JAS lacks that function. `assessment=NOT_ASSESSED` distinguishes existing-but-unverified code. Never mark `COMPLETED` based solely on a PR being opened.

Release governance: no merge without owner approval; draft F2.7 remains draft. Security/physical-hardware results require separate evidence.
