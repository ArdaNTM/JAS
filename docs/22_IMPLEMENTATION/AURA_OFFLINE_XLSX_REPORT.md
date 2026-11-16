# Bounded offline XLSX reporting — feature #112 (partial)

Implementation: core/src/aura_core/application/offline_xlsx_report.py. This is a pure OOXML-byte generator, not an MCP tool, provider, or file writer. Caller must supply already-authorized tabular data. No extra dependencies or network APIs.

## Contract
- render_xlsx_report(headers, rows, sheet_name='AURA Report') -> bytes
- One worksheet, 1–32 unique nonblank headers, up to 1,000 rows, 4,096 chars/cell and 256,000 chars aggregate text. Produced archive must be <=2 MiB.
- Header and text values become explicit inline strings; formula-looking text remains literal without formula cells. Only finite 15-digit compatible numbers, booleans, None and strings are accepted.
- Fixed OOXML member list and ZIP metadata yield deterministic output; no embedded relationships, macros, hyperlinks, external data fetch or dynamic code execution.
- XML validity is checked before serialization; invalid control/surrogate chars, invalid sheet names, unsupported nested objects and unsafe numeric precision fail closed.

## Use
```python
from aura_core.application.offline_xlsx_report import render_xlsx_report
data = render_xlsx_report(['Name', 'Price'], [['A', 12.5]], sheet_name='Report')
# Only an independently authorized and validated caller may write or transmit data.
```

## Tests
cd core && uv run pytest -q tests/test_offline_xlsx_report.py
cd core && uv run python scripts/verify_final_lock.py
Local isolated tests: 8 passed; Python openpyxl successfully reopened generated ZIP workbook with literal formula-like text. Full Core, Persistence and Release Lock require exact-head GitHub CI.

## Gaps
This does not include production integration with authorized result data sources, file output, template styling, PDF/DOCX/PPTX creation, real Office compatibility matrix, accessibility requirements, complex spreadsheets, large datasets, encryption, sensitive-data retention controls or Owner acceptance. Feature #112 stays TESTING/PARTIAL_VERIFIED, not COMPLETED. No extra license dependencies (Python standard library).
