"""Deny-only, externally keyed integrity guard for existing AURA Core registries.

This is tamper evidence, NOT an immutable kernel or a new authorization engine.
It snapshots Service/Capability/Provider registry definitions and the current
PermissionEngine policy digest. Only MCPGateway can authorize/dispatch tools.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, PermissionEngine
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest, MCPGatewayResponse
from aura_core.mcp.provider import ProviderRegistry

_SCHEMA = "aura.core.registry-integrity.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_ENTRIES = 10_000


@dataclass(frozen=True, slots=True)
class IntegrityReceipt:
    """Opaque integrity proof: no policies, principals or secret values exposed."""

    schema: str
    scope_digest: str
    registry_digest: str
    mac: str


def _secret(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("verifier key must be at least 32 random bytes")
    return value


def _scope(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("registry attestation scope must be bounded text")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


class CoreRegistryState:
    """Read current authoritative objects, never duplicate or edit their state."""

    def __init__(
        self,
        services: ServiceRegistry,
        providers: ProviderRegistry,
        capabilities: CapabilityRegistry,
        permissions: PermissionEngine,
    ) -> None:
        if not isinstance(services, ServiceRegistry):
            raise TypeError("existing ServiceRegistry required")
        if not isinstance(providers, ProviderRegistry):
            raise TypeError("existing ProviderRegistry required")
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("existing CapabilityRegistry required")
        if not isinstance(permissions, PermissionEngine):
            raise TypeError("existing PermissionEngine required")
        self.services = services
        self.providers = providers
        self.capabilities = capabilities
        self.permissions = permissions

    def digest(self) -> str:
        services = self.services.records()
        providers = self.providers.records()
        capabilities = self.capabilities.records()
        if sum(map(len, (services, providers, capabilities))) > _MAX_ENTRIES:
            raise ValueError("Core registry inventory exceeds integrity limit")
        data: dict[str, Any] = {
            "schema": _SCHEMA,
            "permission_digest": self.permissions.integrity_digest(),
            "services": [
                {
                    "id": r.definition.service_id,
                    "version": r.definition.version,
                    "provider": r.definition.provider,
                    "category": r.definition.category.value,
                    "state": r.state.value,
                    "capabilities": sorted(r.definition.capabilities),
                    "dependencies": sorted(r.definition.dependencies),
                }
                for r in services
            ],
            "providers": [
                {
                    "id": r.definition.provider_id,
                    "version": r.definition.version,
                    "service_id": r.definition.service_id,
                    "state": r.state.value,
                    "available": r.available,
                    "healthy": r.healthy,
                }
                for r in providers
            ],
            "capabilities": [
                {
                    "id": r.definition.capability_id,
                    "version": r.definition.version,
                    "provider_id": r.definition.provider_id,
                    "provider_type": r.definition.provider_type.value,
                    "category": r.definition.category.value,
                    "tool": r.definition.tool_name,
                    "risk": r.definition.risk_level,
                    "permissions": sorted(r.definition.required_permissions),
                    "dependencies": sorted(r.definition.dependencies),
                    "state": r.state.value,
                    "available": r.available,
                    "healthy": r.healthy,
                }
                for r in capabilities
            ],
        }
        serialized = _canonical(data)
        if len(serialized) > 2_000_000:
            raise ValueError("Core registry snapshot exceeds size budget")
        return hashlib.sha256(serialized).hexdigest()


def _scope_digest(key: bytes, scope: str) -> str:
    return hmac.new(key, b"aura-registry-scope-v1\x00" + scope.encode("utf-8"), hashlib.sha256).hexdigest()


def _mac(key: bytes, fields: dict[str, str]) -> str:
    return hmac.new(key, b"aura-registry-attestation-v1\x00" + _canonical(fields), hashlib.sha256).hexdigest()


def attest_core_registries(state: CoreRegistryState, *, key: bytes, scope: str) -> IntegrityReceipt:
    """Called by an external verifier that controls the key and retains the receipt."""
    secret, name = _secret(key), _scope(scope)
    if not isinstance(state, CoreRegistryState):
        raise TypeError("CoreRegistryState required")
    fields = {
        "schema": _SCHEMA,
        "scope_digest": _scope_digest(secret, name),
        "registry_digest": state.digest(),
    }
    return IntegrityReceipt(**fields, mac=_mac(secret, fields))


def verify_core_registries(
    state: CoreRegistryState, receipt: IntegrityReceipt, *,
    key: bytes, scope: str,
) -> bool:
    """Fail closed on any changed registry or local/enterprise policy digest."""
    secret, name = _secret(key), _scope(scope)
    if not isinstance(state, CoreRegistryState) or not isinstance(receipt, IntegrityReceipt):
        return False
    if receipt.schema != _SCHEMA or not all(
        isinstance(value, str) and _DIGEST.fullmatch(value)
        for value in (receipt.scope_digest, receipt.registry_digest, receipt.mac)
    ):
        return False
    if not hmac.compare_digest(receipt.scope_digest, _scope_digest(secret, name)):
        return False
    fields = {
        "schema": receipt.schema,
        "scope_digest": receipt.scope_digest,
        "registry_digest": receipt.registry_digest,
    }
    if not hmac.compare_digest(receipt.mac, _mac(secret, fields)):
        return False
    try:
        return hmac.compare_digest(receipt.registry_digest, state.digest())
    except Exception:
        # Registry or policy snapshot unavailable: never dispatch on uncertainty.
        return False


class GuardedMCPGateway:
    """Opt-in deny-only wrapper; all allowed requests still use original Gateway.

    Production must ensure **every** execution entrypoint uses this wrapper and
    baseline+key are held independently. Neither requirement is supplied here.
    """

    def __init__(
        self,
        gateway: MCPGateway,
        state: CoreRegistryState,
        receipt: IntegrityReceipt,
        *,
        key: bytes,
        scope: str,
        event_bus: EventBus | None = None,
    ) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("existing MCPGateway required")
        if not isinstance(state, CoreRegistryState) or not isinstance(receipt, IntegrityReceipt):
            raise TypeError("registry state and integrity receipt required")
        self._key = _secret(key)
        self._scope = _scope(scope)
        self._gateway = gateway
        self._state = state
        self._receipt = receipt
        self._event_bus = event_bus

    async def invoke(self, request: MCPGatewayRequest) -> MCPGatewayResponse:
        if not isinstance(request, MCPGatewayRequest):
            raise TypeError("MCPGatewayRequest required")
        if not verify_core_registries(
            self._state, self._receipt, key=self._key, scope=self._scope,
        ):
            if self._event_bus is not None:
                self._event_bus.publish(KernelEvent(
                    event_type="CoreIntegrityRejected",
                    source_component="aura.enterprise.core_integrity",
                    correlation_id=request.request_id,
                    payload={
                        "request_id": request.request_id,
                        "capability_id": request.capability_id,
                        "reason_code": "registry_or_policy_drift",
                    },
                ))
            return MCPGatewayResponse(
                decision=AuthorizationDecision.DENY, result=None,
                provider_id=None, tool_name=request.tool_name,
                reason="Core registry or policy integrity is not verified",
            )
        # Never turn a DENY/REQUIRE_APPROVAL into ALLOW. Gateway alone evaluates
        # policies, one-time approvals, schemas, circuit breakers and dispatch.
        return await self._gateway.invoke(request)
