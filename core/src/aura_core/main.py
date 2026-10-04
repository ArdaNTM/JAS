from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from aura_core.agent.runtime import AgentExecutor
from aura_core.application.composition import create_composed_app
from aura_core.application.tasks import AgentTaskService
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.runtime import AuraKernel
from aura_core.mcp.gateway import MCPGateway


def build_app():
    """The only supported AURA HTTP composition root."""

    kernel_config = KernelConfig.from_environment()

    kernel = AuraKernel(kernel_config)
    kernel.bootstrap()
    kernel.start()

    if (
        kernel.capability_registry is None
        or kernel.provider_registry is None
        or kernel.permission_engine is None
    ):
        raise RuntimeError("AURA kernel registries were not initialized")

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