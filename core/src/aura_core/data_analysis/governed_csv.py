"""Governed local CSV summaries and XLSX export, reusing canonical serializers.

CSV is caller-provided data, never a filesystem path. The existing MCPGateway
authorizes every invocation; no default policy or file/OS authority is granted.
"""
from __future__ import annotations

import base64
import hashlib
import math
from typing import Any

from aura_core.data_analysis.tabular import parse_csv_table
from aura_core.application.offline_xlsx_report import render_xlsx_report
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.provider import ProviderDefinition

_CAP = {"csv_summary": "aura.data.csv.summary",
        "csv_export_xlsx": "aura.data.csv.export"}


class GovernedCSVAnalysisMCP:
    provider_id = "aura.governed-csv-analysis"

    async def list_tools(self) -> tuple[MCPTool, ...]:
        document = {"type": "string", "minLength": 1, "maxLength": 2_000_000}
        return (
            MCPTool("csv_summary", "Numeric summary of authorized CSV body", {
                "type": "object",
                "properties": {
                    "csv_text": document,
                    "column": {"type": "string", "minLength": 1, "maxLength": 120},
                },
                "required": ["csv_text", "column"], "additionalProperties": False,
            }),
            MCPTool("csv_export_xlsx", "Safe formula-literal XLSX from local CSV", {
                "type": "object",
                "properties": {"csv_text": document},
                "required": ["csv_text"], "additionalProperties": False,
            }),
        )

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or name not in _CAP or grant.tool_name != name
            or grant.capability_id != _CAP[name] or
            type(grant.principal_id) is not str or not grant.principal_id.strip()):
            raise PermissionError("Exact Gateway grant required for CSV ingestion or export")
        from aura_core.mcp.gateway import _validate_json_schema
        args = arguments if isinstance(arguments, dict) else {}
        schemas = {item.name: item.input_schema for item in await self.list_tools()}
        _validate_json_schema(args, schemas[name])
        table = parse_csv_table(args["csv_text"])
        digest = hashlib.sha256(args["csv_text"].encode("utf-8")).hexdigest()
        if name == "csv_summary":
            return {
                "summary": table.numeric_summary(column=args["column"]),
                "source_sha256": digest, "source_authenticated": False,
                "untrusted": True,
            }
        if len(table.rows) > 999:
            raise ValueError("XLSX export budget: at most 999 CSV data rows")
        raw = render_xlsx_report(list(table.columns), [list(row) for row in table.rows])
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_sha256": digest, "media_type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "base64": base64.b64encode(raw).decode("ascii"),
            "content_length": len(raw), "formula_execution": False,
            "untrusted_input": True, "owner_approved": False,
        }


def register_governed_csv_analysis(kernel: Any, provider: GovernedCSVAnalysisMCP) -> None:
    if (kernel.service_registry is None or kernel.provider_registry is None or
        kernel.capability_registry is None):
        raise RuntimeError("Kernel must be bootstrapped")
    service = ServiceDefinition(
        name="governed_csv_analysis", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities=frozenset(_CAP.values()))
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id, name="Bounded CSV analysis and local XLSX",
        version="1.0.0", service_id=service.service_id), provider)
    for name, cap in _CAP.items():
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap, name="CSV " + name, version="1.0.0",
            description="CSV source is untrusted and caller-provided",
            provider_id=provider.provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.CODING, tool_name=name, risk_level="low"))


def scan_csv_numeric_stream(
    lines, *, numeric_column: str, max_rows: int = 500_000,
) -> dict[str, Any]:
    """Real memory-bounded CSV stream aggregation for pre-authorized text streams.

    A trusted caller owns the file descriptor; no file paths or sockets are
    opened here. Welford online variance avoids storing whole datasets.
    """
    import csv
    if type(max_rows) is not int or not 1 <= max_rows <= 500_000:
        raise ValueError("invalid streaming row budget")
    if not isinstance(numeric_column, str) or not numeric_column:
        raise ValueError("numeric column required")
    reader = csv.reader(lines, strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise ValueError("CSV header required") from exc
    if (not 1 <= len(header) <= 32 or len(set(header)) != len(header)
        or numeric_column not in header):
        raise ValueError("invalid streaming header or numeric field")
    idx = header.index(numeric_column)
    count = 0
    mean = 0.0
    m2 = 0.0
    try:
        for row in reader:
            if len(row) != len(header) or any(len(c) > 4096 for c in row):
                raise ValueError("invalid streaming row")
            if count >= max_rows:
                raise ValueError("stream row budget exceeded")
            try:
                value = float(row[idx])
            except (ValueError, OverflowError) as exc:
                raise ValueError("stream contains invalid numeric value") from exc
            if not math.isfinite(value) or abs(value) > 1e100:
                raise ValueError("stream contains unbounded numeric value")
            count += 1
            delta = value - mean
            mean += delta / count
            m2 += delta * (value - mean)
            if not math.isfinite(m2):
                raise ValueError("stream variance overflow")
    except csv.Error as exc:
        raise ValueError("malformed streaming CSV") from exc
    if count < 1:
        raise ValueError("stream requires observations")
    return {
        "count": count, "mean": mean,
        "sample_variance": m2 / (count - 1) if count > 1 else None,
        "untrusted_input": True,
        "source_authenticated": False,
        "streaming": True,
    }
