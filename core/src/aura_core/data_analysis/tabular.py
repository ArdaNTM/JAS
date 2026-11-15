"""Read-only, dependency-free CSV parsing and grouped numeric summaries.

The caller must supply already-authorized CSV bytes as a decoded string.
No filesystem read/write, network fetch, formula execution, or SQL is performed.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
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
