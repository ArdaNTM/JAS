from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import logging
import os
import re
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
from aura_core.config.storage import StorageMode, storage_mode_from_environment, validate_storage_mode
from aura_core.enterprise.policy_bundle import PolicyBundle
from aura_core.enterprise.approval_store import SQLiteApprovalStore
from aura_core.enterprise.runtime_controls import HashChainAuditLedger
from aura_core.mcp.graph_memory_provider import GraphMemoryMCPProvider
from aura_core.memory.graph_store import SQLiteGraphStore, PostgreSQLGraphStore
from aura_core.application.windows_screen_driver import WindowsDesktopInputDriver, DesktopVLMAdapter
from aura_core.mcp.screen_control_provider import ScreenControlMCPProvider
from aura_core.application.swarm_orchestration import SwarmOrchestrator
from aura_core.enterprise.postgresql_approval_store import PostgreSQLApprovalStore
from aura_core.enterprise.postgresql_workflow_store import PostgreSQLWorkflowStore
from aura_core.application.postgresql_task_state_machine import PostgreSQLTaskStateMachine
from aura_core.application.postgresql_task_memory import PostgreSQLTaskMemoryCoordinator
from aura_core.memory.postgresql_hierarchical_memory import PostgreSQLHierarchicalMemory
from aura_core.persistence.remote_checkpoint_artifacts import RemoteCheckpointArtifacts
from aura_core.storage.s3_object_storage import S3ObjectStorage
from aura_core.enterprise.workflow_store import SQLiteWorkflowStore
from aura_core.security.http_auth import load_http_auth_config
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
from aura_core.mcp.provider import ProviderDefinition
from aura_core.mcp.codeact_provider import CodeActSandboxMCPProvider
from aura_core.memory.tiered_memory_mcp import TieredMemoryMCPProvider
from aura_core.application.reflection_service import ReflectionService
from aura_core.skills.agent_skills_mcp import AgentSkillsMCPRegistry
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.research.config import ResearchMCPConfig
from aura_core.filesystem.config import LocalFilesystemMCPConfig
from aura_core.filesystem.provider_bootstrap import register_local_filesystem_mcp
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

def _load_policy_bundle_from_environment() -> PolicyBundle | None:
    """Load the configured policy bundle and enforce an optional semantic digest pin."""
    policy_bundle_path = os.getenv("AURA_POLICY_BUNDLE_PATH", "").strip()
    expected_digest = os.getenv("AURA_POLICY_BUNDLE_SHA256", "").strip()

    if expected_digest and not policy_bundle_path:
        raise ValueError("AURA_POLICY_BUNDLE_SHA256 requires AURA_POLICY_BUNDLE_PATH")
    if expected_digest and re.fullmatch(r"[0-9a-fA-F]{64}", expected_digest) is None:
        raise ValueError("AURA_POLICY_BUNDLE_SHA256 must be a 64-character hexadecimal SHA-256 digest")
    if not policy_bundle_path:
        return None

    # A configured path is fail-closed. The optional pin is checked against the
    # canonical policy digest, so formatting/BOM differences do not change policy identity.
    policy_bundle = PolicyBundle.from_json_file(policy_bundle_path)
    if expected_digest and not hmac.compare_digest(
        policy_bundle.digest, expected_digest.casefold()
    ):
        raise ValueError("Policy bundle digest does not match AURA_POLICY_BUNDLE_SHA256")
    return policy_bundle


def _load_approval_fingerprint_key() -> bytes | None:
    """Load an optional base64 HMAC key; approvals stay disabled if it is absent."""
    encoded = os.getenv("AURA_APPROVAL_FINGERPRINT_KEY", "").strip()
    if not encoded:
        return None
    try:
        key = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError(
            "AURA_APPROVAL_FINGERPRINT_KEY must be valid base64"
        ) from exc
    if len(key) < 32:
        raise RuntimeError(
            "AURA_APPROVAL_FINGERPRINT_KEY must decode to at least 32 bytes"
        )
    return key


