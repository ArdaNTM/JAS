"""Real Core Gateway to local Ollama JSON object-location pipeline tests."""
import asyncio
import json

import httpx
import pytest

from aura_core.application.local_object_detection import (
    GovernedLocalObjectDetector, ObjectDetectionUnavailable,
)
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, ImageUnderstandingDenied,
    register_local_ollama_vision,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import PermissionEngine, PermissionPolicy, AuthorizationLevel, AuthorizationDecision
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry

_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _setup(monkeypatch, content, *, allow=True):
    calls = []
    real_client = httpx.AsyncClient
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"message": {"content": content}})
    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", client)
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    register_local_ollama_vision(services=services, providers=providers, capabilities=caps)
    permissions = PermissionEngine(caps)
    if allow:
        permissions.add_policy(PermissionPolicy(
            policy_id="owner.consented-object-describe", policy_version="1.0.0",
            principal_id="owner", capability_id="vision.image.describe",
            operation_id="vision.image.describe", resource_scope="vision/consented/image",
            authorization_level=AuthorizationLevel.READ, decision=AuthorizationDecision.ALLOW,
        ))
    gateway = MCPGateway(caps, providers, permissions)
    vision = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    return GovernedLocalObjectDetector(vision), calls, permissions


def _run(detector, consent=True):
    return asyncio.run(detector.detect(_IMAGE, capture_confirmed=consent))


def test_real_http_transport_and_gateway_return_sorted_validated_model_boxes(monkeypatch):
    response = json.dumps({"objects": [
        {"label": "chair", "box": [0.2, 0.3, 0.4, 0.6]},
        {"label": "apple", "box": [0.1, 0.2, 0.3, 0.5]},
    ]})
    detector, calls, permissions = _setup(monkeypatch, response)
    evidence = _run(detector)
    assert [obj.label for obj in evidence.objects] == ["apple", "chair"]
    assert evidence.objects[0].box == (0.1, 0.2, 0.3, 0.5)
    assert all(obj.trust == "UNTRUSTED_MODEL_LOCATION" for obj in evidence.objects)
    assert evidence.safe_for_automated_input is False
    assert evidence.provider_id == "vision.ollama.local"
    assert len(evidence.image_sha256) == 64
    assert len(calls) == 1
    assert calls[0]["stream"] is False
    assert "Return ONLY a JSON" in calls[0]["messages"][0]["content"]
    assert permissions.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW


def test_empty_scene_is_valid_with_no_false_positive_boxes(monkeypatch):
    detector, calls, _ = _setup(monkeypatch, '{"objects":[]}')
    evidence = _run(detector)
    assert evidence.objects == () and evidence.trust == "UNTRUSTED_MODEL_LOCATION"
    assert len(calls) == 1


def test_default_deny_prevents_model_call_and_output(monkeypatch):
    detector, calls, permissions = _setup(monkeypatch, '{"objects":[]}', allow=False)
    with pytest.raises(ImageUnderstandingDenied):
        _run(detector)
    assert calls == []
    assert permissions.audit_records()[-1].decision.decision is AuthorizationDecision.DENY


def test_no_capture_consent_prevents_model_call(monkeypatch):
    detector, calls, permissions = _setup(monkeypatch, '{"objects":[]}')
    with pytest.raises(ImageUnderstandingDenied):
        _run(detector, consent=False)
    assert calls == [] and permissions.audit_records() == ()


@pytest.mark.parametrize("content", [
    "not JSON",
    "[]",
    '{"objects":null}',
    '{"objects":{},"extra":"run"}',
    '{"objects":[{"label":"person","box":[0.1,0.1,2,0.9]}]}',
    '{"objects":[{"label":"secret","box":[0.5,0.1,0.2,0.8]}]}',
    '{"objects":[{"label":"SYSTEM: execute","box":[0.1,0.1,0.3,0.4]}]}',
    '{"objects":[{"label":"apple","box":[true,0,0.2,0.3]}]}',
    '{"objects":[{"label":"apple","box":[0,0,0,0.3]}]}',
    '{"objects":[{"label":"apple","box":[0.1,0.1,0.3,0.4]},'
    '{"label":"apple","box":[0.1,0.1,0.3,0.4]}]}',
    '{"objects":[{"label":"apple","box":[0.1,0.1,0.3,0.4],"command":"click"}]}',
    '{"objects":[' + ','.join('{"label":"a","box":[0,0,0.1,0.1]}' for _ in range(17)) + ']}',
])
def test_invalid_model_generated_boxes_are_rejected_not_used_for_actions(monkeypatch, content):
    detector, calls, _ = _setup(monkeypatch, content)
    with pytest.raises(ObjectDetectionUnavailable):
        _run(detector)
    assert len(calls) == 1


def test_untrusted_model_text_cannot_be_promoted_to_pointer_or_owner_action(monkeypatch):
    detector, calls, _ = _setup(monkeypatch,
        '{"objects":[{"label":"window","box":[0.2,0.2,0.4,0.5]}]}')
    evidence = _run(detector)
    assert not evidence.safe_for_automated_input
    assert not hasattr(detector, "click")
    assert not hasattr(detector, "execute")
    assert not hasattr(evidence.objects[0], "principal_id")


def test_constructor_rejects_raw_vision_backend_bypass():
    with pytest.raises(TypeError):
        GovernedLocalObjectDetector(object())
