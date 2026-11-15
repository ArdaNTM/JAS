# Safe multisource literal comparison — partial feature #37

The existing `CrossCapabilitySynthesizer` now rejects non-JSON custom objects (including objects with user-defined `__str__`), nonfinite numeric evidence, deep/nested/cyclic payloads and oversized strings before serializing authorized provider outputs. This prevents implicit execution via `json.dumps(default=str)` and keeps tool data non-authoritative.

`compare_literal_claims` is a pure and bounded local function comparing explicit `{"claims":[{"key":"fact.key","value":"literal"}]}` results by provider ID. It reports literal agreement, literal disagreement or insufficient sources with `untrusted=true`, `fact_verified=false` and `source_independence_verified=false`. No tools, prompts, new agents, policies or network operations occur.

**Limitations:** Distinct provider IDs are not necessarily independent publications. Literal agreement does not verify claims, source credibility, recency, semantics, causal inference or truth. This is not a complete multi-source research system or independent verification agent, and does not add any MCP Gateway authorization. Real inputs must already pass the calling app's permissions.

Test: `cd core && uv run pytest -q tests/test_cross_capability_comparison.py`, full AURA Core Assurance and Release Lock.
