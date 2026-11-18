"""Bounded deterministic XLSX reports from already-authorized tabular data.

Returns OOXML bytes only. No file access, macros, external links, formula cells,
network requests, MCP dispatch or implicit owner consent is performed here.
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

_MAX_ROWS = 1_000
_MAX_COLUMNS = 32
_MAX_TEXT = 4096
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_TEXT = 256_000
_XMLNS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKGENS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENTNS = "http://schemas.openxmlformats.org/package/2006/content-types"
_BAD_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")


class XLSXReportError(ValueError):
    """Invalid, unsafe or over-budget tabular report input."""


def _safe_text(value: object, field_name: str, *, max_size: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or len(value) > max_size:
        raise XLSXReportError(f"{field_name} must be bounded text")
    if any(
        (ord(char) < 32 and char not in "\t\r\n")
        or 0xD800 <= ord(char) <= 0xDFFF
        or ord(char) in (0xFFFE, 0xFFFF)
        for char in value
    ):
        raise XLSXReportError(f"{field_name} contains invalid XML characters")
    return value


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(value: object, location: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return f'<c r="{location}" t="b"><v>{int(value)}</v></c>'
    if type(value) is int:
        if abs(value) > 999_999_999_999_999:
            raise XLSXReportError("integer exceeds 15-digit spreadsheet precision")
        return f'<c r="{location}"><v>{value}</v></c>'
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > 999_999_999_999_999:
            raise XLSXReportError("float must be finite and within spreadsheet range")
        return f'<c r="{location}"><v>{format(value, ".15g")}</v></c>'
    if isinstance(value, str):
        text = escape(_safe_text(value, "cell"))
        # t=inlineStr guarantees formula-looking input remains literal text.
        return f'<c r="{location}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    raise XLSXReportError("cell type must be str, int, float, bool or None")


def _zip_member(filename: str, value: str) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    return info, value.encode("utf-8")


def render_xlsx_report(
    headers: list[str] | tuple[str, ...],
    rows: list[list[object] | tuple[object, ...]] | tuple[list[object] | tuple[object, ...], ...],
    *,
    sheet_name: str = "AURA Report",
) -> bytes:
    """Build a single-sheet, read-only OOXML workbook; never write to disk.

    Inputs must already have passed the application's authorization boundary.
    This utility does not access arbitrary paths or accept formula XML.
    """
    if not isinstance(headers, (list, tuple)) or not 1 <= len(headers) <= _MAX_COLUMNS:
        raise XLSXReportError("headers must contain 1..32 columns")
    checked_headers = [_safe_text(value, "header", max_size=128) for value in headers]
    if any(not h.strip() for h in checked_headers):
        raise XLSXReportError("headers may not be blank")
    if len({h.casefold() for h in checked_headers}) != len(checked_headers):
        raise XLSXReportError("duplicate header")
    if not isinstance(rows, (list, tuple)) or len(rows) > _MAX_ROWS:
        raise XLSXReportError("rows must be a bounded list or tuple")
    name = _safe_text(sheet_name, "sheet name", max_size=31)
    if not name or name != name.strip() or name.startswith("'") or name.endswith("'") or _BAD_SHEET_NAME.search(name):
        raise XLSXReportError("invalid Excel sheet name")

    sheet_rows: list[str] = []
    text_budget = sum(len(header) for header in checked_headers)
    for row_index, row in enumerate((checked_headers, *rows), start=1):
        if not isinstance(row, (list, tuple)) or len(row) != len(checked_headers):
            raise XLSXReportError("row has unexpected column count")
        text_budget += sum(len(item) for item in row if isinstance(item, str))
        if text_budget > _MAX_TOTAL_TEXT:
            raise XLSXReportError("input text exceeds total budget")
        cells = "".join(_cell(item, f"{_column_name(col_index)}{row_index}")
                        for col_index, item in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    worksheet = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{_XMLNS}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<workbook xmlns="{_XMLNS}" xmlns:r="{_RELNS}">'
        f'<sheets><sheet name={quoteattr(name)} sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    content_types = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Types xmlns="{_CONTENTNS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_rels = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{_PKGENS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_rels = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{_PKGENS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    members = (
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", root_rels),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", workbook_rels),
        ("xl/worksheets/sheet1.xml", worksheet),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for filename, value in members:
            info, encoded = _zip_member(filename, value)
            archive.writestr(info, encoded)
    result = buffer.getvalue()
    if len(result) > _MAX_FILE_BYTES:
        raise XLSXReportError("XLSX output exceeds byte budget")
    return result
