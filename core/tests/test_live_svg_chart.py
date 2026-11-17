"""Real EventBus telemetry -> registry/Gateway -> authenticated SVG HTTP integration."""
import asyncio
from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.live_svg_chart import (
    GovernedLiveSVGChart, LiveChartDenied, LiveChartUnavailable,
    LocalGatewayLatencyMCP, live_svg_chart_router, register_live_svg_chart,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry


def _system(*, decision=None, principal="owner"):
    bus = EventBus()
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    capabilities = CapabilityRegistry(services)
    backend = register_live_svg_chart(
        services=services, providers=providers,
        capabilities=capabilities, event_bus=bus,
    )
    engine = PermissionEngine(capabilities)
    if decision is not None:
        engine.add_policy(PermissionPolicy(
            policy_id="owner.read.telemetry", policy_version="1.0.0",
            principal_id="owner",
            capability_id="visualization.telemetry.read",
            operation_id="visualization.telemetry.read",
            resource_scope="visualization/gateway-latency/read-only",
            authorization_level=AuthorizationLevel.READ,
            decision=decision,
        ))
    reader = GovernedLiveSVGChart(
        MCPGateway(capabilities, providers, engine),
        authenticated_principal_id=principal,
    )
    return bus, backend, reader, engine, providers, capabilities


def _event(duration, *, event_type="Telemetry.MCPGatewayExecution",
           source="aura.mcp.gateway", extra=None):
    return KernelEvent(
        event_type=event_type, source_component=source,
        payload={"duration_ms": duration, "token": "SECRET_PROHIBITED", **(extra or {})},
    )


def _deliver(bus, *events):
    for event in events:
        bus.publish(event)
    for event in events:
        assert asyncio.run(bus.dispatch_once()) is True


def test_real_eventbus_to_gateway_into_local_svg_renderer():
    bus, backend, reader, engine, providers, caps = _system(
        decision=AuthorizationDecision.ALLOW,
    )
    _deliver(bus, _event(20.75), _event(49.125), _event(1999.5))
    result = asyncio.run(reader.render())
    assert result.sample_count == 3
    assert result.read_only and result.trust == "REDACTED_UNTRUSTED_TELEMETRY"
    assert result.svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'viewBox="0 0 640 240"' in result.svg
    assert "M40.0," in result.svg and "L600.0," in result.svg
    assert "SECRET_PROHIBITED" not in result.svg
    assert "token" not in result.svg
    assert "script" not in result.svg.casefold()
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
    assert providers.resolve("visualization.telemetry.local") is backend
    assert caps.resolve("visualization.telemetry.read").definition.tool_name == "read_latency_samples"
    with pytest.raises(FrozenInstanceError):
        result.sample_count = 99


@pytest.mark.parametrize("decision", [
    None, AuthorizationDecision.DENY, AuthorizationDecision.REQUIRE_APPROVAL,
])
def test_explicit_denial_or_pending_approval_never_exposes_svg(decision):
    bus, backend, reader, engine, *_ = _system(decision=decision)
    _deliver(bus, _event(17))
    with pytest.raises(LiveChartDenied):
        asyncio.run(reader.render())
    assert engine.audit_records()[-1].decision.decision is not AuthorizationDecision.ALLOW


def test_only_fixed_source_and_bounded_numeric_measurements_are_accepted():
    bus, backend, reader, engine, *_ = _system(
        decision=AuthorizationDecision.ALLOW,
    )
    _deliver(bus,
        _event(1, source="untrusted.component"),
        _event(2, event_type="UserMessages"),
        _event("999"),
        _event(True),
        _event(float("nan")),
        _event(-10),
        _event(60001),
        _event(42.5),
    )
    snapshot = asyncio.run(reader.render())
    assert snapshot.sample_count == 1
    assert "SECRET_PROHIBITED" not in snapshot.svg
    assert "<text x=" in snapshot.svg


def test_ring_buffer_is_bounded_and_repeated_reads_are_new_gateway_auth():
    bus, backend, reader, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    _deliver(bus, *[_event(float(i)) for i in range(150)])
    first = asyncio.run(reader.render())
    second = asyncio.run(reader.render())
    assert first.sample_count == second.sample_count == 120
    assert first.svg == second.svg
    assert len(engine.audit_records()) == 2
    backend.close()


def test_direct_provider_call_without_gateway_dispatch_is_denied():
    bus, backend, reader, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    with pytest.raises(LiveChartDenied):
        asyncio.run(backend.call_tool("read_latency_samples", {}))
    assert engine.audit_records() == ()


def test_untrusted_numeric_result_cannot_inject_markup():
    bus, backend, reader, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    async def forged(name, arguments):
        return {"trust": "REDACTED_UNTRUSTED_TELEMETRY",
                "samples": [12, '<script>alert(1)</script>']}
    backend.call_tool = forged
    with pytest.raises(LiveChartUnavailable):
        asyncio.run(reader.render())


def test_failed_provider_errors_are_sanitized():
    bus, backend, reader, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    async def failed(name, args):
        raise RuntimeError("Bearer MY_SECRET")
    backend.call_tool = failed
    with pytest.raises(LiveChartUnavailable) as err:
        asyncio.run(reader.render())
    assert "MY_SECRET" not in str(err.value)


def test_fastapi_http_bearer_and_separate_gateway_authorization_are_required():
    bus, backend, reader, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    _deliver(bus, _event(22.5))
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "owner"
    app.state.live_svg_chart = reader
    app.include_router(live_svg_chart_router)
    with TestClient(app) as client:
        assert client.get("/api/runtime/gateway-latency.svg").status_code == 401
        response = client.get(
            "/api/runtime/gateway-latency.svg",
            headers={"Authorization": "Bearer " + "t" * 40},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert response.headers["cache-control"] == "private, no-store"
        assert "script-src 'none'" in response.headers["content-security-policy"]
        assert response.text.startswith("<svg")
        assert "SECRET_PROHIBITED" not in response.text


def test_fastapi_does_not_infer_gateway_policy_from_bearer_auth():
    bus, backend, reader, engine, *_ = _system()
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "owner"
    app.state.live_svg_chart = reader
    app.include_router(live_svg_chart_router)
    with TestClient(app) as client:
        response = client.get("/api/runtime/gateway-latency.svg",
                              headers={"Authorization": "Bearer " + "t" * 40})
    assert response.status_code == 403


def test_http_wrong_bound_principal_does_not_read_other_owners_samples():
    bus, backend, reader, engine, *_ = _system(
        decision=AuthorizationDecision.ALLOW,
    )
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "other"
    app.state.live_svg_chart = reader
    app.include_router(live_svg_chart_router)
    with TestClient(app) as client:
        response = client.get("/api/runtime/gateway-latency.svg",
                              headers={"Authorization": "Bearer " + "t" * 40})
    assert response.status_code == 403
    assert engine.audit_records() == ()


def test_live_router_fails_closed_when_not_wired():
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "owner"
    app.include_router(live_svg_chart_router)
    with TestClient(app) as client:
        response = client.get("/api/runtime/gateway-latency.svg",
                              headers={"Authorization": "Bearer " + "t" * 40})
    assert response.status_code == 503


def test_provider_registration_does_not_create_read_permission():
    bus, backend, reader, engine, providers, caps = _system()
    with pytest.raises(LiveChartDenied):
        asyncio.run(reader.render())
    with pytest.raises(ValueError):
        register_live_svg_chart(
            services=providers._service_registry, providers=providers,
            capabilities=caps, event_bus=bus,
        )
    assert len(caps.records()) == len(providers.records()) == 1
