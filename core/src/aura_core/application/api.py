import asyncio
import base64
import logging
import os
import tempfile
import threading
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.agent.runtime import Plan, PlanStep, Task
from aura_core.application.bootstrap import create_application
from aura_core.application.live_events import LiveEventBroker
from aura_core.application.readiness import ReadinessService
from aura_core.application.service import InferenceService
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.application.directive_planner import DirectivePlanner
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.contracts.messages import InferenceRequest, InferenceResponse
from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.observability.metrics import RequestMetrics
from aura_core.runtime.errors import (
    BackendInvalidResponseError,
    BackendUnavailableError,
)
from aura_core.runtime.transport import HttpJsonTransport, JsonTransport


from aura_core.memory.chat_memory import ChatMemory
from aura_core.memory.embeddings import OllamaEmbeddingProvider
from aura_core.memory.semantic_store import SemanticMemoryStore
from aura_core.observability.pipeline_trace import PipelineTrace


logger = logging.getLogger("aura_core.http")

_whisper_model = None
_whisper_model_lock = threading.Lock()


def transcribe_audio_bytes(audio_bytes: bytes, language: str, suffix: str = ".webm") -> tuple[str, str]:
    """Run local faster-whisper transcription; load the model lazily once."""
    global _whisper_model
    from pathlib import Path

    if not audio_bytes:
        raise ValueError("Audio payload is empty")

    if _whisper_model is None:
        with _whisper_model_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                _whisper_model = WhisperModel(
                    os.getenv("AURA_STT_MODEL", "small"),
                    device=os.getenv("AURA_STT_DEVICE", "cpu"),
                    compute_type=os.getenv("AURA_STT_COMPUTE_TYPE", "int8"),
                )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as audio_file:
            audio_file.write(audio_bytes)
            temp_path = audio_file.name
        segments, info = _whisper_model.transcribe(
            temp_path,
            language=language,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, getattr(info, "language", None) or language
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to remove temporary STT audio file", exc_info=True)


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


class DirectivePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directive: str = Field(min_length=1, max_length=4000)


class DirectivePlanResponse(BaseModel):
    resource_scope: str
    steps: list[TaskStepPayload]


class AssistantRespondRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1,
        max_length=4000,
    )

    research_output: object | None = None


class AssistantRespondResponse(BaseModel):
    assistant_reply: str
    model: str
    degraded: bool = False

class SpeechTranscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_base64: str = Field(min_length=1, max_length=16_000_000)
    mime_type: str = Field(default="audio/webm", min_length=1, max_length=100)
    language: str = Field(default="tr", min_length=2, max_length=10)


class SpeechTranscriptionResponse(BaseModel):
    text: str
    language: str


class SpeechSynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    voice: str = Field(default="af_heart", min_length=1)

