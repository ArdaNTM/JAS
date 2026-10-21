from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aura_core.agent.runtime import AgentExecutor
from aura_core.application.composition import create_composed_app
from aura_core.application.capability_discovery import DynamicCapabilityDiscovery
from aura_core.application.tasks import AgentTaskService
from aura_core.application.task_memory import TaskMemoryCoordinator
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionPolicy,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.health import HealthReport
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceState
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.research.config import ResearchMCPConfig
from aura_core.research.provider_bootstrap import (
    register_research_mcp,
)
from aura_core.tts.config import KokoroMCPConfig
from aura_core.tts.provider_bootstrap import register_kokoro_mcp


logger = logging.getLogger(
    "aura_core.lifecycle"
)



class VisualizationPlanService:
    """Registry marker for the deterministic, UI-only visualization plan."""

def build_app() -> FastAPI:
    kernel_config = KernelConfig.from_environment()

    kernel = AuraKernel(kernel_config)
    kernel.bootstrap()

    if (
        kernel.capability_registry is None
        or kernel.provider_registry is None
        or kernel.permission_engine is None
        or kernel.service_registry is None
    ):
        raise RuntimeError(
            "AURA kernel registries were not initialized"
        )

    visualization_service_id = "aura:visualization_planner:0.1.0"
    kernel.service_registry.register(
        ServiceDefinition(
            name="visualization_planner",
            version="0.1.0",
            provider="aura",
            category=ServiceCategory.KERNEL,
            capabilities={"3d.visualize"},
            tags={"foundation", "presentation"},
        ),
        VisualizationPlanService(),
    )
    kernel.capability_registry.register(
        CapabilityDefinition(
            capability_id="3d.visualize",
            name="3D Visualization Plan",
            version="1.0.0",
            description="Creates a deterministic UI-only procedural visualization plan.",
            provider_id=visualization_service_id,
            provider_type=ProviderType.CORE,
            category=CapabilityCategory.VISUALIZATION,
            required_permissions=frozenset(),
        )
    )
    research_config = ResearchMCPConfig.from_env()
    kokoro_config = KokoroMCPConfig.from_env()
    research_tools = MCPToolRegistry()
    tts_tools = MCPToolRegistry()

    gateway = MCPGateway(
        capability_registry=kernel.capability_registry,
        provider_registry=kernel.provider_registry,
        permission_engine=kernel.permission_engine,
    )

    task_service = AgentTaskService(
        AgentExecutor(
            gateway=gateway,
            event_bus=kernel.event_bus,
        ),
        memory=TaskMemoryCoordinator.from_environment(),
    )

    app = create_composed_app(
        config=kernel_config.runtime,
        backend_config=kernel_config.backend,
        task_service=task_service,
        event_bus=kernel.event_bus,
        permission_engine=kernel.permission_engine,
        kernel=kernel,
        gateway=gateway,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        research_provider = None
        kokoro_provider = None

        # MCP_HEALTH_REPORT_PATCH: report only after successful provider setup.
        def report_mcp_healthy(config):
            monitor = kernel.health_monitor
            registry = kernel.service_registry
            if monitor is None or registry is None:
                raise RuntimeError("Kernel health services are unavailable")

            record = next(
                (
                    item for item in registry.records()
                    if item.definition.provider == "mcp"
                    and item.definition.name == config.service_name
                    and item.definition.version == config.service_version
                ),
                None,
            )
            if record is None:
                raise RuntimeError(
                    f"MCP service registration not found: {config.service_name}"
                )

            registry.update_state(record.service_id, ServiceState.RUNNING)
            monitor.report(
                HealthReport(
                    service_id=record.service_id,
                    available=True,
                    ready=True,
                    live=True,
                )
            )

        event_bridge = getattr(
            _app.state,
            "event_bridge",
            None,
        )

        learning_scheduler = getattr(
            _app.state,
            "learning_scheduler",
            None,
        )

        # Diagnostic/API tests exercise the composed Kernel without spawning
        # external stdio processes. Production keeps providers enabled unless
        # this explicit test/deployment switch is set.
        if os.getenv("AURA_DISABLE_EXTERNAL_PROVIDERS", "0") == "1":
            yield
            return

        try:
            logger.info(
                "LIFESPAN: registering research MCP"
            )

            research_provider = await asyncio.wait_for(
                register_research_mcp(
                    config=research_config,
                    services=kernel.service_registry,
                    providers=kernel.provider_registry,
                    capabilities=kernel.capability_registry,
                    tools=research_tools,
                ),
                timeout=20.0,
            )
            report_mcp_healthy(research_config)

            kokoro_provider = await asyncio.wait_for(
                register_kokoro_mcp(
                    config=kokoro_config,
                    services=kernel.service_registry,
                    providers=kernel.provider_registry,
                    capabilities=kernel.capability_registry,
                    tools=tts_tools,
                ),
                timeout=20.0,
            )
            report_mcp_healthy(kokoro_config)

            # Discover metadata from providers only after their live MCP
            # connections and registries are established. Discovery creates
            # proposals; it never auto-approves or grants execution policy.
            discovery = DynamicCapabilityDiscovery(kernel.capability_registry)
            _app.state.capability_discovery = discovery
            for provider_record in kernel.provider_registry.records():
                try:
                    connected_provider = kernel.provider_registry.resolve(
                        provider_record.definition.provider_id
                    )
                    if not isinstance(connected_provider, MCPProvider) or not connected_provider.is_connected:
                        continue
                    discovered_tools = await connected_provider.list_tools()
                    category = "voice" if "tts" in provider_record.definition.provider_id.casefold() or "kokoro" in provider_record.definition.provider_id.casefold() else "research"
                    discovery.discover_mcp_tools(
                        provider_record.definition.provider_id,
                        [
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.input_schema,
                            }
                            for tool in discovered_tools
                        ],
                        category=category,
                    )
                    logger.info(
                        "MCP capability proposals discovered",
                        extra={
                            "provider_id": provider_record.definition.provider_id,
                            "tool_count": len(discovered_tools),
                        },
                    )
                except Exception:
                    logger.warning(
                        "MCP capability discovery failed; provider remains governed by existing registrations",
                        extra={"provider_id": provider_record.definition.provider_id},
                        exc_info=True,
                    )

            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id=(
                        "local-user:"
                        "internet.search:"
                        "local_default"
                    ),
                    policy_version="1.0.0",
                    principal_id="local_owner",
                    capability_id="internet.search",
                    operation_id="internet.search",
                    resource_scope="local_default",
                    authorization_level=(
                        AuthorizationLevel.EXECUTE
                    ),
                    decision=(
                        AuthorizationDecision.ALLOW
                    ),
                )
            )
            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id="local-user:speech.synthesize:local_default",
                    policy_version="1.0.0",
                    principal_id="local_owner",
                    capability_id="speech.synthesize",
                    operation_id="speech.synthesize",
                    resource_scope="local_default",
                    authorization_level=AuthorizationLevel.EXECUTE,
                    decision=AuthorizationDecision.ALLOW,
                )
            )

            logger.info(
                "LIFESPAN: starting kernel"
            )

            await asyncio.wait_for(
                asyncio.to_thread(
                    kernel.start
                ),
                timeout=15.0,
            )

            logger.info(
                "LIFESPAN: kernel started"
            )

            if event_bridge is not None:
                logger.info(
                    "LIFESPAN: starting event bridge"
                )

                await asyncio.wait_for(
                    event_bridge.start(),
                    timeout=10.0,
                )

            if learning_scheduler is not None:
                logger.info(
                    "LIFESPAN: starting learning scheduler"
                )

                await asyncio.wait_for(
                    learning_scheduler.start(),
                    timeout=10.0,
                )

            logger.info(
                "AURA LIFESPAN STARTUP COMPLETE"
            )

            yield

        except asyncio.CancelledError:
            logger.warning(
                "AURA lifespan startup cancelled"
            )
            raise

        except Exception:
            logger.exception(
                "AURA lifespan startup failed"
            )
            raise

        finally:
            logger.info(
                "AURA LIFESPAN SHUTDOWN BEGIN"
            )

            if learning_scheduler is not None:
                try:
                    await asyncio.wait_for(
                        learning_scheduler.stop(),
                        timeout=15.0,
                    )
                except Exception:
                    logger.exception(
                        "Learning scheduler shutdown failed"
                    )

            if event_bridge is not None:
                try:
                    await asyncio.wait_for(
                        event_bridge.stop(),
                        timeout=10.0,
                    )
                except Exception:
                    logger.exception(
                        "Event bridge shutdown failed"
                    )

            if kernel.state.value == "running":
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            kernel.stop
                        ),
                        timeout=10.0,
                    )
                except Exception:
                    logger.exception(
                        "Kernel shutdown failed"
                    )

            if research_provider is not None:
                try:
                    # MCP stdio owns AnyIO cancellation scopes; wrapping its
                    # close in asyncio.wait_for exits that scope from a second
                    # cancellation context under TestClient shutdown.
                    await research_provider.close()
                except Exception:
                    logger.exception(
                        "Research provider shutdown failed"
                    )

            if kokoro_provider is not None:
                try:
                    await kokoro_provider.close()
                except Exception:
                    logger.exception("Kokoro provider shutdown failed")

            logger.info(
                "AURA LIFESPAN SHUTDOWN COMPLETE"
            )

    _app_lifespan = lifespan
    app.router.lifespan_context = _app_lifespan

    return app


app = build_app()
