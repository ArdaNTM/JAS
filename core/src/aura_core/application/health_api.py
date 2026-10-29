from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(request: Request) -> JSONResponse:
    """
    Machine-readable AURA health projection.

    This endpoint deliberately reports component availability without
    exposing credentials or internal secrets.
    """

    components: dict[str, object] = {}

    readiness = getattr(request.app.state, "readiness", None)

    if readiness is not None:
        try:
            readiness.check()
            components["inference"] = {
                "status": "healthy",
            }
        except Exception as exc:
            components["inference"] = {
                "status": "unavailable",
                "error": type(exc).__name__,
            }
    else:
        components["inference"] = {
            "status": "not_configured",
        }

    kernel = getattr(request.app.state, "kernel", None)

    if kernel is not None:
        components["kernel"] = {
            "status": str(kernel.state),
        }
    else:
        components["kernel"] = {
            "status": "not_configured",
        }

    gateway = getattr(request.app.state, "mcp_gateway", None)
    components["gateway"] = {
        "status": "configured" if gateway is not None else "not_configured",
    }

    permission_engine = getattr(
        request.app.state,
        "permission_engine",
        None,
    )
    components["permission_engine"] = {
        "status": (
            "configured"
            if permission_engine is not None
            else "not_configured"
        ),
    }

    task_service = getattr(
        request.app.state,
        "task_service",
        None,
    )

    components["agent_runtime"] = {
        "status": (
            "configured"
            if task_service is not None
            else "not_configured"
        )
    }

    return JSONResponse(
        {
            "status": (
                "healthy"
                if all(
                    value.get("status") not in {
                        "unavailable",
                    }
                    for value in components.values()
                    if isinstance(value, dict)
                )
                else "degraded"
            ),
            "components": components,
        }
    )


@router.get("/api/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/health/ready")
async def health_ready(request: Request) -> JSONResponse:
    readiness = getattr(
        request.app.state,
        "readiness",
        None,
    )

    if readiness is None:
        return JSONResponse(
            {"status": "not_configured"},
            status_code=503,
        )

    try:
        readiness.check()
        storage_mode = getattr(request.app.state, "storage_mode", "local")
        storage_mode = getattr(storage_mode, "value", storage_mode)
        if str(storage_mode).lower() == "remote":
            task_state_machine = getattr(request.app.state, "task_state_machine", None)
            object_storage = getattr(request.app.state, "remote_object_storage", None)
            if task_state_machine is None or object_storage is None:
                raise RuntimeError("Remote persistence health checks are not configured")
            from sqlalchemy import text
            async with task_state_machine._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await __import__("asyncio").to_thread(object_storage.head_bucket)
    except Exception as exc:
        return JSONResponse({"status": "not_ready", "error": type(exc).__name__}, status_code=503)

    return JSONResponse({"status": "ready"})