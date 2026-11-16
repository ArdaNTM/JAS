"""Safe read-only live status projection and protected HTTP route integration (#93)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.safe_live_status import SafeLiveStatus, live_status_router
from aura_core.application.system_telemetry import SystemTelemetry
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.health import HealthMonitor, HealthReport
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry

_HEADERS = {"Authorization": "Bearer " + "x" * 40}


def _system(monkeypatch):
    services = ServiceRegistry()
    registered = services.register(ServiceDefinition(
        name="private-provider-host-key", version="1.0.0",
        provider="secret-host", category=ServiceCategory.CORE,
    ), object())
    capabilities = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="private-provider-secret",
        name="private-model-identifier", version="1.0.0",
        service_id=registered.service_id,
        metadata={"api_key": "PRIVATE_TOKEN_SECRET"},
    ), object())
    capabilities.register(CapabilityDefinition(
        capability_id="private.database.query",
        name="Secret private capability", version="1.0.0",
        description="private credentials", provider_id="private-provider-secret",
        provider_type=ProviderType.MCP, category=CapabilityCategory.DIAGNOSTICS,
        risk_level="medium",
    ))
    health = HealthMonitor(services, capabilities)
    health.report(HealthReport(
        service_id=registered.service_id, available=True, ready=True, live=True,
    ))
    telemetry = SystemTelemetry()
    monkeypatch.setattr(telemetry, "snapshot", lambda: {
        "status": "ok", "sampled_at": "2026-11-16T11:02:03+00:00",
        "cpu_percent": 41.25, "memory_percent": 55.12,
        "backend_endpoint": "http://private.internal:8080",
        "OPENAI_API_KEY": "PRIVATE_TOKEN_SECRET",
        "alerts": [
            {"code": "cpu_pressure", "message": "secret provider"},
            {"code": "arbitrary-secret", "message": "PRIVATE_TOKEN_SECRET"},
        ],
    })
    view = SafeLiveStatus(services, capabilities, providers, health, telemetry)
    return view, services, providers, capabilities, health, telemetry, registered.service_id


def _client(view: SafeLiveStatus | None, *, bearer=True):
    app = FastAPI()
    app.state.http_bearer_token = "x" * 40 if bearer else None
    app.state.http_principal_id = "authenticated-owner"
    if view is not None:
        app.state.safe_live_status = view
    app.include_router(live_status_router)
    return TestClient(app)


def test_real_healthy_core_aggregates_without_leaking_identity_or_credential(monkeypatch):
    view, *_ = _system(monkeypatch)
    response = _client(view).get("/api/runtime/live-status", headers=_HEADERS)
    assert response.status_code == 200
    result = response.json()
    assert result == {
        "status": "ok",
        "sampled_at": "2026-11-16T11:02:03+00:00",
        "services_total": 1,
        "services_healthy": 1,
        "services_degraded": 0,
        "services_unknown": 0,
        "capabilities_total": 1,
        "capabilities_available": 1,
        "providers_total": 1,
        "providers_healthy": 1,
        "cpu_percent": 41.2,
        "memory_percent": 55.1,
        "alert_codes": ["cpu_pressure"],
    }
    serialized = response.text
    for secret in ("PRIVATE_TOKEN_SECRET", "private-provider-secret",
                   "private.internal", "secret-host", "private.database.query"):
        assert secret not in serialized


def test_no_bearer_is_denied_before_status_sampling(monkeypatch):
    view, _, _, _, _, telemetry, _ = _system(monkeypatch)
    calls = []
    monkeypatch.setattr(telemetry, "snapshot", lambda: calls.append(True))
    response = _client(view).get("/api/runtime/live-status")
    assert response.status_code == 401
    assert calls == []


def test_missing_status_service_is_503_not_unprotected_fallback():
    response = _client(None).get("/api/runtime/live-status", headers=_HEADERS)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_missing_server_auth_is_fail_closed(monkeypatch):
    view, *_ = _system(monkeypatch)
    response = _client(view, bearer=False).get("/api/runtime/live-status", headers=_HEADERS)
    assert response.status_code == 503


def test_degraded_or_missing_health_does_not_claim_all_healthy(monkeypatch):
    view, _, _, _, health, _, sid = _system(monkeypatch)
    health.report(HealthReport(
        service_id=sid, available=False, ready=False, live=False,
    ))
    result = view.snapshot()
    assert result.status == "degraded"
    assert result.services_healthy == 0
    assert result.services_degraded == 1
    assert result.services_unknown == 0


def test_bad_telemetry_is_unavailable_with_no_sensitive_raw_metrics(monkeypatch):
    view, _, _, _, _, telemetry, _ = _system(monkeypatch)
    monkeypatch.setattr(telemetry, "snapshot", lambda: {
        "status": "ok", "cpu_percent": float("nan"),
        "memory_percent": 123, "sampled_at": "not a timestamp",
        "alerts": [{"code": "secret_alert", "message": "PRIVATE_TOKEN_SECRET"}],
    })
    result = view.snapshot()
    assert result.status == "unavailable"
    assert result.cpu_percent is None
    assert result.memory_percent is None
    assert result.sampled_at is None
    assert result.alert_codes == ()


def test_invalid_telemetry_sample_exception_is_sanitized(monkeypatch):
    view, _, _, _, _, telemetry, _ = _system(monkeypatch)
    def failed():
        raise RuntimeError("PRIVATE_TOKEN_SECRET: /private/key.pem")
    monkeypatch.setattr(telemetry, "snapshot", failed)
    response = _client(view).get("/api/runtime/live-status", headers=_HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert "PRIVATE_TOKEN_SECRET" not in response.text


def test_status_endpoint_fails_closed_on_core_registry_failure(monkeypatch):
    view, services, *_ = _system(monkeypatch)
    def failed():
        raise RuntimeError("PRIVATE_TOKEN_SECRET: unexpected provider error")
    monkeypatch.setattr(services, "records", failed)
    response = _client(view).get("/api/runtime/live-status", headers=_HEADERS)
    assert response.status_code == 503
    assert response.json()["detail"] == "Safe live status unavailable"
    assert "PRIVATE_TOKEN_SECRET" not in response.text


def test_constructor_rejects_fake_registries_or_telemetry(monkeypatch):
    view, services, providers, capabilities, health, telemetry, _ = _system(monkeypatch)
    for args in (
        (object(), capabilities, providers, health, telemetry),
        (services, object(), providers, health, telemetry),
        (services, capabilities, object(), health, telemetry),
        (services, capabilities, providers, object(), telemetry),
        (services, capabilities, providers, health, object()),
    ):
        import pytest
        with pytest.raises(TypeError):
            SafeLiveStatus(*args)
