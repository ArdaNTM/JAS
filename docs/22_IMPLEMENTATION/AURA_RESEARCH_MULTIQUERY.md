# Governed bounded multi-query research — feature #35 (partial)

`core/src/aura_core/research/multiquery.py` combines 1–4 validated public-web queries through the already-registered `MCPResearchSource.search()` adapter. Each query calls the **existing MCP Gateway**, which resolves a registered capability/provider and asks PermissionEngine. No additional HTTP fetch, direct MCP provider invocation, permission grant, backend selection or search credential handling is introduced.

## Contract
- `MultiQueryResearch(source: MCPResearchSource).search(queries, *, principal_id, resource_scope, risk_level, task_id)` returns `MultiQueryEvidence` containing up to 12 deduplicated, bounded `EvidenceHit` entries with query index, original rank, link, URL SHA256 identifier, title, snippet, backend and provider ID.
- A query has at most 256 characters; 1–4 unique queries are run sequentially, each with a distinct request/task ID for Gateway audit. Invalid input is rejected **before** any provider dispatch.
- A non-ALLOW (DENY, DEFER or REQUIRE_APPROVAL) for **any** query aborts the whole operation without exposing a partial evidence collection. MCP/provider failure and malformed/oversized output fail closed.
- Accept only the structured response of the existing MCP provider: no parsing arbitrary text tool output. Filter clearly nonpublic/ambiguous reported URLs, bound metadata, and omit duplicate URL fragments.
- Reported URL SHA256 is **an identifier only**, not a content integrity claim, attestation or evidence of successful fetch.

## End-to-end integration and threat boundary
- Tests use both a fake Gateway and a **real** `MCPGateway` + `PermissionEngine` + `CapabilityRegistry` + `ProviderRegistry` + `MCPProvider` (stub MCP connection) to prove denial does not dispatch and explicit policy ALLOW does.
- Third-party search titles, URLs and snippets are untrusted data. Consumer UI/report layers must display them as untrusted; model prompt injection, final citations and content authenticity require further work.
- URL checks here are **metadata-only**. They are *not* an SSRF defense. A separate actual fetch boundary must revalidate DNS, IP ranges, redirects, response size and every connection; no URL is fetched by this module.
- Live SearXNG/DDG availability, rate limits, full source provenance, deep research reasoning (#43), user UI, persistence, Owner approval and real provider performance are not verified.

## Verification
`cd core && uv run pytest -q tests/test_research_multiquery.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Core feature #35 is `TESTING / PARTIAL_VERIFIED` only after exact PR-head GitHub CI passes. No new dependency, license or automatic permission. Main and existing open PRs stay unmodified.
