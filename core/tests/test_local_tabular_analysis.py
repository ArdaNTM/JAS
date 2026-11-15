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
