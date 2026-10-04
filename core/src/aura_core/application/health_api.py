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
    except Exception as exc:
        return JSONResponse(
            {
                "status": "not_ready",
                "error": type(exc).__name__,
            },
            status_code=503,
        )

    return JSONResponse({"status": "ready"})