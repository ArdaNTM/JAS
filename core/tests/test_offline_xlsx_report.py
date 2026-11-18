"""Format correctness, bounded inputs, and injection regressions for #112."""
import io
import math
import zipfile
import xml.etree.ElementTree as ET

import pytest

from aura_core.application.offline_xlsx_report import XLSXReportError, render_xlsx_report

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _sheet(payload: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert len(archive.namelist()) == 5
        assert len(set(archive.namelist())) == 5
        assert "xl/externalLinks/externalLink1.xml" not in archive.namelist()
        return ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))


def test_valid_ooxml_cells_and_deterministic_zip():
    args = (["Name", "Amount", "Approved", "Optional"], [["Ada & Co", 42, True, None], ["Z", 0.25, False, "line\nbreak"]])
    payload = render_xlsx_report(*args)
    assert payload.startswith(b"PK")
    assert payload == render_xlsx_report(*args)
    sheet = _sheet(payload)
    cells = {c.attrib["r"]: c for c in sheet.iter(MAIN + "c")}
    assert cells["A2"].find(".//" + MAIN + "t").text == "Ada & Co"
    assert cells["B2"].find(MAIN + "v").text == "42"
    assert cells["C2"].attrib["t"] == "b"
    assert "D2" not in cells
    assert cells["B3"].find(MAIN + "v").text == "0.25"


def test_spreadsheet_formula_injection_is_a_literal_inline_string():
    payload = render_xlsx_report(["Input"], [["=HYPERLINK(\"https://evil.example\",\"x\")"], ["+cmd|'/C calc'!A0"], ["<script>&txt"]])
    sheet = _sheet(payload)
    assert not list(sheet.iter(MAIN + "f"))
    cells = list(sheet.iter(MAIN + "c"))
    assert all(c.attrib["t"] == "inlineStr" for c in cells)
    assert any("=HYPERLINK" in (text.text or "") for text in sheet.iter(MAIN + "t"))
    assert "<script>" not in payload.decode("latin1", errors="ignore")


def test_rejects_unbounded_and_malformed_shapes():
    for headers, rows in (([], []), (["A"] * 33, []), (["A", "a"], []), (["A"], [[1, 2]]), (["A"], [1]), (["A"], [[1]] * 1001)):
        with pytest.raises(XLSXReportError):
            render_xlsx_report(headers, rows)
    with pytest.raises(XLSXReportError):
        render_xlsx_report(["A"], (item for item in [[1]]))


def test_rejects_unsafe_xml_and_sheet_names():
    for text in ("a\x00", "\ud800", "\ufffe", "x" * 4097):
        with pytest.raises(XLSXReportError):
            render_xlsx_report(["Column"], [[text]])
    for name in ("bad/name", "[x]", " spaced ", "'bad", "x" * 32, "a\x00"):
        with pytest.raises(XLSXReportError):
            render_xlsx_report(["A"], [], sheet_name=name)


def test_rejects_formula_objects_nonfinite_values_and_unsafe_number_precision():
    for item in (math.inf, math.nan, -math.inf, 10**16, 1e16, {}, [], b"data", complex(1, 2)):
        with pytest.raises(XLSXReportError):
            render_xlsx_report(["A"], [[item]])


def test_no_external_relationships_or_arbitrary_path_access():
    payload = render_xlsx_report(["File"], [["../../secrets"], ["https://test.invalid/?t=secret"]], sheet_name='Safe " data')
    sheet = _sheet(payload)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for filename in archive.namelist():
            assert not filename.startswith("/")
            assert ".." not in filename
            if filename.endswith(".rels"):
                assert b'TargetMode="External"' not in archive.read(filename)
    assert len(list(sheet.iter(MAIN + "row"))) == 3


def test_header_and_empty_row_are_valid():
    root = _sheet(render_xlsx_report(("Only",), [(None,)]))
    assert len(list(root.iter(MAIN + "row"))) == 2


def test_rejects_many_individually_valid_strings_over_total_budget():
    with pytest.raises(XLSXReportError, match="total budget"):
        render_xlsx_report(["A"], [["x" * 4096]] * 65)
