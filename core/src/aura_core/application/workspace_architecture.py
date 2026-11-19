"""Bounded multi-file architecture graph for already-authorized source snapshots.

Never traverses disk, fetches URLs, imports project code or executes it.
Non-Python language extraction is lexical/heuristic, not a compiler. Results
cannot be interpreted as an independent security verdict.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_core.application.code_insight import inspect_python_source
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.provider import ProviderDefinition

_CAP = "aura.coding.architecture.inspect"
_ALLOWED = {"py": "python", "java": "java", "kt": "kotlin", "ts": "typescript"}
_PATH = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]{0,199}\Z", re.ASCII)
_IMPORT = re.compile(
    r"(?m)^\s*(?:import\s+(?:static\s+)?([\w.*]+)\s*;?"
    r"|from\s+['\"]([\w./@-]+)['\"]\s*;?"
    r"|import\s+.*?\s+from\s+['\"]([\w./@-]+)['\"]\s*;?)"
)
_CLASS = re.compile(r"\b(?:class|interface|enum|object)\s+([A-Za-z_$][\w$]*)")
_CALL_RISKS = frozenset({"Runtime.exec", "ProcessBuilder", "eval(", "exec(", "child_process"})


@dataclass(frozen=True, slots=True)
class ArchitectureNode:
    path: str
    language: str
    sha256: str
    imported: tuple[str, ...]
    public_symbols: tuple[str, ...]
    heuristic_risk_markers: tuple[str, ...]


def inspect_source_workspace(sources: Mapping[str, str]) -> dict[str, Any]:
    """Build a capped deterministic dependency graph over supplied source bytes."""
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 40:
        raise ValueError("1..40 exact source snapshots required")
    if sum(len(s) for s in sources.values() if isinstance(s, str)) > 900_000:
        raise ValueError("workspace source budget exceeded")
    nodes: list[ArchitectureNode] = []
    for path, source in sorted(sources.items()):
        if (type(path) is not str or not _PATH.fullmatch(path)
                or ".." in path.split("/") or path.startswith("/")
                or type(source) is not str or not source or "\x00" in source):
            raise ValueError("invalid source path/body")
        ext = path.rsplit(".", 1)[-1]
        if ext not in _ALLOWED:
            raise ValueError("unsupported language")
        try:
            raw = source.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid source encoding") from exc
        if len(raw) > 262_144:
            raise ValueError("source file exceeds limit")
        if ext == "py":
            module_id = path[:-3].replace("/", ".")
            if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,9}", module_id):
                raise ValueError("invalid Python module path")
            report = inspect_python_source(source, module_id=module_id)
            imported = tuple(report.imports)
            symbols = tuple(item.qualified_name for item in report.symbols)
            risks = tuple(sorted({item.review_category for item in report.call_findings}))
        else:
            imported = tuple(sorted({
                part for hit in _IMPORT.finditer(source) for part in hit.groups() if part
            }))[:200]
            symbols = tuple(sorted(set(_CLASS.findall(source))))[:300]
            risks = tuple(sorted(marker for marker in _CALL_RISKS if marker in source))
        nodes.append(ArchitectureNode(
            path, _ALLOWED[ext], hashlib.sha256(raw).hexdigest(),
            imported, symbols, risks,
        ))
    known = {
        node.path.rsplit(".", 1)[0].replace("/", "."): node.path
        for node in nodes
    }
    # Only exact module-name references become edges. Unknown imports stay unresolved.
    edges = sorted({
        (node.path, known[module])
        for node in nodes
        for module in node.imported
        if module in known and known[module] != node.path
    })
    return {
        "nodes": [vars(node) if hasattr(node, "__dict__") else {
            "path": node.path, "language": node.language, "sha256": node.sha256,
            "imports": list(node.imported), "symbols": list(node.public_symbols),
            "heuristic_risk_markers": list(node.heuristic_risk_markers),
        } for node in nodes],
        "edges": [{"source": a, "dependency": b} for a, b in edges],
        "untrusted": True, "code_executed": False,
        "compiler_verified": False, "security_verified": False,
        "trusted_repository_retrieval_verified": False,
    }


class GovernedArchitectureMCP:
    """Source mapping is provisioned by authenticated bootstrap, not user args."""
    provider_id = "aura.governed-architecture"

    def __init__(self, snapshots_by_principal: Mapping[str, Mapping[str, str]]) -> None:
        if not snapshots_by_principal:
            raise ValueError("trusted source inventory required")
        self._snapshots = {
            principal: dict(files)
            for principal, files in snapshots_by_principal.items()
        }
        for principal, files in self._snapshots.items():
            if not isinstance(principal, str) or not principal.strip():
                raise ValueError("invalid principal")
            inspect_source_workspace(files)  # validate at bootstrap

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool("architecture_inspect", "Inspect bounded authorized workspace", {
            "type": "object", "properties": {}, "additionalProperties": False,
        }),)

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or grant.tool_name != "architecture_inspect"
            or grant.capability_id != _CAP or name != "architecture_inspect"
            or grant.principal_id not in self._snapshots):
            raise PermissionError("Exact Gateway grant and bounded source roster required")
        if arguments not in (None, {}):
            raise ValueError("user-supplied path or source override forbidden")
        return inspect_source_workspace(self._snapshots[grant.principal_id])


def register_governed_architecture(kernel: Any, provider: GovernedArchitectureMCP) -> None:
    if (kernel.service_registry is None or kernel.provider_registry is None or
        kernel.capability_registry is None):
        raise RuntimeError("Kernel must be bootstrapped")
    service = ServiceDefinition(
        name="governed_architecture", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities=frozenset({_CAP}))
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id, name="Read-only bounded source architecture",
        version="1.0.0", service_id=service.service_id), provider)
    kernel.capability_registry.register(CapabilityDefinition(
        capability_id=_CAP, name="Static architecture report", version="1.0.0",
        description="Scoped, untrusted source dependency graph",
        provider_id=provider.provider_id, provider_type=ProviderType.MCP,
        category=CapabilityCategory.CODING, tool_name="architecture_inspect",
        risk_level="low"))
