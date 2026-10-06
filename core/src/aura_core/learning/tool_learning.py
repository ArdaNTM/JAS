from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .skill_library import Skill, SkillExtractor, SkillLibrary


@dataclass(frozen=True, slots=True)
class DiscoveredTool:
    provider_id: str
    service_id: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def capability_id(self) -> str:
        return (
            f"{self.service_id}.{self.tool_name}"
        )

    @property
    def operation_id(self) -> str:
        return self.capability_id

    @property
    def fingerprint(self) -> str:
        payload = {
            "provider_id": self.provider_id,
            "service_id": self.service_id,
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        return hashlib.sha256(
            encoded
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class LearnedCapability:
    provider_id: str
    service_id: str
    capability_id: str
    operation_id: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    fingerprint: str
    trusted: bool = False


@dataclass(frozen=True, slots=True)
class ToolLearningResult:
    discovered: DiscoveredTool
    capability: LearnedCapability
    registered: bool
    skill: Skill | None
    reason: str


class CapabilityRegistrar(Protocol):
    async def register_discovered_tool(
        self,
        tool: DiscoveredTool,
    ) -> LearnedCapability:
        ...


class MCPToolCaller(Protocol):
    async def call_tool(
        self,
        *,
        principal_id: str,
        capability_id: str,
        operation_id: str,
        resource_scope: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...


class RegistryCapabilityRegistrar:
    """
    Adapter between MCP discovery and AURA registries.

    The registrar intentionally does NOT create an authorization policy.
    Discovery means "known", not "trusted" and never means "authorized".
    """

    def __init__(
        self,
        *,
        service_registry: Any,
        capability_registry: Any,
        provider_registry: Any,
    ) -> None:
        self.service_registry = service_registry
        self.capability_registry = capability_registry
        self.provider_registry = provider_registry
        self._lock = asyncio.Lock()

    @staticmethod
    async def _call(
        target: Any,
        names: tuple[str, ...],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        for name in names:
            method = getattr(
                target,
                name,
                None,
            )

            if method is None:
                continue

            result = method(
                *args,
                **kwargs,
            )

            if hasattr(
                result,
                "__await__",
            ):
                return await result

            return result

        raise AttributeError(
            f"No supported registry method on "
            f"{type(target).__name__}: {names}"
        )

    async def register_discovered_tool(
        self,
        tool: DiscoveredTool,
    ) -> LearnedCapability:
        async with self._lock:
            await self._call(
                self.provider_registry,
                (
                    "register",
                    "add",
                    "register_provider",
                ),
                tool.provider_id,
            )

            await self._call(
                self.service_registry,
                (
                    "register",
                    "add",
                    "register_service",
                ),
                tool.service_id,
            )

            await self._call(
                self.capability_registry,
                (
                    "register",
                    "add",
                    "register_capability",
                ),
                tool.capability_id,
            )

        return LearnedCapability(
            provider_id=tool.provider_id,
            service_id=tool.service_id,
            capability_id=tool.capability_id,
            operation_id=tool.operation_id,
            tool_name=tool.tool_name,
            description=tool.description,
            input_schema=tool.input_schema,
            fingerprint=tool.fingerprint,
            trusted=False,
        )


class SelfDirectedToolLearner:
    """
    Runtime MCP tool discovery -> registry admission -> skill
    derivation.

    Security invariant:

        discovery != authorization
        registration != execution
        learned skill != permission

    Every real invocation must still enter MCPGateway and therefore
    PermissionEngine.
    """

    def __init__(
        self,
        *,
        registrar: CapabilityRegistrar,
        skill_library: SkillLibrary | None = None,
        skill_extractor: SkillExtractor | None = None,
    ) -> None:
        self.registrar = registrar
        self.skill_library = skill_library
        self.skill_extractor = (
            skill_extractor
            or SkillExtractor()
        )
        self._seen_fingerprints: set[str] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def from_mcp_tool(
        *,
        provider_id: str,
        service_id: str,
        tool: Any,
    ) -> DiscoveredTool:
        name = str(
            getattr(
                tool,
                "name",
                "",
            )
        ).strip()

        description = str(
            getattr(
                tool,
                "description",
                "",
            )
            or ""
        ).strip()

        input_schema = getattr(
            tool,
            "inputSchema",
            None,
        )

        if input_schema is None:
            input_schema = getattr(
                tool,
                "input_schema",
                {},
            )

        output_schema = getattr(
            tool,
            "outputSchema",
            None,
        )

        if output_schema is None:
            output_schema = getattr(
                tool,
                "output_schema",
                None,
            )

        if not name:
            raise ValueError(
                "MCP tool has no name"
            )

        if not isinstance(
            input_schema,
            dict,
        ):
            input_schema = {}

        if (
            output_schema is not None
            and not isinstance(
                output_schema,
                dict,
            )
        ):
            output_schema = None

        return DiscoveredTool(
            provider_id=provider_id,
            service_id=service_id,
            tool_name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata={
                "source": "mcp.tools/list",
            },
        )

    async def learn_tool(
        self,
        tool: DiscoveredTool,
    ) -> ToolLearningResult:
        async with self._lock:
            if (
                tool.fingerprint
                in self._seen_fingerprints
            ):
                capability = LearnedCapability(
                    provider_id=tool.provider_id,
                    service_id=tool.service_id,
                    capability_id=tool.capability_id,
                    operation_id=tool.operation_id,
                    tool_name=tool.tool_name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    fingerprint=tool.fingerprint,
                    trusted=False,
                )

                return ToolLearningResult(
                    discovered=tool,
                    capability=capability,
                    registered=False,
                    skill=None,
                    reason="duplicate discovery",
                )

            capability = (
                await self.registrar.register_discovered_tool(
                    tool
                )
            )

            self._seen_fingerprints.add(
                tool.fingerprint
            )

            return ToolLearningResult(
                discovered=tool,
                capability=capability,
                registered=True,
                skill=None,
                reason=(
                    "registered as untrusted "
                    "discovered capability"
                ),
            )

    async def learn_tools(
        self,
        *,
        provider_id: str,
        service_id: str,
        tools: list[Any],
    ) -> list[ToolLearningResult]:
        results: list[
            ToolLearningResult
        ] = []

        for tool in tools:
            discovered = self.from_mcp_tool(
                provider_id=provider_id,
                service_id=service_id,
                tool=tool,
            )

            results.append(
                await self.learn_tool(
                    discovered
                )
            )

        return results

    async def derive_skill(
        self,
        *,
        result: ToolLearningResult,
        run_id: str,
        objective: str,
        success: bool = True,
        confidence: float = 0.5,
    ) -> Skill | None:
        if not result.registered:
            return None

        skill = self.skill_extractor.from_run(
            run_id=run_id,
            objective=objective,
            capability_id=(
                result.capability.capability_id
            ),
            operation_id=(
                result.capability.operation_id
            ),
            tool_name=(
                result.capability.tool_name
            ),
            success=success,
            confidence=confidence,
        )

        if (
            skill is not None
            and self.skill_library is not None
            and success
        ):
            await self.skill_library.register(
                skill
            )

        return skill


class GatewayBoundToolExecutor:
    """
    Deliberately thin execution adapter.

    No MCPConnection.call_tool() is exposed here. Execution must be
    delegated to MCPGateway, which constructs AuthorizationRequest and
    invokes PermissionEngine before the provider call.
    """

    def __init__(
        self,
        gateway: MCPToolCaller,
    ) -> None:
        self.gateway = gateway

    async def execute(
        self,
        *,
        principal_id: str,
        capability: LearnedCapability,
        resource_scope: str,
        arguments: dict[str, Any],
    ) -> Any:
        if capability.trusted:
            # Trusted status is still not treated as authorization.
            # The gateway remains mandatory.
            pass

        return await self.gateway.call_tool(
            principal_id=principal_id,
            capability_id=(
                capability.capability_id
            ),
            operation_id=(
                capability.operation_id
            ),
            resource_scope=resource_scope,
            tool_name=capability.tool_name,
            arguments=arguments,
        )
