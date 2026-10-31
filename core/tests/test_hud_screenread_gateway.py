"""Security regression: no ScreenRead pixels without consumed local approval."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from aura_core.application.hud_api import router as hud_router
from aura_core.enterprise.approval_store import SQLiteApprovalStore
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.mcp.screen_read_provider import ScreenReadMCPProvider


class FakeCapture:
    def __init__(self):
        self.count = 0
    async def capture(self):
        self.count += 1
        return b"fake-image"


class FakeVision:
    def __init__(self):
        self.calls = []
    async def analyze(self, *, image_bytes, prompt):
        self.calls.append((image_bytes, prompt))
        return "Ekranda bir otomobil ve yol görülüyor."


def make_app(tmp_path, *, allowed=True):
    capture, vision = FakeCapture(), FakeVision()
    provider = ScreenReadMCPProvider(capture=capture, describer=vision)
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="screen-read", version="1", provider="test", category=ServiceCategory.MCP
    ), provider)
    caps, providers = CapabilityRegistry(services), ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="aura.screen-read", name="ScreenRead", version="1",
        service_id=service.service_id,
    ), provider)
    caps.register(CapabilityDefinition(
        capability_id="ScreenRead", name="ScreenRead", version="1",
        description="local approved capture", provider_id="aura.screen-read",
        provider_type=ProviderType.MCP, category=CapabilityCategory.VISION,
        tool_name="screen_read", risk_level="high",
    ))
    permissions = PermissionEngine(caps)
    if allowed:
        permissions.add_policy(PermissionPolicy(
            policy_id="screenread:interactive", policy_version="1",
            principal_id="local_owner", capability_id="ScreenRead",
            operation_id="ScreenRead", resource_scope="local_default",
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
            decision=AuthorizationDecision.REQUIRE_APPROVAL,
        ))
    store = SQLiteApprovalStore(str(tmp_path / "approvals.db"))
    bus = EventBus()
    gateway = MCPGateway(
        caps, providers, permissions,
        approval_store=store, approval_fingerprint_key=b"r" * 32, event_bus=bus,
    )
    app = FastAPI()
    app.include_router(hud_router)
    app.state.mcp_gateway = gateway
    app.state.approval_store = store
    app.state.screen_read_enabled = True
    app.state.kernel = SimpleNamespace(event_bus=bus)
    app.state.http_bearer_token = "k" * 40
    app.state.http_principal_id = "local_owner"
    app.state.screen_read_operator_approval = lambda question: True
    return app, capture, vision, store, bus


async def post(app, path, body, *, bearer=True):
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        return await client.post(
            path, json=body,
            headers={"Authorization": "Bearer " + "k" * 40} if bearer else {},
        )


def test_screenread_requires_bearer_and_user_confirmation(tmp_path):
    async def run():
        app, capture, _, store, _ = make_app(tmp_path)
        try:
            bad_auth = await post(app, "/api/hud/screen/read",
                                  {"prompt": "Bu ne?", "confirmed": True}, bearer=False)
            assert bad_auth.status_code == 401
            missing_consent = await post(app, "/api/hud/screen/read",
                                         {"prompt": "Bu ne?", "confirmed": False})
            assert missing_consent.status_code == 409
            assert capture.count == 0
        finally:
            store.close()
    asyncio.run(run())


def test_screenread_consumes_approval_before_capture(tmp_path):
    async def run():
        app, capture, vision, store, bus = make_app(tmp_path)
        event_types = []
        bus.subscribe("*", lambda event: event_types.append(event.event_type))
        try:
            response = await post(app, "/api/hud/screen/read",
                                  {"prompt": "Ekrandaki eşya ne?", "confirmed": True})
            assert response.status_code == 200, response.text
            assert response.json()["description"] == "Ekranda bir otomobil ve yol görülüyor."
            assert response.json()["bounding_boxes_verified"] is False
            assert "fake-image" not in response.text
            assert capture.count == 1 and len(vision.calls) == 1
            assert "untrusted data" in vision.calls[0][1]
            records = store.list_pending()
            assert not records
            for _ in range(6):
                await bus.dispatch_once()
            assert "HUDVisionScanStarted" in event_types
            assert "HUDVisionScanEnded" in event_types
        finally:
            store.close()
    asyncio.run(run())


def test_screenread_rejected_native_approval_never_captures(tmp_path):
    async def run():
        app, capture, _, store, _ = make_app(tmp_path)
        app.state.screen_read_operator_approval = lambda prompt: False
        try:
            response = await post(app, "/api/hud/screen/read",
                                  {"prompt": "Kim bu?", "confirmed": True})
            assert response.status_code == 403
            assert capture.count == 0
        finally:
            store.close()
    asyncio.run(run())


def test_screenread_missing_policy_never_prompts_or_captures(tmp_path):
    async def run():
        app, capture, _, store, _ = make_app(tmp_path, allowed=False)
        invoked = []
        app.state.screen_read_operator_approval = lambda prompt: invoked.append(prompt)
        try:
            response = await post(app, "/api/hud/screen/read",
                                  {"prompt": "Bu ne?", "confirmed": True})
            assert response.status_code == 403
            assert capture.count == 0 and not invoked
        finally:
            store.close()
    asyncio.run(run())


def test_screenread_provider_refuses_direct_call_even_with_capture():
    async def run():
        cap = FakeCapture()
        provider = ScreenReadMCPProvider(capture=cap, describer=FakeVision())
        with pytest.raises(PermissionError):
            await provider.call_tool("screen_read", {"prompt": "Bu ne?"})
        assert cap.count == 0
    asyncio.run(run())


def test_hud_presentation_does_not_trigger_screen_capture(tmp_path):
    async def run():
        app, capture, _, store, bus = make_app(tmp_path)
        try:
            response = await post(app, "/api/hud/panel",
                                  {"title": "Porsche 911", "kind": "object"})
            assert response.status_code == 200
            assert capture.count == 0
        finally:
            store.close()
    asyncio.run(run())


def test_vision_regions_are_model_estimates_and_invalid_boxes_discarded():
    from aura_core.mcp.screen_read_provider import _decode_visual_regions
    description, regions = _decode_visual_regions(
        '{"description":"İki araç var.","objects":['
        '{"label":"Araç A","box":[0.1,0.2,0.4,0.6]},'
        '{"label":"Uydurma","box":[0.2,-0.1,0.3,0.4]},'
        '{"label":"Yanlış","box":[0.7,0.7,0.3,0.9]}]}'
    )
    assert description == "İki araç var."
    assert regions == [{
        "label": "Araç A", "x": 0.1, "y": 0.2,
        "width": 0.30000000000000004, "height": 0.39999999999999997,
        "verified": False, "source": "model_estimate",
    }]
    fenced, empty = _decode_visual_regions('```json\n{"description":"Test","objects":[]}\n```')
    assert fenced == "Test" and empty == []

def test_qwen_array_pixel_boxes_are_parsed_without_leaking_raw_json():
    from aura_core.mcp.screen_read_provider import _decode_visual_regions
    raw = '[{"description":"AURA ana sayfası","objects":[{"label":"AURA","box":[0,0,956,1064]}]}]'
    description, regions = _decode_visual_regions(raw, (956, 1064))
    assert description == "AURA ana sayfası"
    assert len(regions) == 1
    assert regions[0]["x"] == 0 and regions[0]["y"] == 0
    assert regions[0]["width"] == 1 and regions[0]["height"] == 1
    assert regions[0]["verified"] is False
    assert "objects" not in description


def test_qwen_invalid_boxes_do_not_escape_image():
    from aura_core.mcp.screen_read_provider import _decode_visual_regions
    raw = '{"description":"Araçlar","objects":[{"name":"car","bbox":[100,150,650,450]},{"label":"fake","box":[0,0,9000,9000]}]}'
    text, regions = _decode_visual_regions(raw, (1200, 800))
    assert text == "Araçlar"
    assert len(regions) == 1
    assert regions[0]["width"] == (650 - 100) / 1200
    assert regions[0]["height"] == (450 - 150) / 800


def test_trusted_session_requires_native_approval_and_caps_gateway_captures(tmp_path):
    from aura_core.application.hud_api import TrustedScreenReadSessions

    async def run():
        app, capture, _, store, _ = make_app(tmp_path)
        app.state.hud_trusted_sessions = TrustedScreenReadSessions()
        app.state.hud_session_operator_approval = lambda prompt: False
        try:
            refused = await post(app, "/api/hud/session/start", {"confirmed": True})
            assert refused.status_code == 403
            assert capture.count == 0

            app.state.hud_session_operator_approval = lambda prompt: True
            armed = await post(app, "/api/hud/session/start", {"confirmed": True})
            assert armed.status_code == 200
            token = armed.json()["token"]
            assert armed.json()["captures_remaining"] == 3
            for _ in range(3):
                result = await post(app, "/api/hud/screen/read", {
                    "prompt": "Ekrandaki yazı?", "confirmed": True,
                    "trusted_session_token": token,
                })
                assert result.status_code == 200, result.text
            assert capture.count == 3
            expired = await post(app, "/api/hud/screen/read", {
                "prompt": "Ekrandaki yazı?", "confirmed": True,
                "trusted_session_token": token,
            })
            assert expired.status_code == 403
            assert capture.count == 3
        finally:
            store.close()
    asyncio.run(run())


def test_trusted_session_binds_principal_and_can_be_revoked():
    from aura_core.application.hud_api import TrustedScreenReadSessions

    async def run():
        sessions = TrustedScreenReadSessions()
        token = await sessions.create("user-a")
        assert not await sessions.consume(token, "user-b")
        next_token = await sessions.create("user-a")
        assert not await sessions.consume(token, "user-a")
        await sessions.revoke(next_token, "user-b")
        assert await sessions.consume(next_token, "user-a")
        await sessions.revoke(next_token, "user-a")
        assert not await sessions.consume(next_token, "user-a")
    asyncio.run(run())


def test_media_source_whitelist_and_strict_license_metadata():
    from aura_core.mcp.hud_media_provider import _trusted_image, _plain
    assert _trusted_image("https://upload.wikimedia.org/wikipedia/commons/a/b/car.jpg",
                          "upload.wikimedia.org")
    assert _trusted_image("https://evil.example/track.png", "upload.wikimedia.org") is None
    assert _trusted_image("http://upload.wikimedia.org/track.png", "upload.wikimedia.org") is None
    assert _plain({"value": "<b>Artist</b> &amp; Creator"}) == "Artist & Creator"

def test_jpeg_sof_dimensions_are_read_without_image_decoder():
    from aura_core.mcp.screen_read_provider import _jpeg_dimensions
    # SOI + baseline SOF0 with a 956 x 1064 image + EOI.
    sample = bytes.fromhex("ffd8ffc0001108042803bc03011100021101031101ffd9")
    assert _jpeg_dimensions(sample) == (956, 1064)
    assert _jpeg_dimensions(b"invalid") is None
