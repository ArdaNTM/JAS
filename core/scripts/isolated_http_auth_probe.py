import os
from fastapi import Request

from aura_core.main import build_app
from aura_core.kernel.services import ServiceDefinition, ServiceCategory
from aura_core.kernel.capabilities import (
    CapabilityDefinition, CapabilityCategory, ProviderType
)
from aura_core.kernel.permissions import (
    PermissionPolicy, AuthorizationDecision, AuthorizationLevel
)
from aura_core.mcp.provider import ProviderDefinition
from aura_core.mcp.mcp_provider import MCPProvider


class SyntheticConnection:
    """Yalnizca bellek icinde calisan, harici arac kullanmayan test baglantisi."""

    is_connected = True

    def __init__(self):
        self.calls = 0
        self.last_call = None

    async def call_tool(self, name, arguments=None):
        self.calls += 1
        self.last_call = {
            "tool": name,
            "arguments": arguments or {},
        }
        return {
            "synthetic": True,
            "tool": name,
            "arguments": arguments or {},
        }

    async def list_tools(self):
        class Result:
            tools = []
        return Result()

    async def close(self):
        self.is_connected = False


app = build_app()
kernel = app.state.kernel

connection = SyntheticConnection()
provider_id = "mcp:isolated-http-test"
capability_id = "test.echo"
operation_id = "test.echo"
principal_id = "local_owner"
scope = "local_default"

service = kernel.service_registry.register(
    ServiceDefinition(
        name="isolated-http-test",
        version="1.0.0",
        provider="mcp",
        category=ServiceCategory.MCP,
    ),
    connection,
)

kernel.provider_registry.register(
    ProviderDefinition(
        provider_id=provider_id,
        name="isolated-http-test",
        version="1.0.0",
        service_id=service.service_id,
    ),
    MCPProvider(connection),
)

kernel.capability_registry.register(
    CapabilityDefinition(
        capability_id=capability_id,
        name="Isolated Echo",
        version="1.0.0",
        description="Synthetic test only; no external side effects.",
        provider_id=provider_id,
        provider_type=ProviderType.MCP,
        category=CapabilityCategory.AUTOMATION,
    )
)

scenario = os.getenv("AURA_TEST_SCENARIO", "default-deny")

if scenario == "allow":
    decision = AuthorizationDecision.ALLOW
    level = AuthorizationLevel.EXECUTE
elif scenario == "approval":
    decision = AuthorizationDecision.REQUIRE_APPROVAL
    level = AuthorizationLevel.USER_APPROVAL_REQUIRED
elif scenario == "default-deny":
    decision = None
else:
    raise RuntimeError(f"Unknown test scenario: {scenario}")

# Default-deny senaryosunda kasitli olarak hicbir politika eklenmez.
if decision is not None:
    kernel.permission_engine.add_policy(
        PermissionPolicy(
            policy_id=f"isolated-http-test:{scenario}",
            policy_version="1.0.0",
            principal_id=principal_id,
            capability_id=capability_id,
            operation_id=operation_id,
            resource_scope=scope,
            authorization_level=level,
            decision=decision,
        )
    )


@app.get("/__test/calls")
async def test_calls():
    return {
        "scenario": scenario,
        "calls": connection.calls,
        "last_call": connection.last_call,
    }
