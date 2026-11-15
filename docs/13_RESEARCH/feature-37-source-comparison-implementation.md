# Feature #37 — comparison of multiple previously collected sources

**Scope:** partial feature implementation. This standard-library-only module
(`aura_core.research.source_comparison`) compares already collected, explicit
`(source_id, claim_key, value)` observations.

It reports `SINGLE_SOURCE`, `AGREEING_LITERAL`, or
`DIVERGENT_LITERAL_REVIEW`; **none** proves real-world factual truth.
Source identifiers must represent independent origins assigned at the
authorized retrieval boundary; the function cannot verify that independence.
Every result is `untrusted=True`, `external_verified=False`.

The module is deterministic, offline, side-effect free, capped at 300 claims,
40 sources and 60 keys, detects contradictory duplicate source entries, and
returns bounded text previews and SHA-256 claim fingerprints. It does not
perform web requests, assign permissions, update memory, invoke a model, or
bypass MCP Gateway. Integrating it into authorized research workflows,
publisher authenticity verification, date-aware comparison and human review
remain outstanding. Do not mark feature #37 COMPLETED.

Run `cd core && uv run pytest -q tests/test_research_source_comparison.py`
and the whole `AURA Core Assurance` / release-lock workflow.
