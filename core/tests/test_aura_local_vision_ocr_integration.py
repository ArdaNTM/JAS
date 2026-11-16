"""End-to-end combined AURA Core vision + object-detection + OCR Gateway policies.

Runs the REAL Service/Capability/Provider registries, PermissionEngine and
MCPGateway, invoking real production model HTTP/CLI adapter code. Only the
external on-device Ollama server and Tesseract subprocess are simulated in CI.
"""
import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from aura_core.application.local_object_detection import GovernedLocalObjectDetector
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, ImageUnderstandingDenied,
    register_local_ollama_vision,
)
from aura_core.providers.tesseract_ocr_mcp import (
    GovernedOCRReader, OCRDenied, register_local_tesseract_ocr,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.mcp.provider import ProviderRegistry
from aura_core.mcp.gateway import MCPGateway

_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _runtime(monkeypatch):
    calls = {"model": 0, "ocr": 0}
    orig_client = httpx.AsyncClient

    def handle_http(request):
        calls["model"] += 1
        payload = json.loads(request.content)
        assert payload["model"] == "qwen2.5vl:3b"
        assert base64.b64decode(payload["messages"][0]["images"][0]) == _IMAGE
        return httpx.Response(200, json={"message": {"content": json.dumps({
            "objects": [{"label": "paper", "box": [0.1, 0.1, 0.8, 0.7]}],
        })}})

    def fake_client(*a, **kw):
        return orig_client(*a, transport=httpx.MockTransport(handle_http), **kw)
    monkeypatch.setattr("aura_core.providers.local_vision.httpx.AsyncClient", fake_client)

    class FakeOCRProcess:
        returncode = 0
        async def communicate(self, data):
            assert data == _IMAGE
            calls["ocr"] += 1
            return b"UNTRUSTED IMAGE TEXT\n", b""
    async def fake_exec(*args, **kwargs):
        assert args == ("/usr/bin/tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6")
        assert kwargs["env"]["LC_ALL"] == "C.UTF-8"
        return FakeOCRProcess()
    monkeypatch.setattr("aura_core.providers.tesseract_ocr_mcp.asyncio.create_subprocess_exec", fake_exec)

    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    capabilities = CapabilityRegistry(services)
    register_local_ollama_vision(services=services, providers=providers, capabilities=capabilities)
    register_local_tesseract_ocr(services=services, providers=providers, capabilities=capabilities)
    permissions = PermissionEngine(capabilities)
    gateway = MCPGateway(capabilities, providers, permissions)
    model = GovernedImageUnderstanding(gateway, authenticated_principal_id="owner")
    ocr = GovernedOCRReader(gateway, authenticated_principal_id="owner")
    return gateway, capabilities, providers, permissions, model, ocr, calls


def _grant(engine, capability_id, scope):
    engine.add_policy(PermissionPolicy(
        policy_id="owner." + capability_id,
        policy_version="1.0.0",
        principal_id="owner", capability_id=capability_id,
        operation_id=capability_id, resource_scope=scope,
        authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))


def test_two_real_registered_engines_have_separate_permissions(monkeypatch):
    gateway, caps, providers, engine, model, ocr, calls = _runtime(monkeypatch)
    assert {x.definition.capability_id for x in caps.records()} == {
        "vision.image.describe", "vision.ocr.extract",
    }
    assert {x.definition.provider_id for x in providers.records()} == {
        "vision.ollama.local", "ocr.tesseract.local",
    }
    async def run():
        with pytest.raises(OCRDenied):
            await ocr.read(_IMAGE, language="eng", capture_confirmed=True)
        with pytest.raises(ImageUnderstandingDenied):
            await model.describe(_IMAGE, prompt="Which object?", capture_confirmed=True)
        assert calls == {"model": 0, "ocr": 0}
        _grant(engine, "vision.ocr.extract", "vision/consented/ocr")
        result = await ocr.read(_IMAGE, language="eng", capture_confirmed=True)
        assert result.text == "UNTRUSTED IMAGE TEXT"
        assert result.trust == "UNTRUSTED_OCR_TEXT"
        assert calls == {"model": 0, "ocr": 1}
        with pytest.raises(ImageUnderstandingDenied):
            await model.describe(_IMAGE, prompt="Which object?", capture_confirmed=True)
        _grant(engine, "vision.image.describe", "vision/consented/image")
        locations = await GovernedLocalObjectDetector(model).detect(
            _IMAGE, capture_confirmed=True,
        )
        assert [item.label for item in locations.objects] == ["paper"]
        assert locations.objects[0].box == (0.1, 0.1, 0.8, 0.7)
        assert not locations.safe_for_automated_input
        assert calls == {"model": 1, "ocr": 1}
        assert result.image_sha256 == locations.image_sha256
        assert all(not hasattr(item, "execute") for item in locations.objects)
    asyncio.run(run())


def test_consent_revocation_denies_both_backends_before_model_or_ocr(monkeypatch):
    gateway, caps, providers, engine, model, ocr, calls = _runtime(monkeypatch)
    _grant(engine, "vision.ocr.extract", "vision/consented/ocr")
    _grant(engine, "vision.image.describe", "vision/consented/image")
    async def run():
        with pytest.raises(OCRDenied):
            await ocr.read(_IMAGE, language="eng", capture_confirmed=False)
        with pytest.raises(ImageUnderstandingDenied):
            await GovernedLocalObjectDetector(model).detect(_IMAGE, capture_confirmed=False)
    asyncio.run(run())
    assert calls == {"model": 0, "ocr": 0}
    assert engine.audit_records() == ()
