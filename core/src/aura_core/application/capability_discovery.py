"""Safe runtime capability discovery.

Discovery produces proposals from already-connected providers. It never loads
arbitrary Python code, installs packages, or grants permission to execute tools.
Approval registers metadata only; MCPGateway remains the execution boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)


_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.-]+)?$")
_ALLOWED_CATEGORIES = {item.value: item for item in CapabilityCategory}


@dataclass(frozen=True, slots=True)
class CapabilityProposal:
    proposal_id: str
    capability_id: str
    name: str
    version: str
    description: str
    provider_id: str
    tool_name: str
    category: CapabilityCategory
    input_schema: dict[str, Any]
    requires_permissions: frozenset[str]
    approved: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "provider_id": self.provider_id,
            "tool_name": self.tool_name,
            "category": self.category.value,
            "input_schema": self.input_schema,
            "requires_permissions": sorted(self.requires_permissions),
            "approved": self.approved,
        }


class DynamicCapabilityDiscovery:
    """Validate tool manifests and register metadata only after approval."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry
        self._proposals: dict[str, CapabilityProposal] = {}

    def discover_mcp_tools(
        self,
        provider_id: str,
        tools: list[dict[str, Any]],
        *,
        category: str = "research",
        required_permissions: frozenset[str] = frozenset({"internet.search"}),
    ) -> tuple[CapabilityProposal, ...]:
        if not _ID.fullmatch(provider_id):
            raise ValueError("Invalid provider_id")
        selected_category = _ALLOWED_CATEGORIES.get(category)
        if selected_category is None:
            raise ValueError("Unsupported capability category")
        if len(tools) > 128:
            raise ValueError("Provider manifest exceeds 128 tools")

        proposals: list[CapabilityProposal] = []
        for item in tools:
            if not isinstance(item, dict):
                raise ValueError("Each tool manifest must be an object")
            name = item.get("name")
            description = item.get("description", "")
            schema = item.get("inputSchema", {"type": "object"})
            version = str(item.get("version", "1.0.0"))
            if not isinstance(name, str) or not _ID.fullmatch(name):
                raise ValueError("Tool name is invalid")
            if not isinstance(description, str) or len(description) > 2000:
                raise ValueError("Tool description must be at most 2000 characters")
            if not _VERSION.fullmatch(version):
                raise ValueError("Tool version must be semantic major.minor.patch")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ValueError("Tool inputSchema must be a JSON object schema")
            if len(repr(schema)) > 16_000:
                raise ValueError("Tool input schema is too large")
            capability_id = f"mcp.{provider_id}.{name}"
            proposal_id = f"{provider_id}:{name}:{version}"
            proposal = CapabilityProposal(
                proposal_id=proposal_id,
                capability_id=capability_id,
                name=name,
                version=version,
                description=description,
                provider_id=provider_id,
                tool_name=name,
                category=selected_category,
                input_schema=dict(schema),
                requires_permissions=frozenset(required_permissions),
            )
            existing = self._proposals.get(proposal_id)
            if existing is not None and existing != proposal:
                raise ValueError(f"Conflicting proposal: {proposal_id}")
            self._proposals[proposal_id] = proposal
            proposals.append(proposal)
        return tuple(proposals)

    def proposals(self) -> tuple[CapabilityProposal, ...]:
        return tuple(self._proposals[key] for key in sorted(self._proposals))

    def approve(self, proposal_id: str) -> CapabilityProposal:
        try:
            proposal = self._proposals[proposal_id]
        except KeyError as exc:
            raise KeyError(f"Unknown capability proposal: {proposal_id}") from exc
        if proposal.approved:
            return proposal

        definition = CapabilityDefinition(
            capability_id=proposal.capability_id,
            name=proposal.name,
            version=proposal.version,
            description=proposal.description or f"Discovered MCP tool {proposal.tool_name}",
            provider_id=proposal.provider_id,
            provider_type=ProviderType.MCP,
            category=proposal.category,
            required_permissions=proposal.requires_permissions,
        )
        # This only adds metadata. Provider connection, tool dispatch and
        # permission checks still happen in the existing registries/Gateway.
        self._registry.register(definition)
        approved = CapabilityProposal(
            proposal_id=proposal.proposal_id,
            capability_id=proposal.capability_id,
            name=proposal.name,
            version=proposal.version,
            description=proposal.description,
            provider_id=proposal.provider_id,
            tool_name=proposal.tool_name,
            category=proposal.category,
            input_schema=proposal.input_schema,
            requires_permissions=proposal.requires_permissions,
            approved=True,
        )
        self._proposals[proposal_id] = approved
        return approved
