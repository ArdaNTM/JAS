# Research provenance — feature #36, bounded untrusted evidence

`MCPResearchSource.search_with_evidence` wraps **one existing MCP Gateway search call**, preserving its authorization decision and returning a bounded source-identity projection only when the Gateway allowed the call. The read-only `collect_search_evidence` helper accepts the provider's dictionary or MCP `structuredContent`, deduplicates canonical HTTP(S) URLs, and provides deterministic SHA-256 identities for URL and search-engine snippet.

These fields are **untrusted search-engine observations**. Neither page retrieval nor source authenticity is proven by the hash, URL validation, text of a snippet, or an allowed Gateway request. A hostname can resolve to a private address; URL filtering here is **not** an SSRF protection mechanism and must never authorize a later fetch. Existing public-web fetch policy and network controls remain separate.

The projection deliberately parses no arbitrary serialized MCP text, never follows URL redirects, and returns no evidence from denied/deferred Gateway calls. Invalid credentialed/local literal URLs are dropped. No new capability, policy, external API, dependency or UI route is introduced.

Scope limitation: Feature #36 (source verification) is **not complete**. Trust assessment requires independently retrieved source content, dated provenance, publisher/integrity checks, real DNS/redirect egress enforcement and authorized user review. Multi-source contradiction analysis is also not asserted.

Test: `cd core && uv run pytest -q tests/test_research_source_evidence.py` plus full Core Assurance and Release Lock.
