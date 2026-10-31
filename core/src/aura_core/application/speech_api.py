"""Local-only HTTP controls for the full-duplex speech session."""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_core.security.http_auth import authenticated_principal


router = APIRouter(prefix="/api/speech", tags=["full-duplex-speech"])


def _require_local(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Local client required")


def _manager(request: Request):
    manager = getattr(request.app.state, "speech_session_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Speech providers are not ready")
    return manager


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    confirmed: bool = False


class AudioRequest(SessionRequest):
    audio_base64: str = Field(min_length=1, max_length=28_000_000)


class SpeakRequest(SessionRequest):
    text: str = Field(min_length=1, max_length=8000)


class LatencySampleRequest(SessionRequest):
    stage: str = Field(pattern="^(llm_first_token|browser_first_audio|end_to_end)$")
    milliseconds: float = Field(ge=0, le=600_000)


@router.post("/sessions")
async def start_session(
    body: SessionRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required to activate microphone processing")
    try:
        snapshot = await _manager(request).start(body.session_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session_id": snapshot.session_id, "state": snapshot.state}


@router.post("/sessions/audio")
async def ingest_audio(
    body: AudioRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    manager = _manager(request)
    if manager.snapshot().session_id != body.session_id:
        raise HTTPException(status_code=404, detail="Speech session not found")
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
        transcript = await manager.ingest_audio(audio)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid audio payload") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session_id": body.session_id, "transcript": transcript, "state": manager.snapshot().state}


@router.post("/sessions/speak")
async def speak(
    body: SpeakRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    manager = _manager(request)
    if manager.snapshot().session_id != body.session_id:
        raise HTTPException(status_code=404, detail="Speech session not found")
    try:
        await manager.speak(body.text)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="TTS execution was not authorized") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"session_id": body.session_id, "state": manager.snapshot().state}


@router.post("/sessions/interrupt")
async def interrupt(
    body: SessionRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    manager = _manager(request)
    if manager.snapshot().session_id != body.session_id:
        raise HTTPException(status_code=404, detail="Speech session not found")
    await manager.interrupt(reason="api_interrupt", keep_listening=True)
    return {"session_id": body.session_id, "state": manager.snapshot().state}


@router.get("/health")
async def voice_health(request: Request) -> dict[str, object]:
    _require_local(request)
    config = getattr(request.app.state, "sherpa_onnx_config", None)
    sherpa = config.health() if config is not None else {"available": False, "reason": "not_composed"}
    manager = getattr(request.app.state, "speech_session_manager", None)
    return {"full_duplex_available": manager is not None, "sherpa_onnx": sherpa,
            "latency": manager.latency_snapshot() if manager is not None else {}}


@router.post("/sessions/latency")
async def record_latency(
    body: LatencySampleRequest, request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    manager = _manager(request)
    if manager.snapshot().session_id != body.session_id:
        raise HTTPException(status_code=404, detail="Speech session not found")
    manager.record_client_latency(body.stage, body.milliseconds)
    return {"accepted": True, "latency": manager.latency_snapshot()}


@router.delete("/sessions/{session_id}")
async def close_session(
    session_id: str,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    _require_local(request)
    manager = _manager(request)
    if manager.snapshot().session_id != session_id:
        raise HTTPException(status_code=404, detail="Speech session not found")
    await manager.close()
    return {"session_id": session_id, "state": "idle"}