class SpeechSynthesisResponse(BaseModel):
    mime_type: str
    audio_base64: str

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

    # ========================================================
    # CORS
    # ========================================================
    #
    # Frontend:
    #   http://127.0.0.1:4173
    #   http://localhost:4173
    #
    # Dev:
    #   http://127.0.0.1:5173
    #   http://localhost:5173
    #
    # allow_credentials=False permits wildcard methods/headers.
    # ========================================================

    cors_origins = [
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
        ],
        max_age=600,
    )

    metrics = RequestMetrics()

    app.state.readiness = readiness
    app.state.metrics = metrics
    app.state.task_service = task_service
    app.state.live_events = live_events or LiveEventBroker()
    app.state.directive_planner = DirectivePlanner()
    app.state.chat_memory = ChatMemory(
        SemanticMemoryStore(
            embeddings=OllamaEmbeddingProvider(
                model=os.getenv("AURA_EMBEDDING_MODEL", "bge-m3"),
                base_url=os.getenv(
                    "OLLAMA_BASE_URL",
                    "http://127.0.0.1:11434",
                ),
            ),
            qdrant_url=os.getenv(
                "AURA_QDRANT_URL",
                "http://127.0.0.1:6333",
            ),
            collection=os.getenv(
                "AURA_MEMORY_COLLECTION",
                "aura_memory",
            ),
        )
    )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or str(uuid4())
        )

        request.state.request_id = request_id
        trace = PipelineTrace(request_id)
        trace.start_stage("http_request")
        started_at = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            trace.finish_stage("http_request", outcome="failure")
            logger.exception(
                "HTTP request failed",
                extra={
                    "event": "http_request_failed",
                    "request_id": request_id,
                    "pipeline_trace": trace.snapshot(),
                },
            )
            raise

        trace.finish_stage("http_request", outcome="success")

        latency_ms = round(
            (perf_counter() - started_at) * 1000,
            3,
        )

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
                "pipeline_trace": trace.snapshot(),
            },
        )

        return response
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.exception(
            "Unhandled API exception",
            extra={
                "event": "http_unhandled_exception",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(BackendUnavailableError)
    async def backend_unavailable_handler(
        request,
        exc: BackendUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc)},
        )

    @app.exception_handler(BackendInvalidResponseError)
    async def backend_invalid_response_handler(
        request,
        exc: BackendInvalidResponseError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc)},
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

    @app.post(
        "/api/assistant/respond",
        response_model=AssistantRespondResponse,
    )
    def assistant_respond(
        request: AssistantRespondRequest,
        http_request: Request,
    ) -> AssistantRespondResponse:

        import json

        research_context = ""

        if request.research_output is not None:
            try:
                research_context = json.dumps(
                    request.research_output,
                    ensure_ascii=False,
                    default=str,
                )
            except Exception:
                research_context = str(
                    request.research_output
                )

            research_context = (
                research_context[:12000]
            )

        request_id = getattr(
            http_request.state,
            "request_id",
            "local-request",
        )

        memory_context = ""
        memory_enabled = (
            os.getenv("AURA_CHAT_MEMORY_ENABLED", "0").strip() == "1"
        )

        if memory_enabled:
            try:
                memories = asyncio.run(
                    app.state.chat_memory.recall(
                        scope="local_default",
                        query=request.message,
                    )
                )
                memory_context = "\n".join(
                    item.content for item in memories
                )[:6000]
            except Exception:
                logger.warning(
                    "Chat memory recall unavailable",
                    extra={"request_id": request_id},
                    exc_info=True,
                )
        system_prompt = (
            "Sen AURA'nın JARVIS konuşma katmanısın. "
            "Kullanıcıya doğal Türkçe yanıt ver. "
            "Ham araştırma çıktısını, JSON'u, tool metadata'sını, "
            "execution detaylarını veya iç sistem ayrıntılarını aynen aktarma. "
            "Araştırma verisini yalnızca bağlam olarak kullan. "
            "Yanıt konuşmaya uygun ve kısa olsun."
        )

        user_content = request.message

        if research_context:
            user_content = (
                "KullanÄ±cÄ± direktifi:\n"
                + request.message
                + "\n\n"
                + "AURA araştırma bağlamı:\n"
                + research_context
            )

        if memory_context:
            user_content = (
                user_content
                + "\n\nAURA önceki sohbet belleği:\n"
                + memory_context
            )
        inference_request = InferenceRequest(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        inference_trace = PipelineTrace(request_id)
        inference_trace.start_stage("inference")

        try:
            result = application.infer(
                inference_request
            )
        except Exception:
            inference_trace.finish_stage(
                "inference",
                outcome="failure",
            )
            logger.exception(
                "Inference stage failed",
                extra={
                    "request_id": request_id,
                    "pipeline_trace": inference_trace.snapshot(),
                },
            )
            raise

        inference_trace.finish_stage("inference", outcome="success")
        assistant_reply = result.content.strip()

        logger.info(
            "Inference stage completed",
            extra={
                "request_id": request_id,
                "pipeline_trace": inference_trace.snapshot(),
            },
        )

        if memory_enabled:
            try:
                asyncio.run(
                    app.state.chat_memory.remember(
                        scope="local_default",
                        content=(
                            "User: "
                            + request.message
                            + "\nAssistant: "
                            + assistant_reply
                        ),
                        source="assistant_chat",
                        metadata={"request_id": request_id},
                    )
                )
            except Exception:
                logger.warning(
                    "Chat memory write unavailable",
                    extra={"request_id": request_id},
                    exc_info=True,
                )

        return AssistantRespondResponse(
            assistant_reply=assistant_reply,
            model=result.model,
            degraded=False,
        )


    @app.post("/api/speech/transcribe", response_model=SpeechTranscriptionResponse)
    async def transcribe_speech(request: SpeechTranscriptionRequest) -> SpeechTranscriptionResponse:
        try:
            audio_bytes = base64.b64decode(request.audio_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(status_code=422, detail="Invalid base64 audio payload") from exc

        if not audio_bytes:
            raise HTTPException(status_code=422, detail="Audio payload is empty")
        if len(audio_bytes) > 12 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio payload exceeds 12 MiB limit")

        mime_type = request.mime_type.split(";", 1)[0].strip().lower()
        suffix_by_mime = {
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
        }
        suffix = suffix_by_mime.get(mime_type)
        if suffix is None:
            raise HTTPException(status_code=415, detail="Unsupported audio format")

        try:
            text, detected_language = await asyncio.to_thread(
                transcribe_audio_bytes, audio_bytes, request.language, suffix
            )
        except ImportError as exc:
            logger.exception("Local speech-to-text dependency is unavailable")
            raise HTTPException(status_code=503, detail="Local speech-to-text is unavailable") from exc
        except Exception as exc:
            logger.exception("Local speech-to-text failed")
            raise HTTPException(status_code=500, detail="Local speech-to-text failed; see server log for details") from exc

        return SpeechTranscriptionResponse(text=text, language=detected_language)

    @app.post("/api/speech/synthesize", response_model=SpeechSynthesisResponse)
    async def synthesize_speech(request: SpeechSynthesisRequest) -> SpeechSynthesisResponse:
        gateway = getattr(app.state, "mcp_gateway", None)
        if gateway is None:
            raise HTTPException(status_code=503, detail="Local speech provider is unavailable")
        response = await gateway.invoke(MCPGatewayRequest(
            request_id=f"speech:{uuid4()}", principal_id="local_owner",
            capability_id="speech.synthesize", operation_id="speech.synthesize",
            resource_scope="local_default", risk_level=RiskLevel.LOW,
            tool_name="synthesize", arguments={"text": request.text, "voice": request.voice},
        ))
        if response.result is None:
            raise HTTPException(status_code=403, detail=response.reason)
        result = response.result
        return SpeechSynthesisResponse(mime_type=result["mime_type"], audio_base64=result["audio_base64"])

    @app.post(
        "/v1/inference",
        response_model=InferenceResponse,
    )
    def inference(
        request: InferenceRequest,
    ) -> InferenceResponse:
        return application.infer(request)

    @app.post(
        "/api/tasks/plan",
        response_model=DirectivePlanResponse,
    )
    def generate_task_plan(
        request: DirectivePlanRequest,
    ) -> DirectivePlanResponse:

        try:
            generated = app.state.directive_planner.plan(
                request.directive
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return DirectivePlanResponse(
            resource_scope=generated.resource_scope,
            steps=[
                TaskStepPayload(
                    step_id=step.step_id,
                    capability_id=step.capability_id,
                    operation_id=step.operation_id,
                    tool_name=step.tool_name,
                    risk_level=step.risk_level,
                    arguments=step.arguments,
                    depends_on=step.depends_on,
                    max_attempts=step.max_attempts,
                )
                for step in generated.steps
            ],
        )

    @app.post(
        "/api/tasks",
        response_model=TaskResponse,
    )
    async def submit_task(
        request: TaskRequest,
        http_request: Request,
    ) -> TaskResponse:

        if task_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent runtime is not configured",
            )

        task = Task(
            request.task_id,
            "local_owner",
            request.title,
            "local_default",
        )

        plan = Plan(
            f"plan:{request.task_id}",
            request.task_id,
            tuple(
                PlanStep(
                    step.step_id,
                    step.capability_id,
                    step.operation_id,
                    step.tool_name,
                    step.risk_level,
                    step.arguments,
                    frozenset(step.depends_on),
                    step.max_attempts,
                )
                for step in request.steps
            ),
        )

        try:
            result = await task_service.submit(
                SubmittedTask(
                    task,
                    plan,
                    getattr(http_request.state, "request_id", None),
                )
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        return TaskResponse(
            task_id=task.task_id,
            plan_id=result.plan_id,
            state=result.state,
            steps=[
                {
                    "step_id": step.step_id,
                    "state": step.state,
                    "attempts": step.attempts,
                    "reason": step.reason,
                    "result": step.result,
                }
                for step in result.steps
            ],
        )

    @app.get(
        "/api/tasks/{task_id}",
        response_model=TaskResponse,
    )
    def task_status(task_id: str) -> TaskResponse:

        if task_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent runtime is not configured",
            )

        try:
            result = task_service.get_for_owner(task_id, "local_owner")
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        return TaskResponse(
            task_id=task_id,
            plan_id=result.plan_id,
            state=result.state,
            steps=[
                {
                    "step_id": step.step_id,
                    "state": step.state,
                    "attempts": step.attempts,
                    "reason": step.reason,
                }
                for step in result.steps
            ],
        )

    return app
