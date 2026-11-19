# Governed declarative workflow proposal — feature #49 (partial)

This review-only slice adds `aura_core.learning.governed_skill_proposals.GovernedSkillProposalBuilder` on top of existing AURA Core `CapabilityRegistry`, `SkillLibrary`, `SkillStep` and `SkillValidator`. It creates immutable proposal **data**, not executable skills, tools or permissions.

## Contract and authority boundary
- Trusted composition explicitly supplies a bounded allowlist of registered capability IDs and operation IDs. Unlisted capabilities, operations, high/medium/critical-risk capabilities, missing/unhealthy capabilities and non-MCP or non-readonly categories fail closed.
- At most eight declarative steps with bounded, flat primitive argument maps. Nested structures, arbitrary templating, control characters, unbounded numerics and malformed step schema are rejected. No interpreted Python, shell, imports, file writes, arbitrary code generation or MCP provider calls.
- Existing CapabilityRegistry supplies selection metadata only. This module does not register new services/capabilities/providers, does not call PermissionEngine, and **never** calls MCPGateway; any later actual execution must pass the current Gateway authorization and tool argument schema. Registry and provider health can change after a preview, so downstream must revalidate.
- `SkillProposalPreview` is immutable, `CANDIDATE_UNVERIFIED`, and has `NO_EXECUTION_OR_PROMOTION`. Conversion to existing `Skill` returns a fresh `enabled=False`, `confidence=0`, `source_run_ids=[]` candidate. Existing `SkillValidator` reports `NO_PROVENANCE` error; no automatic SkillPromotionManager activation, persistence or replay.
- The built-in allowlist includes only **explicitly provided** low-risk read-oriented candidates. No guessed permission or human approval status is derived from user text.

## Tests
`cd core && uv run pytest -q tests/test_governed_skill_proposals.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use actual ServiceRegistry/CapabilityRegistry/ProviderRegistry, immutable proposals, deterministic SkillLibrary IDs and existing SkillValidator. Negative paths cover unregistered/high-risk/missing capabilities, unknown operations, nested/unsafe arguments, template-looking strings, invalid skill inputs, candidate tampering and missing promotion provenance. No real skills execute.

## Outstanding acceptance
- No live UI, authenticated Owner consent, sandboxed skill authoring, version governance of generated workflows, real provider execution, Gateway dispatch integration, multi-run replay, immutable audit/promotion approval or production test.
- A declared `read-only` category is only a policy selection hint, **not proof** that the remote MCP provider cannot mutate state; production must independently constrain providers/operations and enforce explicit Gateway/Owner permissions.
- Feature #49 remains `TESTING / PARTIAL_VERIFIED` only after exact-head Core/Persistence/Final Release Lock CI. It is not a full autonomous skill generation or COMPLETED implementation.
- No extra dependency, model download or license.
