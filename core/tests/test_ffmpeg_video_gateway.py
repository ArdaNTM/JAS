"""Real AURA Gateway -> FFmpeg subprocess -> Gateway -> Ollama HTTP tests."""
import asyncio
import base64
import json
import shutil
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from aura_core.providers.ffmpeg_video_mcp import (
    GovernedLocalVideoAnalyzer, LocalFFmpegVideoMCP, VideoReadDenied,
    VideoReadUnavailable, register_local_ffmpeg_video,
)
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, register_local_ollama_vision,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry


_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 40
_JPEG = b"\xff\xd8\xff" + b"j" * 32 + b"\xff\xd9"


class _FakeProcess:
    returncode = 0

    def __init__(self, output, trace):
        self._output = output
        self._trace = trace

    async def communicate(self, data):
        self._trace.append(("video_input", data))
        return self._output, b""

    def kill(self):
        self._trace.append(("killed", True))

    async def wait(self):
        self.returncode = -9
        return -9


def _system(monkeypatch, *, allow_video=True, allow_image=True, frames=None,
            model_response="A lamp appears.", process_exit=0):
    trace = []
    model_calls = []
    import aura_core.providers.ffmpeg_video_mcp as module

    class FakeProcess(_FakeProcess):
        returncode = process_exit

    async def process(*args, **kwargs):
        trace.append(("ffmpeg", args, kwargs))
        return FakeProcess(_JPEG * 2 if frames is None else frames, trace)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", process)
    original = httpx.AsyncClient

    def handle(request):
        data = json.loads(request.content)
        model_calls.append(data)
        assert request.url.host == "127.0.0.1"
        assert request.url.path == "/api/chat"
        assert base64.b64decode(data["messages"][0]["images"][0]) == _JPEG
        return httpx.Response(200, json={"message": {"content": model_response}})

    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handle), **kw)

    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", client)
    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    video = register_local_ffmpeg_video(services=services, capabilities=caps, providers=providers)
    vision = register_local_ollama_vision(services=services, capabilities=caps, providers=providers)
    engine = PermissionEngine(caps)
    for enabled, cap, scope in (
        (allow_video, "vision.video.frames.read", "vision/consented/video"),
        (allow_image, "vision.image.describe", "vision/consented/image"),
    ):
        if enabled:
            engine.add_policy(PermissionPolicy(
                policy_id="owner." + cap, policy_version="1.0.0",
                principal_id="owner", capability_id=cap,
                operation_id=cap, resource_scope=scope,
                authorization_level=AuthorizationLevel.READ,
                decision=AuthorizationDecision.ALLOW,
            ))
    gateway = MCPGateway(caps, providers, engine)
    image_reader = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    analyzer = GovernedLocalVideoAnalyzer(
        gateway, authenticated_principal_id="owner", image_reader=image_reader,
    )
    return analyzer, video, vision, engine, trace, model_calls, gateway


def _run(analyzer, *, video=_MP4, consent=True, interval=5):
    return asyncio.run(analyzer.analyze(
        video, capture_confirmed=consent,
        question="Describe visible motion.", interval_seconds=interval,
    ))


def test_full_authorized_ffmpeg_and_ollama_dispatches_with_distinct_permissions(monkeypatch):
    analyzer, video, vision, engine, trace, model_calls, gateway = _system(monkeypatch)
    evidence = _run(analyzer)
    assert [x.description for x in evidence.frames] == ["A lamp appears."] * 2
    assert [x.index for x in evidence.frames] == [0, 1]
    assert evidence.trust == "UNTRUSTED_VIDEO_ANALYSIS"
    assert evidence.action_executed is False
    assert len(evidence.video_sha256) == 64
    assert len(model_calls) == 2
    assert len(trace) == 2
    cmd = trace[0][1]
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-protocol_whitelist" in cmd and "pipe" in cmd
    assert "pipe:0" in cmd and "pipe:1" in cmd
    assert cmd[cmd.index("-vf") + 1] == "fps=1/5,scale=480:-2"
    assert trace[1] == ("video_input", _MP4)
    assert [a.request.capability_id for a in engine.audit_records()] == [
        "vision.video.frames.read", "vision.image.describe", "vision.image.describe",
    ]
    assert all(a.decision.decision is AuthorizationDecision.ALLOW for a in engine.audit_records())


def test_missing_video_policy_prevents_ffmpeg_and_model(monkeypatch):
    analyzer, video, vision, engine, trace, model_calls, gateway = _system(
        monkeypatch, allow_video=False,
    )
    with pytest.raises(VideoReadDenied):
        _run(analyzer)
    assert trace == [] and model_calls == []
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.DENY


def test_missing_image_policy_fails_video_after_bounded_decode_no_model_call(monkeypatch):
    analyzer, video, vision, engine, trace, model_calls, gateway = _system(
        monkeypatch, allow_image=False,
    )
    with pytest.raises(VideoReadUnavailable):
        _run(analyzer)
    assert len(trace) == 2
    assert model_calls == []
    assert [a.decision.decision for a in engine.audit_records()] == [
        AuthorizationDecision.ALLOW, AuthorizationDecision.DENY,
    ]


