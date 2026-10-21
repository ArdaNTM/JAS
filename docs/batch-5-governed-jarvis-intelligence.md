# Batch 5 — governed JARVIS intelligence

Batch 5 adds a higher-level intelligence layer without replacing the deterministic Kernel, registries, Permission Engine, EventBus, or MCP Gateway.

## Included

- **Durable episodic memory** (application/episodic_memory.py): SQLite-backed preferences, facts, episodes, goals, and lessons; scoped by principal_id; bounded plain-text recall; explicit deletion; importance ranking; configurable path via AURA_MEMORY_DB or AURA_DATA_DIR.
- **Governed self-adaptation** (application/jarvis_intelligence.py): bounded outcome observations, deduplicated proposals, a reviewed strategy allow-list, and explicit approval. Unknown strategy identifiers are rejected. Approval only records a strategy as approved; it does not generate code, change authorization policies, or directly execute tools.
- **Proactive initiative projection**: allow-listed Kernel event types become deduplicated suggestions requiring user review. Suggestions are read-only and explicitly marked can_execute=false.
- **Local API surface** (application/jarvis_api.py): /api/jarvis/memory, /api/jarvis/adaptations/*, and /api/jarvis/initiatives. These endpoints reject non-loopback clients. If the service is exposed through a reverse proxy or network interface, add real authentication and trusted-proxy handling before enabling access.
- **Event integration**: the existing EventBus live bridge feeds task outcomes into the bounded adaptation observation ledger and maps allow-listed events into initiative suggestions.

## Safety and capability boundaries

This is **governed adaptation**, not unrestricted self-modifying software. A newly available MCP tool can be discovered through Batch 4's live capability-discovery API and presented as a proposal. It must still be reviewed; metadata approval does not grant permission. New tools do not become executable merely because they were discovered or mentioned in memory.

No arbitrary package installation, dynamic Python import, shell execution, permission-policy mutation, or autonomous side-effecting task launch is introduced. All actual tool execution remains on the existing AgentTaskService → AgentExecutor → MCPGateway → PermissionEngine path. Proactive suggestions cannot invoke tools. The approved strategy set is metadata at this stage and is not automatically injected into the reasoning planner; this keeps adaptation observable and reviewable until each strategy has its own implementation and tests.

Memory stores user/task content as data, not trusted instructions. The initial retrieval is bounded lexical search, not vector/semantic recall. SQLite data is local and persistent, so operators should protect the configured data directory and provide retention/backup policy appropriate to their environment.

## API examples

Remember a lesson:

~~~http
POST /api/jarvis/memory
Content-Type: application/json

{
  "principal_id": "local-user",
  "kind": "lesson",
  "content": "Check source evidence before finalizing a research response.",
  "tags": ["research", "quality"],
  "importance": 4
}
~~~

Recall scoped memories:

~~~http
GET /api/jarvis/memory?principal_id=local-user&query=research&limit=20
~~~

Propose a reviewed strategy and explicitly approve it:

~~~http
POST /api/jarvis/adaptations/proposals
{"strategy_id":"retry_transient_transport_once","rationale":"Use a single bounded retry for transient transport failures."}

POST /api/jarvis/adaptations/proposals/adapt-.../approve
{"confirmed":true}
~~~

Read initiative suggestions:

~~~http
GET /api/jarvis/initiatives?limit=20
~~~

## Verification

From PowerShell:

~~~powershell
cd D:\AURA\JAS\core
uv run pytest -q tests/test_jarvis_intelligence.py tests/test_jarvis_api.py
uv run pytest -q
~~~

The focused tests cover principal isolation, deletion, bounded observations, allow-listed strategy proposals, explicit approval, and non-executing initiative suggestions. Live MCP integration and real-provider runtime behavior must still be verified in the local AURA environment.
