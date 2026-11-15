# Bounded offline table analytics — partial AURA feature #111

`parse_csv_table(text)` parses a caller-provided CSV string using only the Python standard library. It limits total text (2 million characters), data rows (10,000), columns (32), cell length (4,000), unique header names and per-summary group cardinality (100). Parsed rows remain immutable string data, not formula, SQL, Python or shell instructions. No file reads, downloads, storage writes or network requests are made.

`LocalTable.numeric_summary(column)` computes descriptive numeric sum/mean/min/max and missing count; `grouped_summary(group_column,numeric_column,max_groups)` computes deterministic per-group mean and count. Non-numeric, infinite, NaN and excessive magnitudes fail closed. Empty numeric samples return no invented mean. Results are marked untrusted and non-inferential. Data sent to CSV, spreadsheets or HTML in later work must be escaped at those output boundaries; formula-looking input is not executed here.

This is **not** a production analytics suite, database import service, statistical inference pipeline or chart UI. Feature #111 remains partial; file permissions, authenticated app boundary, dataset provenance, large-data streaming and realistic performance testing require further work. The module grants no capability and does not alter the PermissionEngine or MCP Gateway.

Test: `cd core && uv run pytest -q tests/test_local_tabular_analysis.py` plus complete Core Assurance and Release Lock.
