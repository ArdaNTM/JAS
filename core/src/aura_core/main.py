from __future__ import annotations

import asyncio
import logging
import os
from datetime import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aura_core.agent.runtime import AgentExecutor
from aura_core.application.composition import create_composed_app
from aura_core.application.event_bus_runtime import EventBusRuntime
from aura_core.application.event_driven_orchestration import EventDrivenOrchestrationCoordinator
from aura_core.application.capability_discovery import DynamicCapabilityDiscovery
from aura_core.application.tasks import AgentTaskService
from aura_core.application.task_memory import TaskMemoryCoordinator
from aura_core.application.task_state_machine import TaskStateMachine
from aura_core.application.autonomy_composition import compose_governed_autonomy
from aura_core.application.full_duplex_session import (
    EventBusAudioPlayer, FasterWhisperRecognizer, FullDuplexSessionManager,
    GatewaySpeechSynthesizer, ProactiveNotifier, ControlledVisionService,
)
from aura_core.application.vision_adapters import DesktopScreenCapture, OllamaVisionProvider
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionPolicy,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.kernel.events import KernelEvent
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
    sandbox_service_id = "aura:python_sandbox:0.1.0"
    kernel.service_registry.register(
        ServiceDefinition(
            name="python_sandbox",
            version="0.1.0",
            provider="aura",
            category=ServiceCategory.KERNEL,
            capabilities={"sandbox.python.execute"},
            tags={"sandbox", "isolated-execution"},
        ),
        object(),
    )
    kernel.capability_registry.register(
        CapabilityDefinition(
            capability_id="sandbox.python.execute",
            name="Isolated Python Draft Execution",
            version="1.0.0",
            description="Executes untrusted Python only in a digest-pinned, network-isolated container after explicit authorization.",
            provider_id=sandbox_service_id,
            provider_type=ProviderType.CORE,
            category=CapabilityCategory.CODING,
            required_permissions=frozenset({"sandbox.python.execute"}),
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

    task_database_path = os.getenv(
        "AURA_TASK_DB_PATH", str(os.getenv("LOCALAPPDATA", os.path.expanduser("~"))) + "/AURA/tasks.sqlite3"
    )
    task_state_machine = TaskStateMachine(task_database_path, event_bus=kernel.event_bus)
    task_service = AgentTaskService(
        AgentExecutor(
            gateway=gateway,
            event_bus=kernel.event_bus,
        ),
        memory=TaskMemoryCoordinator.from_environment(),
        state_machine=task_state_machine,
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

    event_runtime = EventBusRuntime(
        kernel.event_bus,
        enabled=os.getenv("AURA_EVENT_RUNTIME_ENABLED", "1").strip().casefold()
        not in {"0", "false", "no", "off"},
        idle_seconds=float(os.getenv("AURA_EVENT_IDLE_SECONDS", "300")),
        poll_interval_seconds=float(os.getenv("AURA_EVENT_POLL_INTERVAL_SECONDS", "0.1")),
    )
    app.state.event_bus_runtime = event_runtime
    app.state.task_state_machine = task_state_machine
    app.state.task_service = task_service

    async def deliver_proactive_notification(*, principal_id: str, message: str) -> None:
        kernel.event_bus.publish(KernelEvent(
            event_type="ProactiveNotificationReady",
            source_component="aura.proactive_notifier",
            payload={"principal_id": principal_id, "message": message, "requires_user_attention": True},
        ))

    app.state.proactive_notifier = ProactiveNotifier(
        deliver=deliver_proactive_notification,
        budget_per_day=int(os.getenv("AURA_PROACTIVE_DAILY_BUDGET", "5")),
        quiet_start=time.fromisoformat(os.getenv("AURA_QUIET_HOURS_START", "22:00")),
        quiet_end=time.fromisoformat(os.getenv("AURA_QUIET_HOURS_END", "08:00")),
    )

    # Autonomous execution is opt-in and fails startup if its explicit operation
    # allow-list is missing or malformed. It never creates permission policies.
    autonomy = compose_governed_autonomy(kernel=kernel, task_service=task_service)
    app.state.governed_autonomous_loop = autonomy.loop if autonomy is not None else None
    app.state.autonomy_components = autonomy

    vision_enabled = os.getenv("AURA_SCREEN_VISION_ENABLED", "0").strip().casefold() in {"1", "true", "yes", "on"}
    if vision_enabled:
        vision_principals = frozenset(
            item.strip() for item in os.getenv("AURA_VISION_PRINCIPALS", "local_owner").split(",")
            if item.strip()
        )
        app.state.controlled_vision_service = ControlledVisionService(
            capture=DesktopScreenCapture(),
            provider=OllamaVisionProvider(
                base_url=os.getenv("AURA_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                model=os.getenv("AURA_VISION_MODEL", "qwen3-vl"),
                timeout_seconds=float(os.getenv("AURA_VISION_TIMEOUT_SECONDS", "30")),
            ),
            consent=lambda principal_id: principal_id in vision_principals,
        )
    else:
        app.state.controlled_vision_service = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        research_provider = None
        kokoro_provider = None
        event_coordinator = None

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
            # TTS always crosses MCPGateway + Permission Engine; the provider
            # connection itself is not an authorization grant.
            app.state.speech_synthesizer = GatewaySpeechSynthesizer(
                gateway=gateway, principal_id=os.getenv("AURA_SPEECH_PRINCIPAL", "local_owner"),
                capability_id=kokoro_config.capability_id,
                operation_id=kokoro_config.operation_id,
                tool_name=kokoro_config.tool_name,
                resource_scope=os.getenv("AURA_SPEECH_RESOURCE_SCOPE", "local_default"),
            )
            app.state.speech_session_manager = FullDuplexSessionManager(
                recognizer=FasterWhisperRecognizer(
                    model_size=os.getenv("AURA_STT_MODEL", "small"),
                    device=os.getenv("AURA_STT_DEVICE", "cpu"),
                    compute_type=os.getenv("AURA_STT_COMPUTE_TYPE", "int8"),
                ),
                synthesizer=app.state.speech_synthesizer,
                player=EventBusAudioPlayer(kernel.event_bus),
                event_bus=kernel.event_bus,
            )

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

            # The runtime owns the sole EventBus dispatch loop. Start it only
            # after the Kernel and existing event bridge are ready.
            event_runtime.start()

            # Reflection integration is conditional: it is activated only if
            # the composition root explicitly provides the existing daemon.
            reflection_daemon = getattr(
                _app.state, "idle_memory_reflection_daemon", None
            )
            if reflection_daemon is not None and os.getenv(
                "AURA_EVENT_REFLECTION_ENABLED", "0"
            ).strip().casefold() in {"1", "true", "yes", "on"}:
                event_coordinator = EventDrivenOrchestrationCoordinator(
                    event_bus=kernel.event_bus,
                    reflection_daemon=reflection_daemon,
                    enabled=True,
                    cooldown_seconds=float(
                        os.getenv("AURA_EVENT_REFLECTION_COOLDOWN_SECONDS", "300")
                    ),
                )
                event_coordinator.start()
                _app.state.event_driven_orchestration = event_coordinator

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

            if event_coordinator is not None:
                try:
                    event_coordinator.stop()
                except Exception:
                    logger.exception("Event-driven orchestration unsubscribe failed")

            try:
                await event_runtime.stop(timeout_seconds=5.0)
            except Exception:
                logger.exception("EventBus runtime shutdown failed")

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
