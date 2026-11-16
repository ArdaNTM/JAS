"""Real registered OpenCV device adapter and dual MCP Gateway camera/vision policies."""
import asyncio
import base64
import hashlib
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from aura_core.providers.opencv_camera_mcp import (
    CameraReadDenied, CameraUnavailable, GovernedLocalCameraReader,
    LocalOpenCVCameraMCP, OwnerCameraConsentLease, register_local_opencv_camera,
)
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, register_local_ollama_vision,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.provider import ProviderRegistry

_JPEG = b"\xff\xd8\xff" + b"x" * 32 + b"\xff\xd9"


def _system(
    monkeypatch, *, allow_camera=True, allow_image=True, armed=True,
    opened=True, valid_image=True, device_index=0,
):
    calls = []
    model_calls = []
    class Capture:
        def isOpened(self):
            return opened
        def set(self, name, value):
            calls.append(("set", name, value))
            return True
        def read(self):
            calls.append(("read",))
            return True, SimpleNamespace(shape=(480, 640, 3))
        def release(self):
            calls.append(("release",))
    class Encoded:
        def tobytes(self):
            return _JPEG if valid_image else b"not-jpeg"
    def capture(index, backend):
        calls.append(("open", index, backend))
        return Capture()
    def imencode(ext, image, opts):
        calls.append(("encode", ext, tuple(opts)))
        return True, Encoded()
    cv = SimpleNamespace(
        CAP_ANY=0, CAP_DSHOW=1, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, IMWRITE_JPEG_QUALITY=20,
        VideoCapture=capture, imencode=imencode,
    )
    monkeypatch.setitem(sys.modules, "cv2", cv)
    real_client = httpx.AsyncClient
    def handle(request):
        body = json.loads(request.content)
        model_calls.append(body)
        assert request.url.path == "/api/chat"
        assert base64.b64decode(body["messages"][0]["images"][0]) == _JPEG
        return httpx.Response(200, json={"message": {"content": "A small desk lamp."}})
    def client(*a, **kw):
        return real_client(*a, transport=httpx.MockTransport(handle), **kw)
    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", client)

    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    lease = OwnerCameraConsentLease(authenticated_principal_id="owner")
    if armed:
        lease.arm(session_id="session1", owner_confirmed=True)
    camera = register_local_opencv_camera(
        services=services, providers=providers, capabilities=caps,
        trusted_device_index=device_index, consent_lease=lease,
    )
    register_local_ollama_vision(services=services, providers=providers, capabilities=caps)
    engine = PermissionEngine(caps)
    for active, op, scope in (
        (allow_camera, "vision.camera.frame.read", f"vision/camera/{device_index}/frame"),
        (allow_image, "vision.image.describe", "vision/consented/image"),
    ):
        if active:
            engine.add_policy(PermissionPolicy(
                policy_id="owner." + op, policy_version="1.0.0",
                principal_id="owner", capability_id=op, operation_id=op,
                resource_scope=scope,
                authorization_level=AuthorizationLevel.READ,
                decision=AuthorizationDecision.ALLOW,
            ))
    gateway = MCPGateway(caps, providers, engine)
    image_reader = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    reader = GovernedLocalCameraReader(
        gateway, authenticated_principal_id="owner",
        image_reader=image_reader, consent_lease=lease,
        trusted_device_index=device_index,
    )
    return reader, camera, lease, engine, gateway, calls, model_calls, image_reader


def _run(reader, *, session="session1"):
    return asyncio.run(reader.describe_frame(session_id=session))


