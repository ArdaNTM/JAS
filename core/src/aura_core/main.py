from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware

from aura_core.agent.runtime import AgentExecutor
from aura_core.application.composition import create_composed_app
from aura_core.application.tasks import AgentTaskService
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.runtime import AuraKernel
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionPolicy,
)
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.research.config import ResearchMCPConfig
from aura_core.research.provider_bootstrap import register_research_mcp


def build_app():
    """The only supported AURA HTTP composition root."""

    kernel_config = KernelConfig.from_environment()

    kernel = AuraKernel(kernel_config)
    kernel.bootstrap()

    if (
        kernel.capability_registry is None
        or kernel.provider_registry is None
        or kernel.permission_engine is None
        or kernel.service_registry is None
    ):
        raise RuntimeError("AURA kernel registries were not initialized")

    research_config = ResearchMCPConfig.from_env()
    research_tools = MCPToolRegistry()

    gateway = MCPGateway(
        capability_registry=kernel.capability_registry,
        provider_registry=kernel.provider_registry,
        permission_engine=kernel.permission_engine,
    )

    task_service = AgentTaskService(
        AgentExecutor(
            gateway=gateway,
            event_bus=kernel.event_bus,
        )
    )

    app = create_composed_app(
        config=kernel_config.runtime,
        backend_config=kernel_config.backend,
        task_service=task_service,
        event_bus=kernel.event_bus,
        permission_engine=kernel.permission_engine,
        kernel=kernel,
    )

    @asynccontextmanager
    async def lifespan(_app):
        research_provider = None

        try:
            research_provider = await register_research_mcp(
                config=research_config,
                services=kernel.service_registry,
                providers=kernel.provider_registry,
                capabilities=kernel.capability_registry,
                tools=research_tools,
            )
            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id="local-user:internet.search:public-web",
                    policy_version="1.0.0",
                    principal_id="local-user",
                    capability_id="internet.search",
                    operation_id="internet.search",
                    resource_scope="public-web",
                    authorization_level=AuthorizationLevel.EXECUTE,
                    decision=AuthorizationDecision.ALLOW,
                )
            )

            kernel.start()
            yield

        finally:
            if research_provider is not None:
                await research_provider.close()

            if kernel.state.value == "running":
                kernel.stop()

    app.router.lifespan_context = lifespan

    origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # Electron production shell uses a file:// origin. It is deliberately opt-in.
    if os.getenv("AURA_ALLOW_FILE_ORIGIN") == "1":
        origins.append("null")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    return app


app = build_app()
