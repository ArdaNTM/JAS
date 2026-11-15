# Features #57/#64 — registry-aware specialist selection (partial)

This PR adds `aura_core.application.specialist_selection` as a real
read-only planner for the **existing** AURA Core `CapabilityRegistry`.
It validates bounded, explicitly supplied `SpecialistProfile` descriptors
for the existing `coder`/`researcher` roles and matches them to
registered, healthy, AVAILABLE/ACTIVE providers. Priorities and stable
provider ordering yield deterministic suggestions. Health changes in
CapabilityRegistry change the recommendation without creating new tools.

Security:
- Selection is **not** MCP invocation, authorization, dynamic provider
  installation, Owner approval, autonomous specialist activation or
  a verified identity/skill credential.
- Profiles are caller-supplied and untrusted identity claims. Every
  result has `profile_identity_verified=False`,
  `authorization_checked=False`, `owner_approval_verified=False`,
  `tool_invoked=False`, `specialist_started=False`.
- Critical/high-risk requested tasks or providers fail closed here;
  they require the separate authenticated Owner/PermissionEngine/
  MCP Gateway workflow. Registry availability is never sufficient to
  grant execution. No registry record or policy is mutated.
- Strict fixed role allowlist, explicit capability/provider IDs,
  max 32 profiles, priorities -20..20, duplicate-identity denial.

Tests use a **real** Core CapabilityRegistry with MCP capability records,
exercise healthy-to-unhealthy provider failover, empty/unregistered cases,
high-risk denial, malformed/duplicate profiles and stable ordering.
They do not spawn or test real expert agents.

Feature #57 specialist agents and #64 dynamic specialization remain
TESTING/PARTIAL pending actual authenticated agent runtime, Owner-approved
profile enrollment, specialized tool routing and end-to-end outcomes.

`cd core && uv run pytest -q tests/test_specialist_selection.py`,
full Core Assurance, Remote Persistence and Final Release Lock.
