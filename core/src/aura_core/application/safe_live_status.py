"""Authenticated, redacted live Core status projection for HUD consumers.

All data comes from *existing* Kernel registries, HealthMonitor, and local
SystemTelemetry. No raw provider IDs, endpoints, token values, task content,
memory records or event payloads are exposed.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_core.application.system_telemetry import SystemTelemetry
from aura_core.kernel.capabilities import CapabilityRegistry, CapabilityState
from aura_core.kernel.health import HealthMonitor, HealthState
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.provider import ProviderRegistry
from aura_core.security.http_auth import authenticated_principal


@dataclass(frozen=True, slots=True)
class RedactedLiveStatus:
    status: str
    sampled_at: str | None
    services_total: int
    services_healthy: int
    services_degraded: int
    services_unknown: int
    capabilities_total: int
    capabilities_available: int
    providers_total: int
    providers_healthy: int
    cpu_percent: float | None
    memory_percent: float | None
    alert_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["alert_codes"] = list(self.alert_codes)
        return data


def _percent(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    candidate = float(value)
    if not math.isfinite(candidate) or not 0 <= candidate <= 100:
        return None
    return round(candidate, 1)


def _sampled_at(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return timestamp.isoformat()


class SafeLiveStatus:
    """Read-only projection with no permission or tool execution side effects.

    Endpoint authentication is done in live_status_router. An application must
    explicitly wire this service and router to expose it; no global unauthenticated
    diagnostics route is installed by this module.
    """

    def __init__(
        self,
        services: ServiceRegistry,
        capabilities: CapabilityRegistry,
        providers: ProviderRegistry,
        health: HealthMonitor,
        telemetry: SystemTelemetry,
    ) -> None:
        if not isinstance(services, ServiceRegistry):
            raise TypeError("authoritative ServiceRegistry required")
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("authoritative CapabilityRegistry required")
        if not isinstance(providers, ProviderRegistry):
            raise TypeError("authoritative ProviderRegistry required")
        if not isinstance(health, HealthMonitor):
            raise TypeError("authoritative HealthMonitor required")
        if not isinstance(telemetry, SystemTelemetry):
            raise TypeError("existing SystemTelemetry required")
        self._services = services
        self._capabilities = capabilities
        self._providers = providers
        self._health = health
        self._telemetry = telemetry

    def snapshot(self) -> RedactedLiveStatus:
        service_records = self._services.records()
        capabilities = self._capabilities.records()
        providers = self._providers.records()
        reports = {component.service_id: component.state for component in self._health.components()}
        try:
            raw: Any = self._telemetry.snapshot()
        except Exception:
            raw = None
        safe = raw if isinstance(raw, dict) else {}
        cpu = _percent(safe.get("cpu_percent"))
        memory = _percent(safe.get("memory_percent"))
        sampled_at = _sampled_at(safe.get("sampled_at"))
        telemetry_ok = safe.get("status") == "ok" and cpu is not None and memory is not None
        healthy_states = {HealthState.HEALTHY}
        bad_states = {HealthState.FAILED, HealthState.DEGRADED, HealthState.UNAVAILABLE}
        healthy = sum(reports.get(s.service_id) in healthy_states for s in service_records)
        degraded = sum(reports.get(s.service_id) in bad_states for s in service_records)
        unknown = len(service_records) - healthy - degraded
        available = sum(
            c.available and c.healthy and c.state in {CapabilityState.ACTIVE, CapabilityState.AVAILABLE}
            for c in capabilities
        )
        provider_healthy = sum(p.available and p.healthy for p in providers)
        # Only two fixed advisory alert types are projected. Provider-returned
        # arbitrary codes/strings are never allowed to reach the HTTP response.
        allowed_alerts = {"cpu_pressure", "memory_pressure"}
        raw_alerts = safe.get("alerts")
        alert_codes = tuple(sorted({
            item["code"] for item in raw_alerts
            if isinstance(item, dict)
            and type(item.get("code")) is str
            and item["code"] in allowed_alerts
        })) if isinstance(raw_alerts, list) and len(raw_alerts) <= 128 else ()
        status = (
            "unavailable" if not telemetry_ok
            else "degraded" if degraded or unknown or provider_healthy < len(providers)
            else "ok"
        )
        return RedactedLiveStatus(
            status=status, sampled_at=sampled_at,
            services_total=len(service_records),
            services_healthy=healthy,
            services_degraded=degraded,
            services_unknown=unknown,
            capabilities_total=len(capabilities),
            capabilities_available=available,
            providers_total=len(providers),
            providers_healthy=provider_healthy,
            cpu_percent=cpu if telemetry_ok else None,
            memory_percent=memory if telemetry_ok else None,
            alert_codes=alert_codes,
        )


live_status_router = APIRouter(tags=["safe-live-status"])


@live_status_router.get("/api/runtime/live-status")
def read_safe_live_status(
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    """Protected read-only route; never expose raw Kernel diagnostics or secrets."""
    service = getattr(request.app.state, "safe_live_status", None)
    if not isinstance(service, SafeLiveStatus):
        raise HTTPException(status_code=503, detail="Safe live status is not configured")
    try:
        return service.snapshot().to_dict()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Safe live status unavailable") from exc
