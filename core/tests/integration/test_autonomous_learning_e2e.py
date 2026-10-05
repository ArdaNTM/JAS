from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionEngine,
    PermissionPolicy,
    RiskLevel,
)
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
)
from aura_core.learning.contracts import ResearchToolSpec
from aura_core.learning.engine import LearningEngine
from aura_core.learning.models import (
    LearningObjective,
    LearningPolicy,
)
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import (
    ProviderDefinition,
    ProviderRegistry,
)

from aura_core.memory.models import MemoryRecord


class FakeConnection:
    is_connected = True

    async def list_tools(self):
        class Tool:
            def __init__(self, name):
                self.name = name
                self.description = name
                self.inputSchema = {
                    "type": "object"
                }

        class Result:
            tools = [
                Tool("search"),
                Tool("fetch"),
            ]

        return Result()

    async def call_tool(
        self,
        name,
        arguments,
    ):
        if name == "search":
            return {
                "results": [
                    {
                        "url":
                            "https://example.test/aura",
                        "title":
                            "AURA Research",
                    }
                ]
            }

        if name == "fetch":
            return {
                "content": (
                    "AURA is a capability-driven "
                    "execution platform."
                )
            }

        raise AssertionError(name)

    async def close(self):
        self.is_connected = False


class FakeKnowledge:
    def __init__(self):
        self.sources = {}
        self.records = {}
        self.facts = {}

    async def initialize(self):
        return None

    async def ingest_source(
        self,
        source,
        payload,
    ):
        self.sources[
            source.source_id
        ] = payload

    async def ingest_record(
        self,
        record,
    ):
        self.records[
            record.record_id
        ] = record

    async def ingest_fact(
        self,
        fact,
    ):
        self.facts[
            fact.fact_id
        ] = fact


class FakeMemory:
    def __init__(self):
        self.records = {}

    async def initialize(self):
        return None

    async def put(
        self,
        record: MemoryRecord,
    ):
        self.records[
            record.record_id
        ] = record


class FakeLLM:
    async def generate(
        self,
        prompt,
        options=None,
    ):
        return (
            '{"facts":['
            '{"subject":"AURA",'
            '"predicate":"architecture",'
            '"object":"capability-driven",'
            '"confidence":0.99,'
            '"quote":"AURA is a capability-driven execution platform."}'
            ']}'
        )


def make_engine(
    checkpoint_root: Path,
):
    bus = EventBus()
    services = ServiceRegistry()

    service = services.register(
        ServiceDefinition(
            "research-test",
            "1",
            "aura",
            ServiceCategory.MCP,
        ),
        object(),
    )

    providers = ProviderRegistry(
        services,
        bus,
    )

    provider = MCPProvider(
        FakeConnection()
    )

    providers.register(
        ProviderDefinition(
            "mcp:test-research",
            "test-research",
            "1",
            service.service_id,
        ),
        provider,
    )

    capabilities = CapabilityRegistry(
        services,
        bus,
    )

    capabilities.register(
        CapabilityDefinition(
            "internet.search",
            "Internet Search",
            "1",
            "test research",
            "mcp:test-research",
            ProviderType.MCP,
            CapabilityCategory.RESEARCH,
        )
    )

    permissions = PermissionEngine(
        capabilities,
        bus,
    )

    permissions.add_policy(
        PermissionPolicy(
            "learning-search",
            "1",
            "aura-learning",
            "internet.search",
            "internet.search",
            "research",
            AuthorizationLevel.READ,
            AuthorizationDecision.ALLOW,
        )
    )

    permissions.add_policy(
        PermissionPolicy(
            "learning-fetch",
            "1",
            "aura-learning",
            "internet.search",
            "internet.fetch",
            "research",
            AuthorizationLevel.READ,
            AuthorizationDecision.ALLOW,
        )
    )

    gateway = MCPGateway(
        capabilities,
        providers,
        permissions,
    )

    tool_spec = ResearchToolSpec(
        search_capability_id="internet.search",
        search_operation_id="internet.search",
        search_tool_name="search",
        fetch_capability_id="internet.search",
        fetch_operation_id="internet.fetch",
        fetch_tool_name="fetch",
    )

    engine = LearningEngine(
        gateway=gateway,
        knowledge=FakeKnowledge(),
        memory=FakeMemory(),
        llm=FakeLLM(),
        tool_spec=tool_spec,
        policy=LearningPolicy(
            interval_seconds=1,
            max_sources=1,
            max_steps=1,
            max_runtime_seconds=10,
        ),
        checkpoint_root=checkpoint_root,
    )

    return engine


def test_learning_e2e_is_restart_safe():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        objective = LearningObjective(
            objective_id="learn-aura",
            title="AURA Architecture Learning",
            description="AURA architecture",
            priority=1,
            enabled=True,
        )

        first = asyncio.run(
            make_engine(root).run(
                objective
            )
        )

        assert first.status.value == "completed"

        second = asyncio.run(
            make_engine(root).run(
                objective
            )
        )

        assert second.status.value == "completed"
        assert second.run_id == first.run_id


def test_learning_gateway_denial_never_reaches_provider():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        engine = make_engine(root)

        engine.gateway._permission_engine._policies.clear()

        objective = LearningObjective(
            objective_id="denied-learning",
            title="Denied Learning Test",
            description="AURA",
            priority=1,
            enabled=True,
        )

        result = asyncio.run(
            engine.run(objective)
        )

        assert result.status.value == "failed"
        assert "PermissionError" in (
            result.error or ""
        )
