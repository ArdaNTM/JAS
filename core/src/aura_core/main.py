from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aura_core.agent.runtime import AgentExecutor
from aura_core.application.composition import create_composed_app
from aura_core.application.tasks import AgentTaskService
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionPolicy,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.research.config import ResearchMCPConfig
from aura_core.research.provider_bootstrap import (
    register_research_mcp,
)


logger = logging.getLogger(
    "aura_core.lifecycle"
)


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
    async def lifespan(_app: FastAPI):
        research_provider = None

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

            kernel.permission_engine.add_policy(
                PermissionPolicy(
                    policy_id=(
                        "local-user:"
                        "internet.search:"
                        "public-web"
                    ),
                    policy_version="1.0.0",
                    principal_id="local-user",
                    capability_id="internet.search",
                    operation_id="internet.search",
                    resource_scope="public-web",
                    authorization_level=(
                        AuthorizationLevel.EXECUTE
                    ),
                    decision=(
                        AuthorizationDecision.ALLOW
                    ),
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
                    await asyncio.wait_for(
                        research_provider.close(),
                        timeout=10.0,
                    )
                except Exception:
                    logger.exception(
                        "Research provider shutdown failed"
                    )

            logger.info(
                "AURA LIFESPAN SHUTDOWN COMPLETE"
            )

    _app_lifespan = lifespan
    app.router.lifespan_context = _app_lifespan

    origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    if os.getenv(
        "AURA_ALLOW_FILE_ORIGIN"
    ) == "1":
        origins.append("null")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=[
            "GET",
            "POST",
            "OPTIONS",
        ],
        allow_headers=[
            "Content-Type",
            "X-Request-ID",
        ],
    )

    return app


app = build_app()

# AURA CORS BEGIN
_AURA_CORS_ORIGINS = [
    "http://127.0.0.1:4173",
    "http://localhost:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_AURA_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# AURA CORS END

















