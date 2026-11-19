"""Consent-bound real FFmpeg video frames + governed local Ollama descriptions.

Every FFmpeg invocation is a registered MCP tool dispatched through the Core
PermissionEngine and MCP Gateway. Each extracted frame additionally requires
its own image-description Gateway permission (#77). No screen capture,
network sources, user-provided process switches, persistent media or actions.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, _validate_identity, _validate_image,
)

_CAP = "vision.video.frames.read"
_SCOPE = "vision/consented/video"
_PROVIDER = "video.ffmpeg.local"
_TOOL = "sample_video_frames"
_MAX_VIDEO = 12 * 1024 * 1024
_MAX_B64 = ((_MAX_VIDEO + 2) // 3) * 4
_MAX_STDOUT = 8 * 1024 * 1024
_MAX_FRAME = 2 * 1024 * 1024
_MAX_FRAMES = 4
_INTERVALS = frozenset({2, 5, 10})


class VideoReadDenied(PermissionError):
    """Video and image processing must each have their own permission grant."""


class VideoReadUnavailable(RuntimeError):
    """Untrusted media could not be decoded under bounded local constraints."""


@dataclass(frozen=True, slots=True)
class VideoFrameSummary:
    index: int
    description: str
    image_sha256: str
    trust: str = "UNTRUSTED_VIDEO_FRAME_SUMMARY"


@dataclass(frozen=True, slots=True)
class VideoAnalysisEvidence:
    video_sha256: str
    frames: tuple[VideoFrameSummary, ...]
    model_provider_id: str
    trust: str = "UNTRUSTED_VIDEO_ANALYSIS"
    action_executed: bool = False


def _video_bytes(data: bytes) -> bytes:
    if type(data) is not bytes or not 32 <= len(data) <= _MAX_VIDEO:
        raise ValueError("Expected bounded local MP4/WebM video bytes")
    if not (data[4:8] == b"ftyp" or data.startswith(b"\x1a\x45\xdf\xa3")):
        raise ValueError("Only MP4/WebM container signatures are accepted")
    return data


def _frames(output: bytes) -> tuple[bytes, ...]:
    if not isinstance(output, bytes) or not 1 <= len(output) <= _MAX_STDOUT:
        raise VideoReadUnavailable("Video decoder exceeded bounded output")
    pos = 0
    frames: list[bytes] = []
    while pos < len(output):
        if output[pos:pos + 3] != b"\xff\xd8\xff":
            raise VideoReadUnavailable("Invalid MJPEG frame boundary")
        end = output.find(b"\xff\xd9", pos + 3)
        if end < 0:
            raise VideoReadUnavailable("Truncated JPEG frame")
        frame = output[pos:end + 2]
        if not 16 <= len(frame) <= _MAX_FRAME:
            raise VideoReadUnavailable("Oversized or empty decoded frame")
        _validate_image(frame)
        frames.append(frame)
        if len(frames) > _MAX_FRAMES:
            raise VideoReadUnavailable("Excessive decoded frames")
        pos = end + 2
    if not frames:
        raise VideoReadUnavailable("Video had no decodable frames")
    return tuple(frames)


class LocalFFmpegVideoMCP:
    """Fixed local decoder subprocess, impossible to invoke outside Gateway."""

    def __init__(
        self, *, executable: str = "/usr/bin/ffmpeg",
        timeout_seconds: float = 20.0,
    ) -> None:
        if (
            not isinstance(executable, str)
            or not 1 <= len(executable) <= 260
            or any(ord(c) < 32 or ord(c) == 127 for c in executable)
        ):
            raise ValueError("Invalid trusted FFmpeg executable")
        path = Path(executable)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("FFmpeg binary requires an explicit nonsymlink absolute path")
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 1 <= timeout_seconds <= 60):
            raise ValueError("Invalid bounded decoder timeout")
        self._executable = str(path)
        self._timeout = float(timeout_seconds)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Sample a few consented local video frames via FFmpeg",
            input_schema={
                "type": "object",
                "properties": {
                    "video_base64": {"type": "string", "minLength": 44, "maxLength": _MAX_B64},
                    "interval_seconds": {"type": "integer", "enum": [2, 5, 10]},
                },
                "required": ["video_base64", "interval_seconds"],
                "additionalProperties": False,
            },
        ),)

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None,
    ) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP
                or grant.tool_name != _TOOL or grant.risk_level != "medium"
                or name != _TOOL):
            raise VideoReadDenied("Video decode requires current AURA Gateway grant")
        if not isinstance(arguments, dict) or set(arguments) != {"video_base64", "interval_seconds"}:
            raise ValueError("Video decoder schema mismatch")
        interval = arguments["interval_seconds"]
        if type(interval) is not int or interval not in _INTERVALS:
            raise ValueError("Unsupported sampling interval")
        encoded = arguments["video_base64"]
        if not isinstance(encoded, str) or not 44 <= len(encoded) <= _MAX_B64:
            raise ValueError("Invalid bounded video payload")
        try:
            video = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid base64 video") from exc
        _video_bytes(video)
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "-hide_banner", "-loglevel", "error", "-nostdin",
                "-threads", "1", "-protocol_whitelist", "pipe",
                "-probesize", "1048576", "-analyzeduration", "1000000",
                "-i", "pipe:0",
                "-an", "-sn", "-dn", "-vf", f"fps=1/{interval},scale=480:-2",
                "-frames:v", str(_MAX_FRAMES),
                "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "8",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
        except OSError as exc:
            raise VideoReadUnavailable("Local FFmpeg decoder cannot start") from exc
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(video), timeout=self._timeout)
        except (TimeoutError, asyncio.CancelledError) as exc:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise VideoReadUnavailable("Local FFmpeg decoding timed out") from exc
        if process.returncode != 0:
            raise VideoReadUnavailable("Local FFmpeg decoding failed")
        images = _frames(stdout)
        return {
            "video_sha256": hashlib.sha256(video).hexdigest(),
            "frames": [base64.b64encode(f).decode("ascii") for f in images],
            "trust": "UNTRUSTED_FFMPEG_FRAMES",
        }


def register_local_ffmpeg_video(
    *, services: ServiceRegistry, providers: ProviderRegistry,
    capabilities: CapabilityRegistry, executable: str = "/usr/bin/ffmpeg",
) -> LocalFFmpegVideoMCP:
    """No implicit owner credentials, policies, or tool execution."""
    if not (isinstance(services, ServiceRegistry)
            and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry)):
        raise TypeError("Existing authoritative Core registries required")
    if any(p.definition.provider_id == _PROVIDER for p in providers.records()):
        raise ValueError("FFmpeg provider already registered")
    if capabilities.providers(_CAP):
        raise ValueError("Video capability already registered")
    instance = LocalFFmpegVideoMCP(executable=executable)
    service = services.register(ServiceDefinition(
        name="aura-local-ffmpeg-video", version="1.0.0", provider="mcp",
        category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Local FFmpeg video",
        version="1.0.0", service_id=service.service_id,
    ), instance)
    capabilities.register(CapabilityDefinition(
        capability_id=_CAP, name="Read local video frames",
        version="1.0.0", description="Consent-bound local FFmpeg frame samples",
        provider_id=_PROVIDER, provider_type=ProviderType.MCP,
        category=CapabilityCategory.VISION, risk_level="medium", tool_name=_TOOL,
    ))
    return instance


class GovernedLocalVideoAnalyzer:
    """Invoke two separately authorized Gateway tools, returning text only."""

    def __init__(
        self, gateway: MCPGateway, *,
        authenticated_principal_id: str,
        image_reader: GovernedImageUnderstanding,
    ) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCP Gateway is required")
        principal = _validate_identity(authenticated_principal_id)
        if not isinstance(image_reader, GovernedImageUnderstanding):
            raise TypeError("Registered governed image reader is required")
        if image_reader._gateway is not gateway or image_reader._principal != principal:
            raise VideoReadDenied("Video and image reads must share authenticated identity and Gateway")
        self._gateway = gateway
        self._principal = principal
        self._images = image_reader

    async def analyze(
        self, video: bytes, *, capture_confirmed: bool,
        question: str = "Describe visible events in this frame.",
        interval_seconds: int = 5,
    ) -> VideoAnalysisEvidence:
        if capture_confirmed is not True:
            raise VideoReadDenied("Explicit video consent is mandatory")
        _video_bytes(video)
        if type(interval_seconds) is not int or interval_seconds not in _INTERVALS:
            raise ValueError("Unsupported video sampling interval")
        if (not isinstance(question, str) or not 1 <= len(question.strip()) <= 500
                or any(ord(c) < 32 or ord(c) == 127 for c in question)):
            raise ValueError("Invalid bounded video question")
        try:
            reply = await self._gateway.invoke(MCPGatewayRequest(
                request_id="video-frame:" + str(uuid4()),
                principal_id=self._principal, capability_id=_CAP,
                operation_id=_CAP, resource_scope=_SCOPE,
                risk_level=RiskLevel.MEDIUM, tool_name=_TOOL,
                arguments={
                    "video_base64": base64.b64encode(video).decode("ascii"),
                    "interval_seconds": interval_seconds,
                },
            ))
        except Exception as exc:
            raise VideoReadUnavailable("Governed local video decoder unavailable") from exc
        if reply.decision is not AuthorizationDecision.ALLOW:
            raise VideoReadDenied("Explicit video read PermissionEngine ALLOW required")
        result = reply.result
        if (not isinstance(result, dict) or result.get("trust") != "UNTRUSTED_FFMPEG_FRAMES"
                or reply.provider_id != _PROVIDER
                or result.get("video_sha256") != hashlib.sha256(video).hexdigest()):
            raise VideoReadUnavailable("Video evidence failed provider identity verification")
        raw_frames = result.get("frames")
        if not isinstance(raw_frames, list) or not 1 <= len(raw_frames) <= _MAX_FRAMES:
            raise VideoReadUnavailable("Video frame sample count invalid")
        frames = []
        for i, encoded in enumerate(raw_frames):
            if not isinstance(encoded, str) or len(encoded) > ((_MAX_FRAME + 2) // 3) * 4:
                raise VideoReadUnavailable("Video frame sample is not bounded")
            try:
                image = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise VideoReadUnavailable("Video frame sample encoding invalid") from exc
            try:
                _validate_image(image)
                evidence = await self._images.describe(
                    image, prompt=question, capture_confirmed=True,
                )
            except Exception as exc:
                raise VideoReadUnavailable("Frame-specific Gateway authorization or model failed") from exc
            frames.append(VideoFrameSummary(
                index=i, description=evidence.description,
                image_sha256=evidence.image_sha256,
            ))
        return VideoAnalysisEvidence(
            video_sha256=hashlib.sha256(video).hexdigest(),
            frames=tuple(frames), model_provider_id="vision.ollama.local",
        )