def test_user_consent_is_required_before_any_gateway_call(monkeypatch):
    analyzer, video, vision, engine, trace, model_calls, gateway = _system(monkeypatch)
    with pytest.raises(VideoReadDenied):
        _run(analyzer, consent=False)
    assert trace == [] and model_calls == [] and engine.audit_records() == ()


def test_direct_provider_call_never_invokes_ffmpeg(monkeypatch):
    analyzer, video, vision, engine, trace, model_calls, gateway = _system(monkeypatch)
    with pytest.raises(VideoReadDenied):
        asyncio.run(video.call_tool("sample_video_frames", {
            "video_base64": base64.b64encode(_MP4).decode(),
            "interval_seconds": 5,
        }))
    assert trace == [] and model_calls == []


def test_cross_principal_or_cross_gateway_reader_rejected():
    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    gateway = MCPGateway(caps, providers, PermissionEngine(caps))
    other = MCPGateway(caps, providers, PermissionEngine(caps))
    image_reader = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    with pytest.raises(VideoReadDenied):
        GovernedLocalVideoAnalyzer(other, authenticated_principal_id="owner", image_reader=image_reader)
    with pytest.raises(VideoReadDenied):
        GovernedLocalVideoAnalyzer(gateway, authenticated_principal_id="other", image_reader=image_reader)


@pytest.mark.parametrize("bad", [
    b"", b"short", b"x" * 42, b"\x00\x00\x00\x18nope" + b"\x00" * 40,
    bytearray(_MP4), b"\x00" * (12 * 1024 * 1024 + 1),
])
def test_invalid_container_never_launches_process(monkeypatch, bad):
    analyzer, _, _, engine, trace, model_calls, _ = _system(monkeypatch)
    with pytest.raises(ValueError):
        _run(analyzer, video=bad)
    assert trace == [] and model_calls == []


@pytest.mark.parametrize("interval", [0, 1, 3, 11, True, 2.5, "5"])
def test_unsupported_sampling_parameter_rejected_before_gateway(monkeypatch, interval):
    analyzer, _, _, engine, trace, model_calls, _ = _system(monkeypatch)
    with pytest.raises(ValueError):
        _run(analyzer, interval=interval)
    assert trace == [] and engine.audit_records() == ()


@pytest.mark.parametrize("raw", [
    b"malformed", b"\xff\xd8\xff" + b"x" * 30,
    _JPEG * 5, b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024) + b"\xff\xd9",
])
def test_ffmpeg_malformed_or_bounded_output_fails_closed(monkeypatch, raw):
    analyzer, _, _, engine, trace, model_calls, _ = _system(monkeypatch, frames=raw)
    with pytest.raises(VideoReadUnavailable):
        _run(analyzer)
    assert len(trace) == 2
    assert model_calls == []


def test_ffmpeg_timeout_kills_running_process_with_sanitized_public_failure(monkeypatch):
    analyzer, decoder, _, _, trace, model_calls, _ = _system(monkeypatch)
    import aura_core.providers.ffmpeg_video_mcp as module
    decoder._timeout = 0.001

    class Slow(_FakeProcess):
        returncode = None

        async def communicate(self, data):
            await asyncio.sleep(1)
            return b"secret-password", b""

    async def slow(*args, **kwargs):
        return Slow(b"", trace)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", slow)
    with pytest.raises(VideoReadUnavailable, match="decoder unavailable") as err:
        _run(analyzer)
    assert "secret-password" not in str(err.value)
    assert ("killed", True) in trace
    assert model_calls == []


def test_real_ffmpeg_file_to_frames_optional_installed_binary():
    """Optional genuine FFmpeg smoke, never count absent system dependency as passed."""
    binary = shutil.which("ffmpeg")
    if not binary:
        pytest.skip("ffmpeg binary not installed")
    # Generate a tiny fragmented MP4 entirely in memory (no file/network).
    cmd = [
        binary, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=1:d=3",
        "-c:v", "mpeg4", "-movflags", "frag_keyframe+empty_moov",
        "-f", "mp4", "pipe:1",
    ]
    try:
        generated = subprocess.run(cmd, capture_output=True, timeout=15, check=True).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Installed FFmpeg lacks required small MP4 codecs")
    if len(generated) < 32 or generated[4:8] != b"ftyp":
        pytest.skip("FFmpeg MP4 output container unavailable")
    from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch

    provider = LocalFFmpegVideoMCP(executable=binary)
    grant = DispatchGrant(
        principal_id="owner", capability_id="vision.video.frames.read",
        tool_name="sample_video_frames", approval_consumed=False, risk_level="medium",
    )
    token = enter_dispatch(grant)
    try:
        decoded = asyncio.run(provider.call_tool("sample_video_frames", {
            "video_base64": base64.b64encode(generated).decode(),
            "interval_seconds": 2,
        }))
    finally:
        leave_dispatch(token)
    assert decoded["trust"] == "UNTRUSTED_FFMPEG_FRAMES"
    assert len(decoded["frames"]) >= 1
