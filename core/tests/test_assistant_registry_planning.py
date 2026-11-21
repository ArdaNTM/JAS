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



def test_capability_question_never_runs_model_tool_selector(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    class ForbiddenSelector:
        async def complete_json(self, **kwargs):
            raise AssertionError("Capability questions must not enter tool-selection")
    api = client(ForbiddenSelector())
    response = api.post("/api/tasks/plan",
        headers={"Authorization": "Bearer " + "t" * 40},
        json={"directive": "Neler yapabilirsin?"})
    assert response.status_code == 200
    assert response.json()["resource_scope"] == "local-assistant"
    assert response.json()["steps"] == []
