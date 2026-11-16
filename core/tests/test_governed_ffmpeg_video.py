"""Real Gateway/FFmpeg video extraction -> independent Ollama image authorization."""
import asyncio
import base64
import hashlib
import json
import shutil

import httpx
import pytest

from aura_core.providers.ffmpeg_video_mcp import (
    GovernedVideoUnderstanding,
    LocalFFmpegVideoMCP,
    VideoUnderstandingDenied,
    VideoUnderstandingUnavailable,
    register_local_ffmpeg_video,
)
from aura_core.providers.ollama_vision_mcp import register_local_ollama_vision
from aura_core.kernel.services import ServiceRegistry
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry

_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 96
_WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 100
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class _Process:
    returncode = 0

    def __init__(self, calls, output=_PNG):
        self._calls = calls
        self._output = output

    async def communicate(self, value):
        self._calls.append(("input", value))
        return self._output, b""

    def kill(self):
        self._calls.append(("kill", True))

    async def wait(self):
        self.returncode = -9
        return -9


def _system(monkeypatch, *, video_allow=False, image_allow=False, output=_PNG,
            kind="mp4", response="Visible: a white board."):
    calls = {"ffmpeg": [], "ollama": []}
    import aura_core.providers.ffmpeg_video_mcp as module

    async def fake_exec(*args, **kwargs):
        calls["ffmpeg"].append(("command", args, kwargs))
        return _Process(calls["ffmpeg"], output=output)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)

    original = httpx.AsyncClient
    def handler(request):
        data = json.loads(request.content)
        calls["ollama"].append(data)
        assert request.url.host == "127.0.0.1"
        assert base64.b64decode(data["messages"][0]["images"][0]) == _PNG
        assert "untrusted" in data["messages"][0]["content"]
        return httpx.Response(200, json={"message": {"content": response}})
    def make_client(*args, **kwargs):
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", make_client)

    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    backend = register_local_ffmpeg_video(
        services=services, providers=providers, capabilities=caps,
        executable="/usr/bin/ffmpeg",
    )
    register_local_ollama_vision(
        services=services, providers=providers, capabilities=caps,
    )
    engine = PermissionEngine(caps)
    for enabled, cap, scope in (
        (video_allow, "vision.video.frames", "vision/consented/video"),
        (image_allow, "vision.image.describe", "vision/consented/image"),
    ):
        if enabled:
            engine.add_policy(PermissionPolicy(
                policy_id="owner." + cap,
                policy_version="1.0.0",
                principal_id="owner", capability_id=cap, operation_id=cap,
                resource_scope=scope,
                authorization_level=AuthorizationLevel.READ,
                decision=AuthorizationDecision.ALLOW,
            ))
    gateway = MCPGateway(caps, providers, engine)
    reader = GovernedVideoUnderstanding(gateway, authenticated_principal_id="owner")
    return reader, backend, engine, calls, caps, providers


def _read(reader, *, video=_MP4, kind="mp4", consent=True):
    return asyncio.run(reader.summarize(video, kind=kind, capture_confirmed=consent))


def test_real_gateway_two_independent_policies_and_model_video_pipeline(monkeypatch):
    reader, backend, engine, calls, caps, providers = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    result = _read(reader)
    assert result.summary == "Visible: a white board."
    assert result.video_sha256 == hashlib.sha256(_MP4).hexdigest()
    assert result.montage_sha256 == hashlib.sha256(_PNG).hexdigest()
    assert result.trust == "UNTRUSTED_VIDEO_MODEL_OUTPUT"
    assert result.interactive_action_authorized is False
    assert result.provider_id == "vision.ffmpeg.local"
    assert result.video_kind == "mp4"
    assert providers.resolve("vision.ffmpeg.local") is backend
    assert caps.resolve("vision.video.frames").definition.tool_name == "video_contact_sheet"
    command = calls["ffmpeg"][0]
    assert command[1][0] == "/usr/bin/ffmpeg"
    assert command[1][command[1].index("-protocol_whitelist") + 1] == "pipe"
    assert command[1][-2:] == ("png", "pipe:1")
    assert command[2]["stderr"] == asyncio.subprocess.DEVNULL
    assert "http" not in str(command[1])
    assert calls["ffmpeg"][1] == ("input", _MP4)
    assert len(calls["ollama"]) == 1
    assert len(engine.audit_records()) == 2
    assert all(x.decision.decision is AuthorizationDecision.ALLOW for x in engine.audit_records())


@pytest.mark.parametrize("video_allow,image_allow,expected_ffmpeg,expected_ollama", [
    (False, False, 0, 0),
    (False, True, 0, 0),
    (True, False, 2, 0),
])
def test_separate_permission_missing_prevents_unapproved_model_or_decode(
    monkeypatch, video_allow, image_allow, expected_ffmpeg, expected_ollama,
):
    reader, backend, engine, calls, *_ = _system(
        monkeypatch, video_allow=video_allow, image_allow=image_allow,
    )
    with pytest.raises((VideoUnderstandingDenied, PermissionError)):
        _read(reader)
    assert len(calls["ffmpeg"]) == expected_ffmpeg
    assert len(calls["ollama"]) == expected_ollama


def test_explicit_video_consent_required_before_any_authorization(monkeypatch):
    reader, backend, engine, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    with pytest.raises(VideoUnderstandingDenied):
        _read(reader, consent=False)
    assert engine.audit_records() == ()
    assert not calls["ffmpeg"] and not calls["ollama"]


def test_provider_rejects_direct_call_without_current_dispatch(monkeypatch):
    reader, backend, engine, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    with pytest.raises(VideoUnderstandingDenied):
        asyncio.run(backend.call_tool("video_contact_sheet", {
            "video_base64": base64.b64encode(_MP4).decode(),
            "kind": "mp4",
        }))
    assert not calls["ffmpeg"] and not calls["ollama"]


