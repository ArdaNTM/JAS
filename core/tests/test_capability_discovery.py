from aura_core.application.capability_discovery import DynamicCapabilityDiscovery
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.services import ServiceRegistry


def test_discovery_creates_proposal_but_does_not_register_until_approval() -> None:
    registry = CapabilityRegistry(ServiceRegistry())
    discovery = DynamicCapabilityDiscovery(registry)
    proposals = discovery.discover_mcp_tools(
        "new-provider",
        [{
            "name": "search",
            "description": "Search public sources",
            "version": "1.0.0",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }],
    )

    assert len(proposals) == 1
    assert registry.records() == ()
    approved = discovery.approve(proposals[0].proposal_id)
    assert approved.approved is True
    record = registry.resolve("mcp.new-provider.search")
    assert record.definition.provider_id == "new-provider"
    assert "internet.search" in record.definition.required_permissions


def test_discovery_rejects_invalid_manifests() -> None:
    discovery = DynamicCapabilityDiscovery(CapabilityRegistry(ServiceRegistry()))
    try:
        discovery.discover_mcp_tools("bad provider", [{"name": "run arbitrary code"}])
    except ValueError as exc:
        assert "provider_id" in str(exc)
    else:
        raise AssertionError("Invalid provider id must be rejected")

    try:
        discovery.discover_mcp_tools("provider", [{"name": "tool", "inputSchema": {"type": "string"}}])
    except ValueError as exc:
        assert "JSON object schema" in str(exc)
    else:
        raise AssertionError("Invalid tool schema must be rejected")


def test_discovery_requires_explicit_approval_and_is_idempotent_after_approval() -> None:
    registry = CapabilityRegistry(ServiceRegistry())
    discovery = DynamicCapabilityDiscovery(registry)
    proposal = discovery.discover_mcp_tools("provider", [{"name": "lookup"}])[0]
    assert discovery.proposals()[0].approved is False
    assert discovery.approve(proposal.proposal_id).approved is True
    assert discovery.approve(proposal.proposal_id).approved is True
