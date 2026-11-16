# Governed bounded multi-query web research — feature #35 (partial)

This slice adds `aura_core.research.multiquery.bounded_multiquery_search` on top of the **existing** `MCPResearchSource.search` API. Each user-authorized query is passed through `MCPGateway.invoke`, which uses the existing CapabilityRegistry/ProviderRegistry/PermissionEngine boundary. There is no independent HTTP request, crawler, search provider, auto-grant or implicit external egress.

## Contract
- 1..3 distinct explicit queries, <=256 chars/query, bounded principal/scope/task and max 1..20 returned findings. Queries run serially with per-query gateway request IDs.
- Every query must receive `MCPGatewayResponse(decision=ALLOW)` with structured tool result; DENY/REQUIRE_APPROVAL/DEFER or malformed output aborts the entire batch, not returning incomplete citations.
- 100-item max tool result collection per query; 160-char title, 400-char snippet, 64-char backend label, <=2048-char public HTTP(S) reference URL. Duplicate URLs across queries have first-seen stable order and fragment-insensitive identity.
- Evidence source labels, page titles and snippets are **UNTRUSTED**. Provider ID derives from Gateway metadata, not a source's claimed label. Tool content must not be promoted into instructions/permissions.
- Localhost/private-IP literal, numeric shorthand, file/javascript schemes, embedded credentials, nonstandard ports and control-character URLs cannot become evidence. This is *reference filtering*, not proof of remote DNS or safe fetch.

## Quality
`cd core && uv run pytest -q tests/test_gateway_multiquery_research.py`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use fake MCP replies for negative-path coverage and separately create **real ServiceRegistry, CapabilityRegistry, ProviderRegistry, PermissionEngine and MCPGateway** with a non-networking test provider for explicit authorized dispatch/denial. No real web results, paid APIs or browser automation are used.

## Missing acceptance
- AURA's existing `core/scripts/local_research_mcp.py` network/fetch provider is **unchanged** and requires its own SSRF/DNS rebinding, redirect, remote content-length, credential logging and sandbox/security review before any production live-web capability claim.
- No real SearXNG installation, provider networking, authenticated external egress, browser research workflow, source reliability scoring, legal provider terms or Owner authorization acceptance.
- This is deterministic partial query orchestration, not full deep research #43. Feature #35 remains TESTING/PARTIAL_VERIFIED.
- No new packages or external dependencies; local stdlib and existing MCP contracts only.
