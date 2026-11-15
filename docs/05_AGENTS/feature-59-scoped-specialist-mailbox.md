# Feature #59 — scoped specialist message mailbox (partial)

Adds `aura_core.application.agent_mailbox.ScopedAgentMailbox`, a
bounded **ephemeral, in-process** data queue allowing the *existing* JAS
specialist role labels `coder` and `researcher` to exchange explicitly
addressed text. The mailbox enforces exact principal/task scope,
recipient selection, unique message IDs, deterministic sequence numbers
and explicit consumption. No executing agent, EventBus subscriber,
MCP tool call, external transport, filesystem or network is created.

Important authorization limits:
- A caller-provided `sender_role` is NOT proof of agent identity.
- Every message has `sender_authenticated=False`,
  `authorization_checked=False`, `delivered_to_agent=False`,
  `tool_executed=False`, `untrusted=True`.
- `confirm=True` only requests local queue consumption and is not a
  user/Owner permission receipt. Upstream principal/role authentication,
  PermissionEngine and MCP Gateway checks are necessary before exposure.
- Text is **data**, never a new capability, policy, tool invocation,
  instruction authority or an actual execution outcome.

Bounds: 128 pending records, 2,048 characters/4,096 UTF-8 bytes each,
1,024 replay IDs per instance; send fails closed on a full queue.
No persistence, cross-process messaging, retries, backpressure scheduling,
authenticated signatures, independent delivery receipts or security
assessment. Feature #59 stays TESTING/PARTIAL.

Tests:
`cd core && uv run pytest -q tests/test_scoped_agent_mailbox.py`;
full Core Assurance, Remote Persistence and Final Release Lock required.
