# Bounded governed research dossier — feature #43 (partial, stacked on #35)

This is a **dependent** review-only slice layered on Draft PR #112 `feat/aura-gateway-multisearch-evidence`. It does not introduce a second web research provider, LLM planner, browser automation or execution authority.

## Inputs and outcome
- Caller supplies one overarching research question <=500 characters and 1..3 explicit subquestions (same bounded validation as #35). The app must already have authenticated the principal and obtained an allowed resource scope.
- `create_research_dossier` calls PR #112's `bounded_multiquery_search`, which executes each query through the existing `MCPResearchSource` and **MCPGateway.invoke**. Any denied, deferred, approval-required or malformed response aborts the entire dossier; no incomplete evidence is presented as complete.
- The dossier enumerates exact untrusted source references by subquestion, counts distinct source hostnames as a *review hint*, and explicitly flags NO_RESULTS / NEEDS_ADDITIONAL_SOURCES / SOURCE_DIVERSITY_REVIEW_REQUIRED.
- The dossier is **never** an automatically verified factual answer: `factual_claims_verified=False`, `needs_human_review=True`, `safety_status=UNTRUSTED_EVIDENCE`. Source text is not an instruction, permission or code execution request.

## Verification
`cd core && uv run pytest -q tests/test_research_dossier.py tests/test_gateway_multiquery_research.py`
`cd core && uv run python scripts/verify_final_lock.py`

All tests use a fake non-networking MCP result or (in #112 tests) the real JAS Service/Provider/Capability registries, PermissionEngine and Gateway with a mock registered provider. No live SearXNG/HTTP, paid API or unattended agent behavior is claimed.

## Acceptance / merge dependency
- Parent PR #112 must be owner-reviewed and merged first; this PR targets parent branch and inherits its source lock/test basis. Never merge automatically.
- Missing actual autonomous (governed) question decomposition, systematic real-world searching, source authentication, fact/contradiction verification, iterative research and human-approved synthesis.
- Existing local research MCP live network provider still needs independent SSRF and data-exfiltration hardening before any real-web acceptance. Hostname diversity is not publication independence and is not truth evidence.
- Feature #43 remains TESTING/PARTIAL_VERIFIED until full research behavior and production Owner acceptance, not COMPLETED.
