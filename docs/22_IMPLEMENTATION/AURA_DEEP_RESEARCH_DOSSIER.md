# Two-stage governed research dossier — feature #43 (partial)

This feature is **stacked on Draft PR #112** (feature #35: governed bounded multi-query search) and must not be merged independently. It only consumes `aura_core.research.multiquery.bounded_multiquery_search` and the existing `MCPResearchSource -> MCPGateway -> PermissionEngine` execution path. No direct HTTP, raw provider invocation, new permission, Owner approval bypass, unrestricted browsing or generated follow-up search is introduced.

## Capability contract
- An explicit immutable `ResearchDossierPlan(topic, primary_queries, verification_queries)` contains 1–3 user-provided queries in **each** of two stages. No tool content can generate the second-stage searches. Queries are unique across stages and validated before execution.
- `build_research_dossier(...)` carries the caller's authenticated principal, resource scope, risk level and separate stage/task IDs through the #35 MCP Gateway adapter. Both stages must complete and be authorized before any dossier is returned. A DENY, REQUIRE_APPROVAL, DEFER, malformed response or timeout fails the whole operation.
- Each stage retains at most 12 untrusted findings; the dossier retains at most 18 unique URLs, source/domain/provider labels, stage/query indices and raw untrusted text. No content is executed or treated as a system instruction.
- Host diversity is a visible **heuristic only** (`distinct_hosts`, `repeated_hosts`, `insufficient_source_diversity`): two hostnames do not prove source independence or factual corroboration. The dossier status is always `EVIDENCE_ONLY_NOT_FACT_CHECKED`.
- Bounded 1–120 second total timeout; sequential MCP requests preserve Gateway audit and avoid unbounded fanout.

## Security and evidence
- Tests use a fake Gateway for malformed/host duplication/timeouts and a real `MCPGateway`, `PermissionEngine`, capability/provider/service registries and fake networkless MCP provider for positive policy and default-deny proofs.
- No live SearXNG/DDG, URL fetching, authenticated web content, claim-level fact verification, LLM drafting, adversarial prompt isolation, provenance signing or owner production acceptance is claimed.
- URL metadata accepted by #35 is **not** an SSRF prevention mechanism. Future real fetches require connection-time IP/DNS/redirect validation at their own MCP capability boundary, plus size/secret logging limits.

## Test commands
`cd core && uv run pytest -q tests/test_research_dossier.py tests/test_gateway_multiquery_research.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

## Version/dependency gates
- Base: `feat/aura-gateway-multisearch-evidence` on PR #112 at initial head `dcc4efd854468eeebf66bb5ba515077281929a2a`.
- This PR should target the #112 feature branch and stay Draft until upstream accepted separately. Shared `release-manifest.final.json` includes both modules and must be regenerated on eventual integration/rebase.
- Feature #43 is `TESTING/PARTIAL_VERIFIED` **only after** exact-head CI passes. Full acceptance requires real sources, verified claim citations, host/DNS security, model evaluation and Owner-approved UI.
