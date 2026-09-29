"""Multi-MCP routing based on registered capabilities and tool metadata."""

from dataclasses import dataclass

from aura_core.discovery.service import ToolCandidate, ToolDiscoveryRequest, ToolDiscoveryService, ToolSelectionService
from aura_core.mcp.provider import ProviderRegistry, ProviderState


@dataclass(frozen=True, slots=True)
class MCPRoute:
    candidate: ToolCandidate
    provider_state: ProviderState


class MCPOrchestrator:
    """Selects healthy MCP routes without executing them.

    Execution must be performed later by MCPGateway, so orchestration cannot
    bypass authorization or call a provider instance.
    """

    def __init__(self, discovery: ToolDiscoveryService, providers: ProviderRegistry, selector: ToolSelectionService | None = None) -> None:
        self._discovery = discovery
        self._providers = providers
        self._selector = selector or ToolSelectionService()

    def route(self, request: ToolDiscoveryRequest) -> MCPRoute:
        candidates = tuple(candidate for candidate in self._discovery.discover(request) if self._eligible(candidate.provider_id))
        candidate = self._selector.select(candidates)
        return MCPRoute(candidate, self._providers.get(candidate.provider_id).state)

    def _eligible(self, provider_id: str) -> bool:
        record = self._providers.get(provider_id)
        return record.available and record.healthy and record.state in {ProviderState.REGISTERED, ProviderState.READY, ProviderState.RUNNING}
