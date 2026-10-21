"""Local-only API for explicitly requested governed autonomous runs."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/autonomy", tags=["governed-autonomy"])


def _require_local(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Local client required")


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)
    principal_id: str = Field(min_length=1, max_length=128)
    resource_scope: str = Field(min_length=1, max_length=256)
    confirmed: bool = False


def _runs(request: Request) -> dict:
    runs = getattr(request.app.state, "autonomy_runs", None)
    if runs is None:
        runs = {}
        request.app.state.autonomy_runs = runs
    return runs


@router.post("/runs", status_code=202)
async def start_run(body: RunRequest, request: Request) -> dict[str, object]:
    _require_local(request)
    loop = getattr(request.app.state, "governed_autonomous_loop", None)
    if loop is None:
        raise HTTPException(status_code=503, detail="Governed autonomy is disabled or not configured")
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required to start autonomous execution")
    if body.principal_id not in {
        item.strip() for item in __import__("os").getenv("AURA_AUTONOMY_PRINCIPALS", "local_owner").split(",")
        if item.strip()
    }:
        raise HTTPException(status_code=403, detail="Principal is not enabled for autonomous execution")
    run_id = str(uuid4())
    cancel_event = asyncio.Event()

    async def execute():
        try:
            result = await loop.run(
                goal=body.goal, principal_id=body.principal_id,
                resource_scope=body.resource_scope, cancelled=cancel_event.is_set,
            )
            record["result"] = asdict(result)
            record["state"] = result.status
        except asyncio.CancelledError:
            record["state"] = "cancelled"
            raise
        except Exception as exc:
            record["state"] = "needs_review"
            record["error"] = type(exc).__name__

    record = {
        "run_id": run_id, "principal_id": body.principal_id,
        "goal": body.goal, "state": "running", "result": None, "error": None,
        "cancel_event": cancel_event, "task": None,
    }
    record["task"] = asyncio.create_task(execute(), name=f"aura-autonomy-{run_id}")
    _runs(request)[run_id] = record
    return {"run_id": run_id, "state": "running", "note": "Task tools remain subject to MCP Gateway and Permission Engine."}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, principal_id: str) -> dict[str, object]:
    _require_local(request)
    record = _runs(request).get(run_id)
    if record is None or record["principal_id"] != principal_id:
        raise HTTPException(status_code=404, detail="Autonomy run not found")
    return {key: value for key, value in record.items() if key not in {"task", "cancel_event"}}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request, principal_id: str) -> dict[str, object]:
    _require_local(request)
    record = _runs(request).get(run_id)
    if record is None or record["principal_id"] != principal_id:
        raise HTTPException(status_code=404, detail="Autonomy run not found")
    if record["state"] != "running":
        return {"run_id": run_id, "state": record["state"], "cancel_requested": False}
    record["cancel_event"].set()
    return {"run_id": run_id, "state": "cancellation_requested", "cancel_requested": True}
