# Feature #41 — read-only RSS/Atom feed delta monitoring (partial)

The existing JAS research package gains an offline parser and change detector:
`parse_feed(xml_text, feed_key)` and `detect_new_items(before, after)`.
Both operate on XML **already obtained through an authorized retrieval path**.
Neither initiates network requests, follows links, writes snapshots, schedules
tasks, or creates MCP permissions.

The parser recognizes RSS and Atom, rejects DTD declarations, input above
256 KiB, excessive XML elements and non-HTTPS/credentialed/local item URLs,
and enforces a 200-item budget. Output titles and URLs remain untrusted data.
A newly observed identity does not establish its publication date. Missing
entries are not interpreted as deletion. URL text validation does not verify
DNS records or publishers and must never authorize a subsequent fetch.

Tests: `cd core && uv run pytest -q tests/test_research_feed_monitor.py`.
Core Assurance and release-lock verification are required as well.

Limits: The feature is not COMPLETED; persisted snapshots, a user-authorized
scheduler, delivery mechanism, independent source validation and E2E tests
remain outside this PR. JAS PermissionEngine and MCP Gateway retain authority.
