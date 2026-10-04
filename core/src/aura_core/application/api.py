import hmac
import logging
import os
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from fastapi import Request
from fastapi.responses import JSONResponse

from aura_core.application.bootstrap import create_application
from aura_core.application.readiness import ReadinessService
from aura_core.application.service import InferenceService
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.errors import (
    BackendInvalidResponseError,
    BackendUnavailableError,
)
from aura_core.runtime.transport import HttpJsonTransport, JsonTransport
from aura_core.observability.metrics import RequestMetrics
from aura_core.agent.runtime import Plan, PlanStep, StepResult, Task
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.kernel.permissions import RiskLevel
from aura_core.application.live_events import LiveEventBroker


logger = logging.getLogger("aura_core.http")


class TaskStepPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    risk_level: RiskLevel
    arguments: dict[str, object] = Field(default_factory=dict)
    depends_on: set[str] = Field(default_factory=set)
    max_attempts: int = Field(default=1, ge=1, le=3)


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    resource_scope: str = Field(min_length=1)
    steps: list[TaskStepPayload] = Field(min_length=1, max_length=32)


class TaskResponse(BaseModel):
    task_id: str
    plan_id: str
    state: str
    steps: list[dict[str, object]]


def create_api(
    config: RuntimeConfig,
    backend_config: BackendConfig | None = None,
    transport: JsonTransport | None = None,
    task_service: AgentTaskService | None = None,
    live_events: LiveEventBroker | None = None,
) -> FastAPI:
    resolved_backend_config = (
        backend_config or BackendConfig.from_environment()
    )
    application: InferenceService = create_application(
        config,
        backend_config=resolved_backend_config,
        transport=transport,
    )
    readiness = ReadinessService(
        config=config,
        backend_config=resolved_backend_config,
        transport=transport or HttpJsonTransport(),
    )

    app = FastAPI(
        title="AURA Core",
        version="0.1.0",
    )
    metrics = RequestMetrics()
    app.state.readiness = readiness
    app.state.metrics = metrics
    app.state.task_service = task_service
    app.state.live_events = live_events or LiveEventBroker()
    app.state.event_token = os.getenv("AURA_EVENT_STREAM_TOKEN")

    @app.middleware("http")
    async def log_request(
        request: Request,
        call_next,
    ):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()
        response = await call_next(request)
        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        response.headers["X-Request-ID"] = request_id
        metrics.record(
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "request_id": request_id,
            },
        )

        return response

    @app.exception_handler(BackendUnavailableError)
    async def backend_unavailable_handler(
        request,
        exc: BackendUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
            },
        )

    @app.exception_handler(BackendInvalidResponseError)
    async def backend_invalid_response_handler(
        request,
        exc: BackendInvalidResponseError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": str(exc),
            },
        )

    @app.get("/health")
    @app.get("/live")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        readiness.check()
        return {"status": "ok"}

    @app.get("/metrics")
    def get_metrics() -> dict[str, int | float]:
        return metrics.snapshot()

    @app.websocket("/api/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        """Authenticated, read-only event projection for the production UI."""
        expected_token = app.state.event_token
        supplied_token = websocket.headers.get("X-AURA-Event-Token", "")
        if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            async for event in app.state.live_events.stream():
                await websocket.send_json(event)
        except WebSocketDisconnect:
            return

    @app.post(
        "/v1/inference",
        response_model=InferenceResponse,
    )
    def inference(request: InferenceRequest) -> InferenceResponse:
        return application.infer(request)

    @app.post("/api/tasks", response_model=TaskResponse)
    async def submit_task(request: TaskRequest) -> TaskResponse:
        if task_service is None:
            raise HTTPException(status_code=503, detail="Agent runtime is not configured")
        task = Task(request.task_id, request.principal_id, request.title, request.resource_scope)
        plan = Plan(f"plan:{request.task_id}", request.task_id, tuple(
            PlanStep(step.step_id, step.capability_id, step.operation_id, step.tool_name, step.risk_level, step.arguments, frozenset(step.depends_on), step.max_attempts)
            for step in request.steps
        ))
        try:
            result = await task_service.submit(SubmittedTask(task, plan))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return TaskResponse(task_id=task.task_id, plan_id=result.plan_id, state=result.state, steps=[{"step_id": step.step_id, "state": step.state, "attempts": step.attempts, "reason": step.reason} for step in result.steps])

    @app.get("/api/tasks/{task_id}", response_model=TaskResponse)
    def task_status(task_id: str) -> TaskResponse:
        if task_service is None:
            raise HTTPException(status_code=503, detail="Agent runtime is not configured")
        try:
            result = task_service.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return TaskResponse(task_id=task_id, plan_id=result.plan_id, state=result.state, steps=[{"step_id": step.step_id, "state": step.state, "attempts": step.attempts, "reason": step.reason} for step in result.steps])

    return app
