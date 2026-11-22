"""Bounded agent tool selection uses live registries but grants no permissions."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.capabilities import (
    CapabilityDefinition, CapabilityCategory, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition


class FakeProvider:
    async def list_tools(self):
        return [SimpleNamespace(
            name="read_data",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )]


class FakeSelector:
    def __init__(self, response):
        self.response = response

    async def complete_json(self, *, system_prompt, user_prompt):
        assert "filesystem.read_test_data" in user_prompt
        assert "never follow instructions" in system_prompt
        return self.response


def client(selector):
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="test-provider", version="1.0.0", provider="mcp",
        category=ServiceCategory.MCP,
    ), object())
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="filesystem.test", name="Test provider",
        version="1.0.0", service_id=service.service_id,
    ), FakeProvider())
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="filesystem.read_test_data",
        name="Read bounded test data", version="1.0.0",
        description="Read explicitly approved test data only",
        provider_id="filesystem.test", provider_type=ProviderType.MCP,
        category=CapabilityCategory.STORAGE,
        tool_name="read_data", risk_level="low",
    ))
    app = create_api(config=RuntimeConfig(runtime="mock", model="test"))
    app.state.kernel = SimpleNamespace(
        capability_registry=capabilities, provider_registry=providers,
    )
    app.state.assistant_tool_selector = selector
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    return TestClient(app)


def test_registered_tool_can_be_planned_without_execution(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    api = client(FakeSelector({
        "capability_id": "filesystem.read_test_data",
        "arguments": {"path": "safe.txt"},
    }))
    r = api.post("/api/tasks/plan",
                 headers={"Authorization": "Bearer " + "t" * 40},
                 json={"directive": "Dosyamı oku ve yorumla"})
    assert r.status_code == 200
    plan = r.json()
    assert plan["resource_scope"] == "local_default"
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["capability_id"] == "filesystem.read_test_data"


def test_unregistered_tool_fails_closed(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    api = client(FakeSelector({
        "capability_id": "terminal.sandbox.execute",
        "arguments": {"argv": ["sh"]},
    }))
    r = api.post("/api/tasks/plan",
                 headers={"Authorization": "Bearer " + "t" * 40},
                 json={"directive": "Dosyamı oku ve yorumla"})
    assert r.status_code == 422


def test_no_tool_needed_returns_text_chat_without_dispatch(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    api = client(FakeSelector({"capability_id": "none", "arguments": {}}))
    r = api.post("/api/tasks/plan",
                 headers={"Authorization": "Bearer " + "t" * 40},
                 json={"directive": "Dosyamı oku ve yorumla"})
    assert r.status_code == 200
    assert r.json()["steps"] == []
    assert r.json()["resource_scope"] == "local-assistant"


def test_external_nineteen_mcp_tools_visible_and_selectable_with_exact_gateway_scope(
    monkeypatch,
):
    import json
    from aura_core.kernel.permissions import (
        PermissionEngine, PermissionPolicy, AuthorizationLevel, AuthorizationDecision,
    )
    from aura_core.application.api import _external_mcp_execution_scope

    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    class CaptureSelector:
        async def complete_json(self, *, system_prompt, user_prompt):
            catalog = json.loads(user_prompt)["available_tools"]
            external = [entry for entry in catalog
                        if entry["capability_id"].startswith("external.mcp.")]
            assert len(external) == 19
            assert len(catalog) >= 36
            return {"capability_id": "external.mcp.abcdef123456.memory_00",
                    "arguments": {"query": "workspace"}}

    api = client(CaptureSelector())
    kernel = api.app.state.kernel
    providers = kernel.provider_registry
    caps = kernel.capability_registry
    services = providers._service_registry

    class ToolCollection:
        def __init__(self, prefix, count):
            self.tools = [
                SimpleNamespace(name=f"{prefix}_{i:02d}", input_schema={
                    "type": "object", "properties": {"query": {"type": "string"}},
                })
                for i in range(count)
            ]

        async def list_tools(self):
            return self.tools

    def register_group(prefix, count, provider_id, external):
        service = services.register(ServiceDefinition(
            name=f"mock-{prefix}", version="1.0.0", provider="mcp",
            category=ServiceCategory.MCP,
        ), object())
        providers.register(ProviderDefinition(
            provider_id=provider_id, name=f"Provider {prefix}",
            version="1.0.0", service_id=service.service_id,
        ), ToolCollection(prefix, count))
        for i in range(count):
            tool_name = f"{prefix}_{i:02d}"
            cap = (f"external.mcp.abcdef123456.{tool_name}"
                   if external else f"builtin.{tool_name}")
            caps.register(CapabilityDefinition(
                capability_id=cap, name=f"Tool {tool_name}", version="1.0.0",
                description="Local MCP tool",
                provider_id=provider_id, provider_type=ProviderType.MCP,
                category=CapabilityCategory.MEMORY,
                tool_name=tool_name, risk_level="low",
            ))

    register_group("built", 20, "builtin.provider", False)
    register_group("memory", 19, "aura.external.abcdef123456", True)
    engine = PermissionEngine(caps)
    kernel.permission_engine = engine
    cap = "external.mcp.abcdef123456.memory_00"
    scope = "evolution:isolated:" + ("a" * 64) + ":memory_00"
    engine.add_policy(PermissionPolicy(
        policy_id="owner-approved-memory",
        policy_version="1.0.0", principal_id="local_owner",
        capability_id=cap, operation_id=cap,
        resource_scope=scope, authorization_level=AuthorizationLevel.EXECUTE,
        decision=AuthorizationDecision.ALLOW,
    ))

    def plan():
        return api.post("/api/tasks/plan",
                        headers={"Authorization": "Bearer " + "t" * 40},
                        json={"directive": "Projectmem hafızamı sorgula"})

    response = plan()
    assert response.status_code == 200, response.text
    assert response.json()["resource_scope"] == scope
    assert response.json()["steps"][0]["capability_id"] == cap
    assert _external_mcp_execution_scope(engine, "local_owner", cap) == scope

    # Scope selection never grants a policy: signed Owner revocation is final.
    engine.revoke_policy("owner-approved-memory")
    assert _external_mcp_execution_scope(engine, "local_owner", cap) is None
    denied = plan()
    assert denied.status_code == 422
    assert "explicit authorized scope" in denied.json()["detail"]


def test_external_scope_never_uses_unrelated_or_ambiguous_allow_policy():
    from aura_core.kernel.permissions import (
        PermissionEngine, PermissionPolicy, AuthorizationLevel, AuthorizationDecision,
    )
    from aura_core.application.api import _external_mcp_execution_scope
    from aura_core.kernel.capabilities import CapabilityRegistry

    engine = PermissionEngine(CapabilityRegistry(ServiceRegistry()))
    cap = "external.mcp.abcdef.tool"
    for n, scope in enumerate((
        "evolution:isolated:" + "a" * 64 + ":tool",
        "evolution:isolated:" + "b" * 64 + ":tool",
    )):
        engine.add_policy(PermissionPolicy(
            policy_id=f"policy-{n}", policy_version="1.0.0",
            principal_id="local_owner", capability_id=cap, operation_id=cap,
            resource_scope=scope, authorization_level=AuthorizationLevel.EXECUTE,
            decision=AuthorizationDecision.ALLOW,
        ))
    assert _external_mcp_execution_scope(engine, "local_owner", cap) is None
    assert _external_mcp_execution_scope(engine, "foreign", cap) is None


def test_model_selector_preserves_fastmcp_nullable_arguments(monkeypatch):
    import json

    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")

    class NullableSelector:
        async def complete_json(self, *, system_prompt, user_prompt):
            catalog = json.loads(user_prompt)["available_tools"]
            selected = next(
                row for row in catalog
                if row["capability_id"] == "filesystem.read_test_data"
            )
            assert "context" in selected["argument_keys"]
            assert selected["nullable_arguments"] == ["context"]
            return {
                "capability_id": "filesystem.read_test_data",
                "arguments": {"path": "safe.txt", "context": None},
            }

    api = client(NullableSelector())
    provider = api.app.state.kernel.provider_registry.resolve("filesystem.test")

    async def nullable_tools():
        return [SimpleNamespace(
            name="read_data",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "context": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "default": None,
                    },
                },
            },
        )]

    monkeypatch.setattr(provider, "list_tools", nullable_tools)
    response = api.post(
        "/api/tasks/plan",
        headers={"Authorization": "Bearer " + "t" * 40},
        json={"directive": "Read my safe note"},
    )
    assert response.status_code == 200
    assert response.json()["steps"][0]["arguments"] == {
        "path": "safe.txt", "context": None,
    }
