"""Cross-PR #137/#140/#141/#142/#143 real Core/Gateway visual pipeline.

Fake transports stand in *only* for physical camera, FFmpeg and running model;
all JAS Service/Capability/Provider registrations, PermissionEngine, Gateway,
SQLite persistence, CRC-correct PNG decoding and EventBus are production code.
No tool permission is inferred from one successful read.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
import sys
import zlib
from types import SimpleNamespace

import httpx

from aura_core.kernel.services import ServiceRegistry
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.events import EventBus
from aura_core.mcp.provider import ProviderRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, register_local_ollama_vision,
)
from aura_core.providers.ffmpeg_video_mcp import (
    GovernedLocalVideoAnalyzer, register_local_ffmpeg_video,
)
from aura_core.providers.opencv_camera_mcp import (
    GovernedLocalCameraReader, OwnerCameraConsentLease, register_local_opencv_camera,
)
from aura_core.memory.visual_sqlite import (
    GovernedVisualMemory, SQLiteVisualMemoryStore, register_visual_memory_capabilities,
)
from aura_core.application.visual_task_verification import (
    GovernedVisualTaskVerifier, LocalPixelChangeComparator, register_visual_task_verifier,
)

_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 40
_JPEG = b"\xff\xd8\xff" + b"x" * 32 + b"\xff\xd9"


def _png(red: int) -> bytes:
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload)))
    width, height = 20, 15
    raw = (b"\x00" + bytes((red, 0, 0)) * width) * height
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_all_camera_video_image_memory_and_visual_verification_share_real_kernel(monkeypatch, tmp_path):
    calls = []
    original = httpx.AsyncClient
    def model_handle(request):
        payload = json.loads(request.content)
        calls.append(("model", payload["model"]))
        assert request.url.path == "/api/chat" and request.url.host == "127.0.0.1"
        return httpx.Response(200, json={"message": {"content": "A desk lamp is visible."}})
    def fake_client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(model_handle), **kw)
    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", fake_client)

    class Camera:
        def isOpened(self): return True
        def set(self, *_): return True
        def read(self):
            calls.append(("opencv", "read"))
            return True, SimpleNamespace(shape=(480, 640, 3))
        def release(self): calls.append(("opencv", "release"))
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        CAP_DSHOW=1, CAP_ANY=0, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, IMWRITE_JPEG_QUALITY=20,
        VideoCapture=lambda index, backend: Camera(),
        imencode=lambda *args: (True, SimpleNamespace(tobytes=lambda: _JPEG)),
    ))
    import aura_core.providers.ffmpeg_video_mcp as video_module
    class FFmpeg:
        returncode = 0
        async def communicate(self, content):
            calls.append(("ffmpeg", hashlib.sha256(content).hexdigest()))
            return _JPEG, b""
    async def fake_ffmpeg(*args, **kwargs):
        assert args[0] == "/usr/bin/ffmpeg"
        assert "-protocol_whitelist" in args
        return FFmpeg()
    monkeypatch.setattr(video_module.asyncio, "create_subprocess_exec", fake_ffmpeg)

    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    bus = EventBus()
    lease = OwnerCameraConsentLease(authenticated_principal_id="owner")
    lease.arm(session_id="owner-session", owner_confirmed=True)
    store = SQLiteVisualMemoryStore(tmp_path / "private-vision.sqlite3")
    pixel = LocalPixelChangeComparator()
    register_local_ollama_vision(services=services, providers=providers, capabilities=caps)
    register_local_ffmpeg_video(services=services, providers=providers, capabilities=caps)
    register_local_opencv_camera(services=services, providers=providers,
                                 capabilities=caps, consent_lease=lease)
    register_visual_memory_capabilities(store=store, services=services, capabilities=caps)
    register_visual_task_verifier(comparator=pixel, services=services, capabilities=caps)
    engine = PermissionEngine(caps)
    policies = (
        ("vision.image.describe", "vision/consented/image"),
        ("vision.video.frames.read", "vision/consented/video"),
        ("vision.camera.frame.read", "vision/camera/0/frame"),
        ("memory.visual.write", "memory/visual/owner"),
        ("memory.visual.read", "memory/visual/owner"),
        ("memory.visual.delete", "memory/visual/owner"),
        ("vision.task.verify", "vision/task/compare-only"),
    )
    for cap, scope in policies:
        engine.add_policy(PermissionPolicy(
            policy_id="owner." + cap, policy_version="1.0.0", principal_id="owner",
            capability_id=cap, operation_id=cap, resource_scope=scope,
            authorization_level=AuthorizationLevel.WRITE if cap.endswith(("write", "delete"))
                else AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    gateway = MCPGateway(caps, providers, engine)
    vision = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    camera = GovernedLocalCameraReader(
        gateway, authenticated_principal_id="owner", image_reader=vision,
        consent_lease=lease,
    )
    video = GovernedLocalVideoAnalyzer(
        gateway, authenticated_principal_id="owner", image_reader=vision,
    )
    memory = GovernedVisualMemory(
        store, engine, vision, authenticated_principal_id="owner", event_bus=bus,
    )
    verifier = GovernedVisualTaskVerifier(
        pixel, engine, vision, authenticated_principal_id="owner", event_bus=bus,
    )

    async def scenario():
        camera_evidence = await camera.describe_frame(session_id="owner-session")
        assert camera_evidence.trust == "UNTRUSTED_CAMERA_FRAME"
        assert not camera_evidence.computer_or_robot_actuation
        video_evidence = await video.analyze(_MP4, capture_confirmed=True)
        assert len(video_evidence.frames) == 1
        assert video_evidence.action_executed is False
        baseline, after = _png(0), _png(255)
        receipt = await memory.remember_image(baseline, capture_confirmed=True)
        assert memory.recall()[0].image_sha256 == receipt.image_sha256
        task = await verifier.verify(
            before=baseline, after=after,
            baseline_confirmed=True, after_confirmed=True,
            expected_observation="A red object changed color.",
        )
        assert task.pixels.classification == "OBSERVED_DIFFERENCE"
        assert task.task_success_verified is False and task.human_review_required
        assert memory.forget(memory_id=receipt.memory_id) is True
        lease.revoke()
        from aura_core.providers.opencv_camera_mcp import CameraReadDenied
        try:
            await camera.describe_frame(session_id="owner-session")
        except CameraReadDenied:
            pass
        else:
            raise AssertionError("Revoked camera consent accepted")
    asyncio.run(scenario())
    asserted_caps = {x.request.capability_id for x in engine.audit_records()}
    assert asserted_caps == {cap for cap, _ in policies}
    assert all(x.decision.decision is AuthorizationDecision.ALLOW for x in engine.audit_records())
    assert ("opencv", "read") in calls and ("opencv", "release") in calls
    assert any(x[0] == "ffmpeg" for x in calls)
    assert len([x for x in calls if x[0] == "model"]) == 5
    assert store.path.is_file()
    assert not hasattr(camera, "unlock") and not hasattr(video, "execute")