@pytest.mark.parametrize("video,kind", [
    (b"", "mp4"), (b"small", "mp4"), (b"x" * 90, "mp4"),
    (_MP4, "webm"), (_WEBM, "mp4"), (_MP4, "avi"), (_MP4, ""),
    (_MP4, None), (_MP4, []), (_MP4, {"container": "mp4"}),
    (_MP4, True), (bytearray(_MP4), "mp4"),
])
def test_invalid_video_input_or_container_denied_before_gateway(
    monkeypatch, video, kind,
):
    reader, backend, engine, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    with pytest.raises(ValueError):
        _read(reader, video=video, kind=kind)
    assert engine.audit_records() == () and not calls["ffmpeg"]


def test_webm_container_passes_allowlisted_demuxer_not_dynamic_url(monkeypatch):
    reader, backend, engine, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    result = _read(reader, video=_WEBM, kind="webm")
    assert result.video_kind == "webm"
    command = calls["ffmpeg"][0][1]
    assert command[command.index("-f") + 1] == "matroska"


def test_malformed_or_oversized_montage_fails_before_model_dispatch(monkeypatch):
    for payload in (b"", b"random non PNG" * 5, b"\x89PNG\r\n\x1a\n",
                    b"\x89PNG\r\n\x1a\n" + b"\0" * (8 * 1024 * 1024 + 1)):
        reader, _, _, calls, *_ = _system(
            monkeypatch, video_allow=True, image_allow=True, output=payload,
        )
        with pytest.raises(VideoUnderstandingUnavailable):
            _read(reader)
        assert not calls["ollama"]


def test_failed_ffmpeg_exit_returns_generic_error_not_decoder_secrets(monkeypatch):
    reader, backend, _, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    import aura_core.providers.ffmpeg_video_mcp as module
    class Failed(_Process):
        returncode = 9
    async def failing_exec(*args, **kwargs):
        return Failed(calls["ffmpeg"])
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", failing_exec)
    with pytest.raises(VideoUnderstandingUnavailable) as err:
        _read(reader)
    assert "private" not in str(err.value).lower()
    assert not calls["ollama"]


def test_ffmpeg_timeout_kills_live_process(monkeypatch):
    reader, backend, _, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    import aura_core.providers.ffmpeg_video_mcp as module
    backend._timeout = 0.001
    class Slow(_Process):
        returncode = None
        async def communicate(self, data):
            await asyncio.sleep(1)
            return b"PRIVATE", b""
    async def slow_exec(*args, **kwargs):
        return Slow(calls["ffmpeg"])
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", slow_exec)
    with pytest.raises(VideoUnderstandingUnavailable):
        _read(reader)
    assert ("kill", True) in calls["ffmpeg"]
    assert not calls["ollama"]


@pytest.mark.parametrize("binary", [
    "ffmpeg", "./ffmpeg", "ffmpeg -y", "../tmp/ffmpeg", "/bad\nfile",
])
def test_only_explicit_absolute_executable_accepted(binary):
    with pytest.raises(ValueError):
        LocalFFmpegVideoMCP(executable=binary)


def test_unauthorized_cross_principal_client_cannot_switch_identity(monkeypatch):
    reader, backend, _, calls, *_ = _system(
        monkeypatch, video_allow=True, image_allow=True,
    )
    with pytest.raises(TypeError):
        asyncio.run(reader.summarize(
            _MP4, kind="mp4", capture_confirmed=True, principal_id="attacker",
        ))
    assert not calls["ffmpeg"]


def test_optional_real_ffmpeg_process_generates_contact_sheet_through_gateway():
    binary = shutil.which("ffmpeg")
    if not binary:
        pytest.skip("Local FFmpeg binary absent")
    # Generate a tiny self-contained fragment MP4 with FFmpeg's real built-in
    # color filter; no network, camera, external clip or licensed test content.
    async def generate():
        proc = await asyncio.create_subprocess_exec(
            binary, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=white:s=64x64:r=1",
            "-t", "4", "-c:v", "mpeg4",
            "-movflags", "frag_keyframe+empty_moov",
            "-f", "mp4", "pipe:1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out if proc.returncode == 0 else b""
    video = asyncio.run(generate())
    if not 64 <= len(video) <= 12 * 1024 * 1024:
        pytest.skip("Runner FFmpeg lacks built-in MP4 encoder")
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    register_local_ffmpeg_video(services=services, providers=providers,
                                capabilities=caps, executable=binary)
    engine = PermissionEngine(caps)
    engine.add_policy(PermissionPolicy(
        policy_id="owner.real-ffmpeg", policy_version="1.0.0",
        principal_id="owner", capability_id="vision.video.frames",
        operation_id="vision.video.frames", resource_scope="vision/consented/video",
        authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    gateway = MCPGateway(caps, providers, engine)
    from aura_core.mcp.gateway import MCPGatewayRequest
    from aura_core.kernel.permissions import RiskLevel
    from uuid import uuid4
    async def decode():
        return await gateway.invoke(MCPGatewayRequest(
            request_id=str(uuid4()), principal_id="owner",
            capability_id="vision.video.frames", operation_id="vision.video.frames",
            resource_scope="vision/consented/video",
            risk_level=RiskLevel.MEDIUM,
            tool_name="video_contact_sheet",
            arguments={"video_base64": base64.b64encode(video).decode(),
                       "kind": "mp4"},
        ))
    response = asyncio.run(decode())
    assert response.decision is AuthorizationDecision.ALLOW
    assert response.result["trust"] == "UNTRUSTED_DECODED_VIDEO_FRAMES"
    image = base64.b64decode(response.result["contact_sheet_base64"])
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
