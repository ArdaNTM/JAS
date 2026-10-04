from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.routing import WebSocketRoute

from aura_core.application.api import create_api
from aura_core.application.approval_api import router as approval_router
from aura_core.application.event_bridge import EventBusLiveBridge
from aura_core.kernel.diagnostics import DiagnosticsService
from aura_core.application.health_api import health, health_live, health_ready, router as health_router
from aura_core.application.live_api import router as live_router
from aura_core.application.live_events import LiveEventBroker
from aura_core.application.ws_api import router as ws_router
from aura_core.kernel.runtime import KernelState
from aura_core.security.ws_ticket import WebSocketTicketManager


def create_composed_app(
    *,
    config,
    backend_config=None,
    transport=None,
    task_service=None,
    event_bus=None,
    permission_engine=None,
    kernel=None,
) -> FastAPI:
    """
    Canonical AURA HTTP composition root.

    Task execution remains:
    HTTP -> AgentTaskService -> AgentExecutor -> MCPGateway ->
    PermissionEngine -> Provider.
    """

    app = create_api(
        config=config,
        backend_config=backend_config,
        transport=transport,
        task_service=task_service,
    )

    app.state.kernel = kernel
    app.state.permission_engine = permission_engine

    broker = getattr(app.state, "live_events", None)
    if not isinstance(broker, LiveEventBroker):
        broker = LiveEventBroker()
        app.state.live_events = broker

    app.state.ws_ticket_manager = WebSocketTicketManager()

    # Router paths already include /api. Do not add a duplicate prefix.
    app.include_router(health_router)
    app.include_router(approval_router)
    app.include_router(ws_router)
    app.include_router(live_router)

    app.state.event_bridge = (
        EventBusLiveBridge(event_bus, broker)
        if event_bus is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        bridge = application.state.event_bridge

        if bridge is not None:
            await bridge.start()

        try:
            yield
        finally:
            if bridge is not None:
                await bridge.stop()

            active_kernel = getattr(application.state, "kernel", None)
            if (
                active_kernel is not None
                and active_kernel.state is KernelState.RUNNING
            ):
                active_kernel.stop()

    app.router.lifespan_context = lifespan
    # ------------------------------------------------------------


    # AURA canonical health route guarantee.
    _aura_paths = {
        getattr(route, "path", None)
        for route in app.routes
    }

    if "/api/health" not in _aura_paths:
        app.add_api_route(
            "/api/health",
            health,
            methods=["GET"],
            tags=["health"],
        )

    _aura_paths = {
        getattr(route, "path", None)
        for route in app.routes
    }

    if "/api/health/live" not in _aura_paths:
        app.add_api_route(
            "/api/health/live",
            health_live,
            methods=["GET"],
            tags=["health"],
        )

    _aura_paths = {
        getattr(route, "path", None)
        for route in app.routes
    }

    if "/api/health/ready" not in _aura_paths:
        app.add_api_route(
            "/api/health/ready",
            health_ready,
            methods=["GET"],
            tags=["health"],
        )


    # --------------------------------------------------------
    # AURA Kernel Diagnostics HTTP surface
    #
    # DiagnosticsService zaten Kernel seviyesinde bulunuyor.
    # HTTP katmanı yalnızca read-only snapshot yayınlar.
    # --------------------------------------------------------

    if "/api/diagnostics" not in {
        getattr(route, "path", None)
        for route in app.routes
    }:

        def _aura_diagnostics() -> dict:
            active_kernel = getattr(app.state, "kernel", None)

            if active_kernel is None:
                return {
                    "status": "unavailable",
                    "reason": "kernel_not_initialized",
                }

            service_registry = getattr(
                active_kernel,
                "service_registry",
                None,
            )

            capability_registry = getattr(
                active_kernel,
                "capability_registry",
                None,
            )

            health_monitor = getattr(
                active_kernel,
                "health_monitor",
                None,
            )

            permission_engine = getattr(
                active_kernel,
                "permission_engine",
                None,
            )

            event_bus = getattr(
                active_kernel,
                "event_bus",
                None,
            )

            if (
                service_registry is None
                or capability_registry is None
                or health_monitor is None
                or permission_engine is None
                or event_bus is None
            ):
                return {
                    "status": "degraded",
                    "reason": "kernel_components_not_available",
                }

            diagnostics_service = DiagnosticsService(
                active_kernel.config,
                service_registry,
                capability_registry,
                health_monitor,
                permission_engine,
                event_bus,
            )

            snapshot = diagnostics_service.snapshot()

            return {
                "status": "ok",
                "generated_at": snapshot.generated_at.isoformat(),
                "configuration": snapshot.configuration,
                "services": list(snapshot.services),
                "capabilities": list(snapshot.capabilities),
                "health": list(snapshot.health),
                "authorization": snapshot.authorization,
                "events": snapshot.events,
                "warnings": list(snapshot.warnings),
            }

        app.add_api_route(
            "/api/diagnostics",
            _aura_diagnostics,
            methods=["GET"],
            tags=["diagnostics"],
        )
    return app
