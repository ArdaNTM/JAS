"""Real registry wiring with fail-closed HTTP/Gateway execution checks."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.capability_center import FeatureCatalog, router
from aura_core.kernel.capabilities import (
    CapabilityDefinition, CapabilityRegistry, ProviderType, CapabilityCategory,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry


ROOT = Path(__file__).resolve().parents[2]
BEARER = "local-feature-center-testing-token-32-chars"


class OfflineTool:
    def __init__(self) -> None:
        self.calls = 0

    async def list_tools(self):
        return (MCPTool("read_snapshot", "Read test snapshot",
                        {"type": "object", "properties": {}, "additionalProperties": False}),)

    async def call_tool(self, name, arguments=None):
        self.calls += 1
        return {"snapshot": "authorized", "tool": name}


def configured_center():
    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    center = FeatureCatalog()
    center.register(services=services, capabilities=caps, providers=providers)
    tool = OfflineTool()
    descriptor = ServiceDefinition(
        name="governed_test_read", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities={"demo.safe.read"},
    )
    services.register(descriptor, tool)
    providers.register(ProviderDefinition(
        provider_id="aura.test.safe-read", name="Test-only read provider",
        version="1.0.0", service_id=descriptor.service_id,
    ), tool)
    caps.register(CapabilityDefinition(
        capability_id="demo.safe.read", name="Test-only safe read",
        version="1.0.0", description="Authorized read",
        provider_id="aura.test.safe-read", provider_type=ProviderType.MCP,
        category=CapabilityCategory.DIAGNOSTICS,
        tool_name="read_snapshot", risk_level="low",
        required_permissions=frozenset({"demo.safe.read"}),
    ))
    permissions = PermissionEngine(caps)
    gateway = MCPGateway(caps, providers, permissions)
    app = FastAPI()
    app.state.http_bearer_token = BEARER
    app.state.http_principal_id = "local_owner"
    app.state.feature_catalog = center
    app.state.kernel = SimpleNamespace(
        capability_registry=caps,
        provider_registry=providers,
        permission_engine=permissions,
        service_registry=services,
    )
    app.state.mcp_gateway = gateway
    app.include_router(router)
    return TestClient(app), center, caps, permissions, tool


def headers():
    return {"Authorization": "Bearer " + BEARER}


def test_pinned_index_is_exactly_canonical_117_names_and_phases():
    catalog = FeatureCatalog()
    tracker = json.loads((ROOT / "docs/22_IMPLEMENTATION/AURA_FEATURE_TRACKER.json").read_text("utf-8"))
    assert [(f["id"], f["name"], f["phase"]) for f in catalog.features] == [
        (f["id"], f["name"], f["phase"]) for f in tracker["features"]
    ]


def test_all_117_sources_registered_as_nonexecuting_metadata_and_gateway_tools_separate():
    client, center, caps, permissions, tool = configured_center()
    sources = [rec for rec in caps.records()
               if rec.definition.capability_id.startswith("aura.feature.")]
    assert len(sources) == 117
    assert all(not rec.available and not rec.healthy for rec in sources)
    assert all(rec.definition.provider_type is ProviderType.CORE for rec in sources)
    assert len(permissions.audit_records()) == 0
    response = client.get("/api/capabilities/center", headers=headers())
    assert response.status_code == 200
    data = response.json()
    assert data["feature_count"] == 117
    assert len(data["features"]) == 117
    assert data["features"][0]["runtime_status"] == "metadata_only"
    assert data["tools"] == [{
        "capability_id": "demo.safe.read",
        "tool_name": "read_snapshot", "provider_id": "aura.test.safe-read",
        "risk_level": "low", "category": "diagnostics",
        "gateway_registered": True, "authorization": "required_at_dispatch",
    }]
    assert tool.calls == 0


def test_missing_bearer_and_source_only_invocation_never_run():
    client, _center, _caps, _engine, tool = configured_center()
    assert client.get("/api/capabilities/center").status_code == 401
    body = {"capability_id": "aura.feature.001", "resource_scope": "local_default",
            "arguments": {}}
    assert client.post("/api/capabilities/center/invoke", json=body).status_code == 401
    assert client.post("/api/capabilities/center/invoke", json=body,
                       headers=headers()).status_code == 404
    forged = dict(body, principal_id="attacker")
    assert client.post("/api/capabilities/center/invoke", json=forged,
                       headers=headers()).status_code == 422
    assert tool.calls == 0


def test_existing_mcp_tool_deny_by_default_then_separately_authorized():
    client, _center, _caps, engine, tool = configured_center()
    body = {"capability_id": "demo.safe.read", "resource_scope": "local_default",
            "arguments": {}}
    denied = client.post("/api/capabilities/center/invoke", json=body, headers=headers())
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"
    assert tool.calls == 0
    engine.add_policy(PermissionPolicy(
        policy_id="explicit-owner-read-test",
        policy_version="1.0.0", principal_id="local_owner",
        capability_id="demo.safe.read", operation_id="demo.safe.read",
        resource_scope="local_default", authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    allowed = client.post("/api/capabilities/center/invoke", json=body, headers=headers())
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "executed"
    assert tool.calls == 1
    forged = client.post("/api/capabilities/center/invoke",
                         json=dict(body, resource_scope="another-tenant"), headers=headers())
    assert forged.status_code == 200 and forged.json()["status"] == "denied"
    assert tool.calls == 1


def test_bad_json_tool_schema_and_unknown_mcp_do_not_dispatch():
    client, _center, _caps, engine, tool = configured_center()
    body = {"capability_id": "demo.safe.read", "resource_scope": "local_default",
            "arguments": {"extra": "reject"}}
    engine.add_policy(PermissionPolicy(
        policy_id="explicit-owner-read",
        policy_version="1.0.0", principal_id="local_owner",
        capability_id="demo.safe.read", operation_id="demo.safe.read",
        resource_scope="local_default", authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    invalid_schema = client.post("/api/capabilities/center/invoke", json=body,
                                 headers=headers())
    assert invalid_schema.status_code == 200
    assert invalid_schema.json()["status"] == "denied"
    missing = client.post("/api/capabilities/center/invoke",
                          json=dict(body, capability_id="unregistered.tool"),
                          headers=headers())
    assert missing.status_code == 404
    assert tool.calls == 0


def test_center_get_200_from_core_cwd_with_string_category_metadata(monkeypatch):
    """Reproduces .value AttributeError when a live MCP uses a plain str.

    CapabilityDefinition is a dataclass: category annotations do not coerce
    categories. External/legacy registrations may supply their wire value.
    A GET request must never invoke a provider or grant permissions.
    """
    monkeypatch.chdir(ROOT / "core")
    client, center, caps, engine, tool = configured_center()
    caps.register(CapabilityDefinition(
        capability_id="demo.legacy.read", name="Legacy MCP category",
        version="1.0.0", description="Legacy string-backed category",
        provider_id="aura.test.safe-read", provider_type=ProviderType.MCP,
        category="diagnostics", tool_name="read_snapshot",
        risk_level="low", required_permissions=frozenset({"demo.legacy.read"}),
    ))
    response = client.get("/api/capabilities/center", headers=headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_count"] == 117
    assert len(payload["features"]) == 117
    assert {item["capability_id"]: item["category"] for item in payload["tools"]} == {
        "demo.safe.read": "diagnostics", "demo.legacy.read": "diagnostics",
    }
    assert tool.calls == 0
    assert engine.audit_records() == ()


def test_invalid_category_metadata_does_not_promote_tool_to_available():
    client, _center, caps, _engine, tool = configured_center()
    caps.register(CapabilityDefinition(
        capability_id="demo.malformed.read", name="Malformed MCP category",
        version="1.0.0", description="Cannot infer available UI category",
        provider_id="aura.test.safe-read", provider_type=ProviderType.MCP,
        category="unsupported-category", tool_name="read_snapshot",
        risk_level="low", required_permissions=frozenset({"demo.malformed.read"}),
    ))
    response = client.get("/api/capabilities/center", headers=headers())
    assert response.status_code == 200
    malformed = next(item for item in response.json()["tools"]
                     if item["capability_id"] == "demo.malformed.read")
    assert malformed["gateway_registered"] is False
    assert malformed["category"] == "unknown"
    assert tool.calls == 0


def test_center_cwd_does_not_control_117_index_resolution(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client, _center, _caps, _engine, tool = configured_center()
    response = client.get("/api/capabilities/center", headers=headers())
    assert response.status_code == 200
    assert len(response.json()["features"]) == 117
    assert tool.calls == 0