def build_app() -> FastAPI:
    # Keep the remote rollout gate authoritative; once released, the remote branch
    # below selects only remote stores and never constructs SQLite persistence.
    validate_storage_mode()
    storage_mode = storage_mode_from_environment()
    kernel_config = KernelConfig.from_environment()
    policy_bundle = _load_policy_bundle_from_environment()
    kernel = AuraKernel(kernel_config, policy_bundle=policy_bundle)
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
    filesystem_config = LocalFilesystemMCPConfig.from_env()
    research_tools = MCPToolRegistry()
    tts_tools = MCPToolRegistry()
    filesystem_tools = MCPToolRegistry()

    http_bearer_token, http_principal_id = load_http_auth_config()
    approval_fingerprint_key = _load_approval_fingerprint_key()
    approval_store = None
    task_state_machine = None
    workflow_store = None
    task_memory = None
    checkpoint_artifacts = None
    startup_stores = []
    remote_objects = None

    if storage_mode is StorageMode.REMOTE:
        database_url = os.getenv("AURA_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("AURA_DATABASE_URL is required in remote storage mode")
        task_state_machine = PostgreSQLTaskStateMachine(database_url, event_bus=kernel.event_bus)
        workflow_store = PostgreSQLWorkflowStore(database_url)
        task_memory_store = PostgreSQLHierarchicalMemory(database_url)
        task_memory = PostgreSQLTaskMemoryCoordinator(task_memory_store)
        if approval_fingerprint_key is not None:
            approval_store = PostgreSQLApprovalStore(database_url)
        remote_objects = S3ObjectStorage(
            endpoint_url=os.environ["AURA_OBJECT_STORAGE_ENDPOINT"],
            bucket=os.environ["AURA_OBJECT_STORAGE_BUCKET"],
            access_key=os.getenv("AURA_OBJECT_STORAGE_ACCESS_KEY", os.getenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "")),
            secret_key=os.getenv("AURA_OBJECT_STORAGE_SECRET_KEY", os.getenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", "")),
            region=os.getenv("AURA_OBJECT_STORAGE_REGION", "us-east-1"),
            session_token=os.getenv("AURA_OBJECT_STORAGE_SESSION_TOKEN"),
        )
        checkpoint_artifacts = RemoteCheckpointArtifacts(remote_objects, workflow_store)
        startup_stores = [task_state_machine, workflow_store, task_memory]
        if approval_store is not None:
            startup_stores.append(approval_store)
    else:
        if approval_fingerprint_key is not None:
            approval_database_path = os.getenv(
                "AURA_APPROVAL_DB_PATH",
                os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "AURA", "approvals.sqlite3"),
            )
            os.makedirs(os.path.dirname(os.path.abspath(approval_database_path)), exist_ok=True)
            approval_store = SQLiteApprovalStore(approval_database_path)

        task_database_path = os.getenv(
            "AURA_TASK_DB_PATH",
            str(os.getenv("LOCALAPPDATA", os.path.expanduser("~"))) + "/AURA/tasks.sqlite3",
        )
        task_state_machine = TaskStateMachine(task_database_path, event_bus=kernel.event_bus)
        workflow_database_path = os.getenv(
            "AURA_WORKFLOW_DB_PATH",
            str(os.getenv("LOCALAPPDATA", os.path.expanduser("~"))) + "/AURA/workflows.sqlite3",
        )
        os.makedirs(os.path.dirname(os.path.abspath(workflow_database_path)), exist_ok=True)
        workflow_store = SQLiteWorkflowStore(workflow_database_path)
        task_memory = TaskMemoryCoordinator.from_environment()

    # Local mode uses durable SQLite, remote mode uses PostgreSQL only.
    # Remote graph initialization participates in the existing startup rollback.
    if storage_mode is StorageMode.REMOTE:
        graph_store = PostgreSQLGraphStore(database_url)
        startup_stores.append(graph_store)
    else:
        graph_path = os.getenv(
            "AURA_GRAPH_DB_PATH",
            os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
                         "AURA", "graph-memory.sqlite3"),
        )
        graph_store = SQLiteGraphStore(graph_path)

    # Desktop control is disabled unless explicitly configured with an
    # interactive ApprovalStore. Enabling it on unsupported platforms aborts.
    screen_control_enabled = os.getenv(
        "AURA_SCREEN_CONTROL_ENABLED", "0"
    ).strip().casefold() in {"1", "true", "yes", "on"}
    screen_control_provider = ScreenControlMCPProvider()
    if screen_control_enabled:
        if approval_store is None:
            raise RuntimeError("ScreenControl requires AURA_APPROVAL_FINGERPRINT_KEY and ApprovalStore")
        screen_control_provider = ScreenControlMCPProvider(
            vision=DesktopVLMAdapter(
                DesktopScreenCapture(),
                OllamaVisionProvider(
                    base_url=os.getenv("AURA_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                    model=os.getenv("AURA_VISION_MODEL", "qwen3-vl"),
                    timeout_seconds=float(os.getenv("AURA_VISION_TIMEOUT_SECONDS", "30")),
                ),
            ),
            input_driver=WindowsDesktopInputDriver(),
        )
        kernel.permission_engine.add_policy(PermissionPolicy(
            policy_id="local-owner:screen-control:interactive",
            policy_version="1.0.0",
            principal_id=http_principal_id,
            capability_id="ScreenControl", operation_id="ScreenControl",
            resource_scope="local_default",
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
            decision=AuthorizationDecision.REQUIRE_APPROVAL,
        ))

    # Register governed MCP adapters through the Kernel registries.
    memory_service = ServiceDefinition(
        name="tiered_memory_mcp", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP,
        capabilities={"memory.core.append", "memory.core.read", "memory.archival.append", "memory.archival.search"},
        tags={"memory", "mcp", "governed"},
    )
    memory_provider_id = "aura.tiered-memory"
    memory_provider = TieredMemoryMCPProvider(task_memory.store)
    kernel.service_registry.register(memory_service, memory_provider)
    kernel.provider_registry.register(
        ProviderDefinition(provider_id=memory_provider_id, name="Tiered Memory MCP",
            version="1.0.0", service_id=memory_service.service_id,
            description="Principal-scoped core and archival memory"),
        memory_provider,
    )
    for cap_id, tool_name, risk in (
        ("memory.core.append", "core_memory_append", "medium"),
        ("memory.core.read", "core_memory_read", "low"),
        ("memory.archival.append", "archival_memory_append", "medium"),
        ("memory.archival.search", "archival_memory_search", "low"),
    ):
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap_id, name=tool_name, version="1.0.0",
            description="Governed tiered-memory MCP operation",
            provider_id=memory_provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.MEMORY, tool_name=tool_name, risk_level=risk,
            required_permissions=frozenset({cap_id}),
        ))

    codeact_service = ServiceDefinition(
        name="codeact_sandbox_mcp", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities={"sandbox.codeact.execute"},
        tags={"sandbox", "docker", "mcp", "high-risk"},
    )
    codeact_provider_id = "aura.codeact-sandbox"
    codeact_provider = CodeActSandboxMCPProvider()
    kernel.service_registry.register(codeact_service, codeact_provider)
    kernel.provider_registry.register(
        ProviderDefinition(provider_id=codeact_provider_id, name="CodeAct Docker Sandbox",
            version="1.0.0", service_id=codeact_service.service_id,
            description="Digest-pinned isolated Docker execution"),
        codeact_provider,
    )
    kernel.capability_registry.register(CapabilityDefinition(
        capability_id="sandbox.codeact.execute", name="CodeAct Sandbox Execute",
        version="1.0.0", description="Execute untrusted code in isolated Docker",
        provider_id=codeact_provider_id, provider_type=ProviderType.MCP,
        category=CapabilityCategory.CODING, tool_name="codeact_execute",
        risk_level="high", required_permissions=frozenset({"sandbox.codeact.execute"}),
    ))

    gateway_audit_ledger = HashChainAuditLedger()
    # Registration declares availability, never grants authorization.
    for provider_id, service_name, instance, definitions in (
        ("aura.graph-memory", "graph_memory_mcp", GraphMemoryMCPProvider(graph_store), (
            ("memory.graph.query", "graph_memory_query", "low", CapabilityCategory.MEMORY),
            ("memory.graph.insert", "graph_memory_insert", "medium", CapabilityCategory.MEMORY),
        )),
        ("aura.screen-control", "screen_control_mcp", screen_control_provider, (
            ("ScreenControl", "screen_control", "high", CapabilityCategory.AUTOMATION),
        )),
    ):
        service = ServiceDefinition(
            name=service_name, version="1.0.0", provider="aura",
            category=ServiceCategory.MCP,
            capabilities=frozenset(row[0] for row in definitions),
            tags={"governed", "mcp"},
        )
        kernel.service_registry.register(service, instance)
        kernel.provider_registry.register(ProviderDefinition(
            provider_id=provider_id, name=service_name, version="1.0.0",
            service_id=service.service_id,
        ), instance)
        for cap_id, tool, risk, category in definitions:
            kernel.capability_registry.register(CapabilityDefinition(
                capability_id=cap_id, name=tool, version="1.0.0",
                description="Gateway-governed MCP capability",
                provider_id=provider_id, provider_type=ProviderType.MCP,
                category=category, tool_name=tool, risk_level=risk,
                required_permissions=frozenset({cap_id}),
            ))

    gateway = MCPGateway(
        capability_registry=kernel.capability_registry,
        provider_registry=kernel.provider_registry,
        permission_engine=kernel.permission_engine,
        approval_store=approval_store,
        approval_fingerprint_key=approval_fingerprint_key,
        event_bus=kernel.event_bus,
        audit_ledger=gateway_audit_ledger,
    )

    task_service = AgentTaskService(
        AgentExecutor(gateway=gateway, event_bus=kernel.event_bus),
        memory=task_memory,
        state_machine=task_state_machine,
        workflow_store=workflow_store,
        checkpoint_artifacts=checkpoint_artifacts,
    )

    app = create_composed_app(
        config=kernel_config.runtime,
        backend_config=kernel_config.backend,
        task_service=task_service,
        event_bus=kernel.event_bus,
        permission_engine=kernel.permission_engine,
        kernel=kernel,
        gateway=gateway,
        approval_store=approval_store,
        storage_mode=storage_mode,
    )

    app.state.http_bearer_token = http_bearer_token
    app.state.http_principal_id = http_principal_id
    app.state.approval_store = approval_store
    app.state.gateway_audit_ledger = gateway_audit_ledger
    app.state.graph_store = graph_store
    app.state.screen_control_enabled = screen_control_enabled
    app.state.swarm_orchestrator = SwarmOrchestrator(gateway=gateway, event_bus=kernel.event_bus)
    app.state.storage_mode = storage_mode
    app.state.task_memory = task_memory
    app.state.checkpoint_artifacts = checkpoint_artifacts
    app.state.remote_object_storage = remote_objects
    # Imported skills are declarative proposals only; invocation still requires Gateway authorization.
    app.state.agent_skills_mcp_registry = AgentSkillsMCPRegistry()

    event_runtime = EventBusRuntime(
        kernel.event_bus,
        enabled=os.getenv("AURA_EVENT_RUNTIME_ENABLED", "1").strip().casefold()
        not in {"0", "false", "no", "off"},
        idle_seconds=float(os.getenv("AURA_EVENT_IDLE_SECONDS", "300")),
        poll_interval_seconds=float(os.getenv("AURA_EVENT_POLL_INTERVAL_SECONDS", "0.1")),
    )
    app.state.event_bus_runtime = event_runtime
    app.state.task_state_machine = task_state_machine
    app.state.workflow_store = workflow_store
    app.state.task_service = task_service

    def _reflection_planner(failure: dict) -> dict:
        return {"action": "replan", "reason": "tool_execution_failed",
                "failed_tool": failure.get("tool_name"),
                "requires_new_gateway_authorization": True, "automatic_execution": False}

    reflection_service = ReflectionService(kernel.event_bus, task_state_machine, _reflection_planner)
    app.state.reflection_service = reflection_service
    app.state.last_reflection_plan = None

    def _capture_reflection_plan(event: KernelEvent) -> None:
        app.state.last_reflection_plan = dict(event.payload)

    app.state.reflection_plan_unsubscribe = kernel.event_bus.subscribe(
        "ReflectionPlanReady", _capture_reflection_plan
    )

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
        filesystem_provider = None
        event_coordinator = None
        initialized_stores = []

        async def close_store(store):
            close = getattr(store, "close", None)
            if close is None:
                return
            result = close()
            if hasattr(result, "__await__"):
                await result

        # Initialize durable adapters before serving requests. If any remote
        # store fails, startup aborts instead of falling back to local files.
        try:
            for store in startup_stores:
                await store.initialize()
                initialized_stores.append(store)
        except Exception:
            for store in reversed(initialized_stores):
                try:
                    await close_store(store)
                except Exception:
                    logger.exception("Persistence rollback failed")
            raise

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
            try:
                yield
            finally:
                reflection_service.close()
                app.state.reflection_plan_unsubscribe()
                for store in reversed(startup_stores):
                    try:
                        await close_store(store)
                    except Exception:
                        logger.exception("Persistence shutdown failed")
                if not startup_stores:
                    for store in (approval_store, workflow_store, task_state_machine, task_memory):
                        if store is not None:
                            try:
                                await close_store(store)
                            except Exception:
                                logger.exception("Local persistence shutdown failed")
            return

        try:
            logger.info(
                "LIFESPAN: registering research MCP"
            )

            research_provider = await register_research_mcp(
                config=research_config,
                services=kernel.service_registry,
                providers=kernel.provider_registry,
                capabilities=kernel.capability_registry,
                tools=research_tools,
            )
            report_mcp_healthy(research_config)

            kokoro_provider = await register_kokoro_mcp(
                config=kokoro_config,
                services=kernel.service_registry,
                providers=kernel.provider_registry,
                capabilities=kernel.capability_registry,
                tools=tts_tools,
            )
            report_mcp_healthy(kokoro_config)

            filesystem_provider = await register_local_filesystem_mcp(
                config=filesystem_config,
                services=kernel.service_registry,
                providers=kernel.provider_registry,
                capabilities=kernel.capability_registry,
                tools=filesystem_tools,
            )
            report_mcp_healthy(filesystem_config)
            # File reads are still dispatched through MCPGateway and Permission Engine.
            # Registration alone is not permission to execute the tool.

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
            # Public web retrieval is read-only but still requires an explicit,
            # principal- and scope-bound grant before MCP dispatch.
            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id="local-owner:internet.fetch:local_default",
                    policy_version="1.0.0",
                    principal_id="local_owner",
                    capability_id="internet.fetch",
                    operation_id="internet.fetch",
                    resource_scope="local_default",
                    authorization_level=AuthorizationLevel.EXECUTE,
                    decision=AuthorizationDecision.ALLOW,
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

            # Local filesystem reads are limited to the registered test-data capability.
            # MCPGateway still enforces this policy before any provider tool invocation.
            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id="local-owner:filesystem.read_test_data:test-data",
                    policy_version="1.0.0",
                    principal_id="local_owner",
                    capability_id="filesystem.read_test_data",
                    operation_id="filesystem.read_test_data",
                    resource_scope="local_default",
                    authorization_level=AuthorizationLevel.READ,
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

            reflection_service.close()
            app.state.reflection_plan_unsubscribe()

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

            if filesystem_provider is not None:
                try:
                    await filesystem_provider.close()
                except Exception:
                    logger.exception("Local filesystem provider shutdown failed")

            if startup_stores:
                for store in reversed(startup_stores):
                    try:
                        await close_store(store)
                    except Exception:
                        logger.exception("Persistence shutdown failed")
            else:
                for store in (approval_store, workflow_store, task_state_machine, task_memory):
                    if store is not None:
                        try:
                            await close_store(store)
                        except Exception:
                            logger.exception("Local persistence shutdown failed")

            logger.info(
                "AURA LIFESPAN SHUTDOWN COMPLETE"
            )

    _app_lifespan = lifespan
    app.router.lifespan_context = _app_lifespan

    return app


app = build_app()
