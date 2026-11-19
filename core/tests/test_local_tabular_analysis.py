"""Actual local tabular analytics, strict CSV validation and no side effects."""
from __future__ import annotations

import pytest

from aura_core.data_analysis.tabular import parse_csv_table


def test_parse_numeric_and_grouped_real_csv():
    data = "region,amount,comment\nDE,10,paid\nFR,7,paid\nDE,12,paid\nFR,,missing\n"
    table = parse_csv_table(data)
    assert table.columns == ("region", "amount", "comment")
    assert len(table.rows) == 4
    total = table.numeric_summary(column="amount")
    assert total["sum"] == 29.0
    assert total["mean"] == pytest.approx(29 / 3)
    assert total["missing_count"] == 1
    assert total["inferential_claim"] is False
    groups = table.grouped_summary(group_column="region", numeric_column="amount")
    assert [r["group"] for r in groups] == ["DE", "FR"]
    assert groups[0]["mean"] == 11
    assert groups[1]["missing_count"] == 1
    assert all(row["untrusted_input"] for row in groups)


def test_quoted_csv_and_no_formula_execution():
    table = parse_csv_table('label,value\n"untrusted, text",2\n"=cmd|/C|calc",3\n')
    assert table.rows[0] == ("untrusted, text", "2")
    assert table.rows[1][0] == "=cmd|/C|calc"
    assert table.numeric_summary(column="value")["sum"] == 5.0


def test_empty_data_rows_have_no_invented_mean():
    table = parse_csv_table("value\n")
    result = table.numeric_summary(column="value")
    assert result["rows"] == 0
    assert result["mean"] is None
    assert result["sum"] is None


@pytest.mark.parametrize("bad", [
    "", "a,a\n1,2", "a,b\n1", "a,b\n1,2,3", "\x00",
    "header\n" + "x\n" * 10001, "a\n" + ("z" * 4001),
    '"unterminated\nword',
])
def test_csv_invalid_inputs_fail_closed(bad):
    with pytest.raises(ValueError):
        parse_csv_table(bad)


def test_group_bound_and_nonfinite_numeric_values_fail_closed():
    table = parse_csv_table("group,num\nA,1\nB,2\nC,3")
    with pytest.raises(ValueError, match="group"):
        table.grouped_summary(group_column="group", numeric_column="num",
                              max_groups=2)
    table = parse_csv_table("group,num\nA,NaN")
    with pytest.raises(ValueError, match="finite"):
        table.numeric_summary(column="num")
    with pytest.raises(ValueError):
        table.grouped_summary(group_column="group", numeric_column="num",
                              max_groups=True)


def test_text_numeric_column_is_not_silently_coerced():
    table = parse_csv_table("value\ntwelve")
    with pytest.raises(ValueError):
        table.numeric_summary(column="value")


def test_empty_columns_and_unknown_header_are_not_read():
    table = parse_csv_table("a,b\n1,2")
    with pytest.raises(ValueError):
        table.numeric_summary(column="unknown")
    with pytest.raises(ValueError):
        table.grouped_summary(group_column="a", numeric_column="a")


def test_xlsx_export_is_literal_and_formula_injection_resistant():
    import io
    from xml.etree import ElementTree
    from zipfile import ZipFile
    from aura_core.data_analysis.tabular import export_xlsx_formula_literal

    table = parse_csv_table("name,payload\nAlice,=2+2\nBob,+SUM(1;2)\n")
    artifact = export_xlsx_formula_literal(table)
    assert artifact[:2] == b"PK"
    with ZipFile(io.BytesIO(artifact)) as z:
        assert set(z.namelist()) == {
            "[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml",
        }
        document = ElementTree.fromstring(z.read("xl/worksheets/sheet1.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert document.findall(".//x:f", ns) == []
    cells = document.findall(".//x:c", ns)
    assert len(cells) == 6 and all(c.get("t") == "inlineStr" for c in cells)
    assert [c.find("x:is/x:t", ns).text for c in cells] == [
        "name", "payload", "Alice", "=2+2", "Bob", "+SUM(1;2)",
    ]


def test_xlsx_export_escapes_markup_without_mutating_cells():
    import io
    from xml.etree import ElementTree
    from zipfile import ZipFile
    from aura_core.data_analysis.tabular import export_xlsx_formula_literal

    table = parse_csv_table('name\n" <unsafe&> "\n')
    with ZipFile(io.BytesIO(export_xlsx_formula_literal(table))) as z:
        document = ElementTree.fromstring(z.read("xl/worksheets/sheet1.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert [c.find("x:is/x:t", ns).text for c in document.findall(".//x:c", ns)] == [
        "name", " <unsafe&> ",
    ]


def test_xlsx_export_rejects_controls_and_bad_dimensions():
    from aura_core.data_analysis.tabular import LocalTable, export_xlsx_formula_literal

    with pytest.raises(ValueError, match="XML character"):
        export_xlsx_formula_literal(LocalTable(("safe",), (("\x01",),)))
    with pytest.raises(ValueError, match="dimensions"):
        export_xlsx_formula_literal(LocalTable(tuple("c" + str(i) for i in range(33)), ()))
    with pytest.raises(ValueError, match="width"):
        export_xlsx_formula_literal(LocalTable(("a", "b"), (("one",),)))
    with pytest.raises(ValueError, match="cell exceeds"):
        export_xlsx_formula_literal(LocalTable(("a",), (("x" * 4001,),)))
