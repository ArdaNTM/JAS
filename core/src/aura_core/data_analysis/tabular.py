"""Read-only, dependency-free CSV parsing and grouped numeric summaries.

The caller must supply already-authorized CSV bytes as a decoded string.
No filesystem read/write, network fetch, formula execution, or SQL is performed.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from itertools import chain
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from typing import Any

_MAX_CHARS = 2_000_000
_MAX_ROWS = 10_000
_MAX_COLS = 32
_MAX_CELL_CHARS = 4_000


def _column_index(columns: tuple[str, ...], name: str) -> int:
    if type(name) is not str or name not in columns:
        raise ValueError("column not found")
    return columns.index(name)


def _as_finite_float(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        parsed = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("numeric column contains nonnumeric value") from exc
    if not math.isfinite(parsed) or abs(parsed) > 1e100:
        raise ValueError("numeric value is not finite and bounded")
    return parsed


@dataclass(frozen=True, slots=True)
class LocalTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def numeric_summary(self, *, column: str) -> dict[str, Any]:
        idx = _column_index(self.columns, column)
        numbers = [_as_finite_float(row[idx]) for row in self.rows]
        present = [value for value in numbers if value is not None]
        return {
            "column": column, "rows": len(self.rows),
            "non_null_count": len(present),
            "missing_count": len(numbers) - len(present),
            "sum": math.fsum(present) if present else None,
            "mean": math.fsum(present) / len(present) if present else None,
            "minimum": min(present) if present else None,
            "maximum": max(present) if present else None,
            "untrusted_input": True,
            "inferential_claim": False,
        }

    def grouped_summary(
        self, *, group_column: str, numeric_column: str,
        max_groups: int = 100,
    ) -> list[dict[str, Any]]:
        if type(max_groups) is not int or not 1 <= max_groups <= 100:
            raise ValueError("max_groups must be an integer 1..100")
        gi, ni = (
            _column_index(self.columns, group_column),
            _column_index(self.columns, numeric_column),
        )
        if gi == ni:
            raise ValueError("group and numeric columns must differ")
        groups: dict[str, list[float]] = {}
        missing: dict[str, int] = {}
        for row in self.rows:
            key = row[gi]
            if key not in groups:
                if len(groups) >= max_groups:
                    raise ValueError("number of groups exceeds limit")
                groups[key], missing[key] = [], 0
            val = _as_finite_float(row[ni])
            if val is None:
                missing[key] += 1
            else:
                groups[key].append(val)
        return [
            {
                "group": key, "non_null_count": len(values),
                "missing_count": missing[key],
                "mean": math.fsum(values) / len(values) if values else None,
                "untrusted_input": True,
            }
            for key, values in sorted(groups.items())
        ]


def parse_csv_table(text: str) -> LocalTable:
    """Parse at most 10,000 data rows, 32 uniquely named columns and 2 MiB."""
    if (type(text) is not str or not text or len(text) > _MAX_CHARS
            or "\x00" in text):
        raise ValueError("CSV text is empty, invalid or oversized")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
        if (not 1 <= len(header) <= _MAX_COLS or any(
                not value or len(value) > 120 or any(ord(ch) < 32 for ch in value)
                for value in header)
                or len(set(header)) != len(header)):
            raise ValueError("CSV header must have 1..32 unique valid names")
        rows: list[tuple[str, ...]] = []
        for row in reader:
            if len(rows) >= _MAX_ROWS:
                raise ValueError("CSV row limit exceeded")
            if len(row) != len(header):
                raise ValueError("CSV row width mismatch")
            if any(len(v) > _MAX_CELL_CHARS or "\x00" in v for v in row):
                raise ValueError("CSV cell exceeds limit or contains NUL")
            rows.append(tuple(row))
    except (csv.Error, UnicodeError) as exc:
        raise ValueError("invalid CSV structure") from exc
    return LocalTable(tuple(header), tuple(rows))


def export_xlsx_formula_literal(table: LocalTable) -> bytes:
    """Serialize already-authorized data as literal-only XLSX, without side effects.

    All cells are inline strings, even if they start with =, +, - or @. This
    module does not read files, authorize data access or expose download routes.
    The caller must enforce the existing AURA authorization boundary.
    """
    if type(table) is not LocalTable:
        raise ValueError("validated LocalTable required")
    columns, rows = table.columns, table.rows
    if (type(columns) is not tuple or type(rows) is not tuple
            or not 1 <= len(columns) <= _MAX_COLS
            or len(rows) > _MAX_ROWS):
        raise ValueError("XLSX table dimensions exceed limits")
    if (any(type(c) is not str or not c or len(c) > 120 for c in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError("invalid XLSX header")
    total = 0
    for n, row in enumerate(chain((columns,), rows)):
        if type(row) is not tuple or len(row) != len(columns):
            raise ValueError("XLSX row width mismatch")
        for value in row:
            if type(value) is not str or len(value) > (120 if n == 0 else _MAX_CELL_CHARS):
                raise ValueError("XLSX cell exceeds bounds")
            if any((ord(c) < 32 and c not in "\t\n\r")
                   or 0xD800 <= ord(c) <= 0xDFFF
                   or ord(c) in (0xFFFE, 0xFFFF) for c in value):
                raise ValueError("invalid XML character in XLSX cell")
            total += len(value)
            if total > _MAX_CHARS:
                raise ValueError("XLSX text budget exceeded")

    types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    book_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", book_rels)
        with archive.open("xl/worksheets/sheet1.xml", "w") as sheet:
            sheet.write((
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData>'
            ).encode("utf-8"))
            for row_no, row in enumerate(chain((columns,), rows), 1):
                sheet.write(f'<row r="{row_no}">'.encode("ascii"))
                for col_no, value in enumerate(row):
                    col = chr(65 + col_no) if col_no < 26 else "A" + chr(65 + col_no - 26)
                    cell = (
                        f'<c r="{col}{row_no}" t="inlineStr">'
                        f'<is><t xml:space="preserve">{escape(value)}</t></is></c>'
                    )
                    sheet.write(cell.encode("utf-8"))
                sheet.write(b"</row>")
            sheet.write(b"</sheetData></worksheet>")
    artifact = buffer.getvalue()
    if len(artifact) > 8_000_000:
        raise ValueError("XLSX archive exceeds output budget")
    return artifact