def test_live_opencv_backend_uses_two_distinct_gateway_permissions(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, image_reader = _system(monkeypatch)
    result = _run(reader)
    assert result.description == "A small desk lamp."
    assert result.image_sha256 == hashlib.sha256(_JPEG).hexdigest()
    assert result.trust == "UNTRUSTED_CAMERA_FRAME"
    assert result.computer_or_robot_actuation is False
    assert len(model_calls) == 1
    assert calls[0][0:2] == ("open", 0)
    assert ("read",) in calls and ("release",) in calls
    assert any(c[0] == "encode" for c in calls)
    assert [a.request.capability_id for a in engine.audit_records()] == [
        "vision.camera.frame.read", "vision.image.describe",
    ]
    assert all(a.decision.decision is AuthorizationDecision.ALLOW for a in engine.audit_records())


def test_default_denied_camera_policy_cannot_touch_device_or_model(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, allow_camera=False,
    )
    with pytest.raises(CameraReadDenied):
        _run(reader)
    assert calls == [] and model_calls == []
    assert engine.audit_records()[0].decision.decision is AuthorizationDecision.DENY


def test_second_model_permission_does_not_follow_camera_read(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, allow_image=False,
    )
    with pytest.raises(CameraUnavailable):
        _run(reader)
    assert ("read",) in calls and len(model_calls) == 0
    assert [a.decision.decision for a in engine.audit_records()] == [
        AuthorizationDecision.ALLOW, AuthorizationDecision.DENY,
    ]


def test_unarmed_or_revoked_owner_lease_denies_before_gateway(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, armed=False,
    )
    with pytest.raises(CameraReadDenied):
        _run(reader)
    assert engine.audit_records() == () and calls == []
    lease.arm(session_id="session1", owner_confirmed=True)
    lease.revoke()
    with pytest.raises(CameraReadDenied):
        _run(reader)
    assert calls == []


def test_direct_gateway_with_allow_policy_but_unarmed_lease_cannot_capture(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, armed=False,
    )
    with pytest.raises(CameraReadDenied):
        asyncio.run(gateway.invoke(MCPGatewayRequest(
            request_id="direct-capture", principal_id="owner",
            capability_id="vision.camera.frame.read",
            operation_id="vision.camera.frame.read",
            resource_scope="vision/camera/0/frame", risk_level=RiskLevel.HIGH,
            tool_name="capture_local_camera_frame",
            arguments={"session_id": "session1"}, session_id="session1",
        )))
    assert calls == [] and model_calls == []
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW


def test_direct_provider_invocation_outside_gateway_denied(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(monkeypatch)
    with pytest.raises(CameraReadDenied):
        asyncio.run(camera.call_tool("capture_local_camera_frame", {"session_id": "session1"}))
    assert calls == [] and model_calls == []


def test_wrong_dispatch_owner_does_not_bypass_lease(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(monkeypatch)
    token = enter_dispatch(DispatchGrant(
        principal_id="intruder", capability_id="vision.camera.frame.read",
        tool_name="capture_local_camera_frame", approval_consumed=False, risk_level="high",
    ))
    try:
        with pytest.raises(CameraReadDenied):
            asyncio.run(camera.call_tool("capture_local_camera_frame", {"session_id": "session1"}))
    finally:
        leave_dispatch(token)
    assert calls == []


def test_device_unavailable_releases_handle_and_does_not_run_model(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, opened=False,
    )
    with pytest.raises(CameraUnavailable):
        _run(reader)
    assert calls[0][0] == "open"
    assert ("release",) in calls and model_calls == []


def test_invalid_encoded_jpeg_fails_closed_after_capture(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(
        monkeypatch, valid_image=False,
    )
    with pytest.raises(CameraUnavailable):
        _run(reader)
    assert ("release",) in calls and model_calls == []


@pytest.mark.parametrize("session", [
    "", "session1\nadmin", "other", " session1 ", "x" * 129,
])
def test_invalid_or_unapproved_session_never_reaches_gateway(monkeypatch, session):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(monkeypatch)
    with pytest.raises((CameraReadDenied, ValueError)):
        _run(reader, session=session)
    assert calls == [] and model_calls == [] and engine.audit_records() == ()


def test_revocation_during_frame_read_prevents_model_analysis(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, _ = _system(monkeypatch)
    original = camera._capture_once
    def capture_then_revoke():
        result = original()
        lease.revoke()
        return result
    monkeypatch.setattr(camera, "_capture_once", capture_then_revoke)
    with pytest.raises(CameraReadDenied):
        _run(reader)
    assert ("read",) in calls
    assert model_calls == []


@pytest.mark.parametrize("index", [-1, 4, True, "0"])
def test_cannot_select_untrusted_camera_device(index):
    with pytest.raises(ValueError):
        LocalOpenCVCameraMCP(
            consent_lease=OwnerCameraConsentLease(authenticated_principal_id="owner"),
            trusted_device_index=index,
        )


def test_camera_lease_must_be_trusted_and_not_caller_flag():
    lease = OwnerCameraConsentLease(authenticated_principal_id="owner")
    with pytest.raises(CameraReadDenied):
        lease.arm(session_id="s", owner_confirmed=False)
    with pytest.raises(ValueError):
        lease.arm(session_id="s", owner_confirmed=True, ttl_seconds=301)
    with pytest.raises(CameraReadDenied):
        lease.require(session_id="s")


def test_wrong_lease_identity_or_different_device_fails_reader_constructor(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, image = _system(monkeypatch)
    with pytest.raises(CameraReadDenied):
        GovernedLocalCameraReader(
            gateway, authenticated_principal_id="owner",
            image_reader=image,
            consent_lease=OwnerCameraConsentLease(authenticated_principal_id="owner"),
        )
    with pytest.raises(CameraReadDenied):
        GovernedLocalCameraReader(
            gateway, authenticated_principal_id="other",
            image_reader=image, consent_lease=lease,
        )
    with pytest.raises(CameraReadDenied):
        GovernedLocalCameraReader(
            gateway, authenticated_principal_id="owner",
            image_reader=image, consent_lease=lease, trusted_device_index=1,
        )


def test_real_local_camera_never_opened_automatically_on_registration(monkeypatch):
    reader, camera, lease, engine, gateway, calls, model_calls, image = _system(monkeypatch)
    assert calls == [] and model_calls == []
    assert engine.audit_records() == ()
    with pytest.raises(ValueError):
        register_local_opencv_camera(
            services=gateway._provider_registry._service_registry,
            providers=gateway._provider_registry,
            capabilities=gateway._capability_registry,
            consent_lease=lease,
        )
    assert calls == []
