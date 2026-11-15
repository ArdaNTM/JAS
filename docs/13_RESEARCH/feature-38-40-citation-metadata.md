# Features #38 and #40 — bounded academic citation normalization (partial)

The existing JAS research package now contains an offline citation reconciler
for DOI-labelled metadata already returned by an authorized research provider.
`reconcile_academic_metadata` validates size, publication year, author names,
DOI syntax and source identifiers; groups records by DOI; and flags differing
titles/authors/venues/years for human review rather than silently treating one
source as true. Up to 150 records, 50 DOI groups and 20 authors are supported.
`render_bibliography` safely escapes Markdown metacharacters and renders a
deterministic textual bibliography without live hyperlinks or fetching.

Every result is untrusted and metadata_verified=False. DOI syntax validation
is not DOI existence or Crossref/publisher verification. Source identities are
caller-supplied and require existing MCP Gateway authorization. The module
does not access the internet, modify memory, create policies, schedule work,
or perform paid/API calls.

Feature #38 academic research and #40 research report creation remain
PARTIAL: authenticated academic retrieval, source dates, citation styles,
document export, provenance attestation and E2E acceptance are not present.

Test: cd core && uv run pytest -q tests/test_academic_citations.py
Full Core Assurance and Final Release Lock are mandatory before review.
