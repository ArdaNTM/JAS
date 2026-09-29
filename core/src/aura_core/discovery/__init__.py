"""Deterministic discovery and selection of registered MCP tools.

This package only produces candidates. It deliberately has no provider
instances and cannot execute a tool; execution remains MCPGateway's job.
"""

from aura_core.discovery.service import (
    ToolCandidate,
    ToolDiscoveryRequest,
    ToolDiscoveryService,
    ToolSelectionService,
)

__all__ = ["ToolCandidate", "ToolDiscoveryRequest", "ToolDiscoveryService", "ToolSelectionService"]
