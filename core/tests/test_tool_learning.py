from __future__ import annotations

import asyncio
from pathlib import Path

from aura_core.learning.skill_library import (
    SkillLibrary,
)
from aura_core.learning.tool_learning import (
    GatewayBoundToolExecutor,
    RegistryCapabilityRegistrar,
    SelfDirectedToolLearner,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.values: list[object] = []

    async def register(
        self,
        value,
    ) -> None:
        self.values.append(value)


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def call_tool(
        self,
        *,
        principal_id,
        capability_id,
        operation_id,
        resource_scope,
        tool_name,
        arguments,
    ):
        self.calls.append(
            {
                "principal_id": principal_id,
                "capability_id": capability_id,
                "operation_id": operation_id,
                "resource_scope": resource_scope,
                "tool_name": tool_name,
                "arguments": arguments,
            }
        )

        return {
            "ok": True,
            "authorized_by_gateway": True,
        }


class FakeTool:
    name = "search"
    description = "Search the public web"
    inputSchema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string"
            }
        },
        "required": ["query"],
    }
    outputSchema = {
        "type": "object"
    }


def test_phase10_runtime_tool_learning_and_gateway_boundary(
    tmp_path: Path,
) -> None:
    asyncio.run(
        _test_phase10_runtime_tool_learning_and_gateway_boundary(
            tmp_path
        )
    )


async def _test_phase10_runtime_tool_learning_and_gateway_boundary(
    tmp_path: Path,
) -> None:
    service_registry = FakeRegistry()
    capability_registry = FakeRegistry()
    provider_registry = FakeRegistry()

    registrar = RegistryCapabilityRegistrar(
        service_registry=service_registry,
        capability_registry=capability_registry,
        provider_registry=provider_registry,
    )

    library = SkillLibrary(
        tmp_path / "skills"
    )

    await library.initialize()

    learner = SelfDirectedToolLearner(
        registrar=registrar,
        skill_library=library,
    )

    results = await learner.learn_tools(
        provider_id="provider-x",
        service_id="service-x",
        tools=[FakeTool()],
    )

    assert len(results) == 1

    result = results[0]

    assert result.registered is True
    assert (
        result.capability.capability_id
        == "service-x.search"
    )
    assert (
        result.capability.trusted is False
    )

    assert len(
        provider_registry.values
    ) == 1

    assert len(
        service_registry.values
    ) == 1

    assert len(
        capability_registry.values
    ) == 1

    skill = await learner.derive_skill(
        result=result,
        run_id="tool-learning-run-001",
        objective="Search the public web",
        success=True,
        confidence=0.8,
    )

    assert skill is not None

    stored = await library.get(
        skill.skill_id
    )

    assert stored is not None
    assert stored.enabled is False


def test_phase10_duplicate_discovery_is_idempotent(
    tmp_path: Path,
) -> None:
    asyncio.run(
        _test_phase10_duplicate_discovery_is_idempotent(
            tmp_path
        )
    )


async def _test_phase10_duplicate_discovery_is_idempotent(
    tmp_path: Path,
) -> None:
    registrar = RegistryCapabilityRegistrar(
        service_registry=FakeRegistry(),
        capability_registry=FakeRegistry(),
        provider_registry=FakeRegistry(),
    )

    learner = SelfDirectedToolLearner(
        registrar=registrar,
        skill_library=SkillLibrary(
            tmp_path / "skills"
        ),
    )

    await learner.skill_library.initialize()

    first = await learner.learn_tools(
        provider_id="provider-x",
        service_id="service-x",
        tools=[FakeTool()],
    )

    second = await learner.learn_tools(
        provider_id="provider-x",
        service_id="service-x",
        tools=[FakeTool()],
    )

    assert first[0].registered is True
    assert second[0].registered is False
    assert second[0].reason == (
        "duplicate discovery"
    )


def test_phase10_execution_always_crosses_gateway(
) -> None:
    asyncio.run(
        _test_phase10_execution_always_crosses_gateway()
    )


async def _test_phase10_execution_always_crosses_gateway(
) -> None:
    gateway = FakeGateway()

    executor = GatewayBoundToolExecutor(
        gateway
    )

    registrar = RegistryCapabilityRegistrar(
        service_registry=FakeRegistry(),
        capability_registry=FakeRegistry(),
        provider_registry=FakeRegistry(),
    )

    learner = SelfDirectedToolLearner(
        registrar=registrar
    )

    results = await learner.learn_tools(
        provider_id="provider-secure",
        service_id="service-secure",
        tools=[FakeTool()],
    )

    capability = results[0].capability

    response = await executor.execute(
        principal_id="local-user",
        capability=capability,
        resource_scope="public-web",
        arguments={
            "query": "MCP"
        },
    )

    assert response["authorized_by_gateway"] is True
    assert len(gateway.calls) == 1

    call = gateway.calls[0]

    assert call["principal_id"] == (
        "local-user"
    )
    assert call["capability_id"] == (
        "service-secure.search"
    )
    assert call["operation_id"] == (
        "service-secure.search"
    )
    assert call["resource_scope"] == (
        "public-web"
    )
    assert call["tool_name"] == "search"


def test_phase10_malformed_tool_is_rejected(
) -> None:
    asyncio.run(
        _test_phase10_malformed_tool_is_rejected()
    )


async def _test_phase10_malformed_tool_is_rejected(
) -> None:
    registrar = RegistryCapabilityRegistrar(
        service_registry=FakeRegistry(),
        capability_registry=FakeRegistry(),
        provider_registry=FakeRegistry(),
    )

    learner = SelfDirectedToolLearner(
        registrar=registrar
    )

    class BrokenTool:
        name = ""
        description = ""
        inputSchema = {}

    try:
        await learner.learn_tools(
            provider_id="provider-x",
            service_id="service-x",
            tools=[BrokenTool()],
        )
    except ValueError as exc:
        assert "no name" in str(
            exc
        ).lower()
    else:
        raise AssertionError(
            "Malformed MCP tool was accepted"
        )
