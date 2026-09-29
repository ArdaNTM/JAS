from fastapi.testclient import TestClient

from aura_core.agent.integration import CapabilityAgentRuntime
from aura_core.agent.runtime import AgentExecutor
from aura_core.application.api import create_api
from aura_core.application.tasks import AgentTaskService
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.discovery.service import ToolDiscoveryService, ToolSelectionService
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPProvider, MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.mcp.tool_registry import MCPToolRegistry


class Connection:
    is_connected = True
    async def call_tool(self, name, arguments):
        return {"tool": name, "arguments": arguments}

    async def close(self):
        self.is_connected = False


class Transport:
    def post_json(self, endpoint, payload, timeout):
        return {"model": "test", "message": {"content": "ok"}, "done": True}
    def get_json(self, endpoint, timeout):
        return {"models": [{"name": "test"}]}


def client(decision: AuthorizationDecision) -> TestClient:
    bus, services = EventBus(), ServiceRegistry()
    service = services.register(ServiceDefinition("mcp-test", "1", "aura", ServiceCategory.MCP), object())
    capabilities = CapabilityRegistry(services, bus)
    providers = ProviderRegistry(services, bus)
    provider_id, capability_id, operation = "mcp:test", "test.echo", "test.echo"
    providers.register(ProviderDefinition(provider_id, "test", "1", service.service_id), MCPProvider(Connection()))
    capabilities.register(CapabilityDefinition(capability_id, "Test echo", "1", "test-only capability", provider_id, ProviderType.MCP, CapabilityCategory.AUTOMATION))
    tools = MCPToolRegistry(bus)
    tools.register(provider_id, MCPTool("echo", "Echo a test payload", {"type": "object"}))
    permissions = PermissionEngine(capabilities, bus)
    permissions.add_policy(PermissionPolicy("test-policy", "1", "agent:web", capability_id, operation, "D:/workspace", AuthorizationLevel.USER_APPROVAL_REQUIRED if decision is AuthorizationDecision.REQUIRE_APPROVAL else AuthorizationLevel.EXECUTE, decision))
    gateway = MCPGateway(capabilities, providers, permissions)
    runtime = CapabilityAgentRuntime(AgentExecutor(gateway, bus), ToolDiscoveryService(capabilities, tools, bus), ToolSelectionService(), bus)
    app = create_api(RuntimeConfig(model="test"), BackendConfig(endpoint="http://test", timeout=1), Transport(), AgentTaskService(runtime))
    return TestClient(app)


def payload():
    return {"task_id": "task-1", "principal_id": "agent:web", "title": "Echo", "resource_scope": "D:/workspace", "steps": [{"step_id": "one", "capability_id": "test.echo", "operation_id": "test.echo", "tool_name": "echo", "risk_level": "low", "arguments": {"message": "hello"}}]}


def test_http_agent_discovery_permission_gateway_provider_tool_allow() -> None:
    response = client(AuthorizationDecision.ALLOW).post("/api/tasks", json=payload())
    assert response.status_code == 200
    assert response.json()["state"] == "succeeded"


def test_http_agent_default_deny_stops_tool_execution() -> None:
    response = client(AuthorizationDecision.DENY).post("/api/tasks", json=payload())
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["steps"][0]["reason"] == "Explicit deny policy matched"


def test_http_agent_approval_requirement_stops_tool_execution() -> None:
    response = client(AuthorizationDecision.REQUIRE_APPROVAL).post("/api/tasks", json=payload())
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["steps"][0]["reason"] == "Explicit user approval is required"
