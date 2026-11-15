# Feature #58 — fail-closed specialist plan admission (partial)

The existing JAS SwarmOrchestrator continues to dispatch all approved
specialist tool requests exclusively through MCPGateway/PermissionEngine.
This PR validates the **entire** proposed sequence before any tool dispatch
or EventBus publication. An invalid second step must not execute the first.

Input guardrails cover fixed allowlisted roles, exact principal and task IDs,
bounded JSON arguments (1000 nodes, depth 10, <=32 KiB per step) and
type-confused step limits. Cyclic or nonfinite/unserializable inputs fail
closed. A successful syntax preflight is NOT an Owner-approval receipt,
semantic permission, mission outcome verification or autonomy grant.

No new agent role, policy, provider, tool execution, credential, OS command
or F2.7 broker action is introduced. Gateway denial still halts the sequence.
Feature #58 remains partial, pending real owner-controlled end-to-end
specialist delegation and independent security acceptance.

Test: cd core && uv run pytest -q tests/test_swarm_plan_admission.py
plus full AURA Core Assurance and Final Release Lock.
