"""Bounded read-only Home Assistant-style entity state through MCP Gateway.

This stacked component depends on the authorized inventory from #85. Device
presence in an inventory is only a precondition, never permission: every state
read must independently pass the existing PermissionEngine/Gateway.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from aura_core.application.governed_home_inventory import HomeInventory, HomeDeviceHint
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest, MCPGatewayResponse

_DEVICE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_PROVIDER_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_ALLOWED_STATES = frozenset({"on", "off", "active", "idle", "unavailable", "unknown"})
_SAFE_TYPES = frozenset({"light", "switch", "sensor", "climate", "other"})


class HomeStateDenied(PermissionError):
    """Explicit per-device read policy was not granted by Core."""


class HomeStateInvalid(ValueError):
    """MCP provider state is malformed or cannot be trusted for display."""


@dataclass(frozen=True, slots=True)
class HomeStateEvidence:
    device_id: str
    state: str
    sampled_at: str
    provider_id: str
    trust: str = "UNTRUSTED_STATE_METADATA"
    read_only: bool = True


def _identity(value: str) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("Invalid authenticated Home Assistant principal")
    return value


def _validated_inventory(value: HomeInventory) -> HomeInventory:
    if (
        not isinstance(value, HomeInventory) or value.read_only is not True
        or value.scope != "home/devices/read-only"
        or not isinstance(value.provider_id, str)
        or not _PROVIDER_ID.fullmatch(value.provider_id)
        or not isinstance(value.devices, tuple)
        or len(value.devices) > 64
    ):
        raise ValueError("Expected bounded authorized read-only device inventory")
    seen: set[str] = set()
    for device in value.devices:
        if (
            not isinstance(device, HomeDeviceHint)
            or not isinstance(device.device_id, str)
            or not _DEVICE_ID.fullmatch(device.device_id)
            or device.device_id in seen
            or device.category not in _SAFE_TYPES
            or type(device.available) is not bool
            or device.trust != "UNTRUSTED_DEVICE_METADATA"
        ):
            raise ValueError("Invalid home inventory evidence")
        seen.add(device.device_id)
    return value


def _parse(response: object, device_id: str, expected_provider: str) -> HomeStateEvidence:
    if not isinstance(response, MCPGatewayResponse):
        raise HomeStateInvalid("Home state response is not from MCP Gateway")
    if response.decision is not AuthorizationDecision.ALLOW:
        raise HomeStateDenied("Explicit entity state read permission required")
    if response.provider_id != expected_provider:
        raise HomeStateInvalid("Entity state provider does not match inventory provider")
    result = response.result
    if (
        result is None or getattr(result, "is_error", False) is True
        or getattr(result, "isError", False) is True
    ):
        raise HomeStateInvalid("Entity state provider failed")
    if isinstance(result, dict):
        if result.get("isError") is True or result.get("status") == "failed":
            raise HomeStateInvalid("Entity state provider failed")
        payload = result.get("structuredContent", result.get("structured_content", result))
    else:
        payload = getattr(result, "structured_content", None)
        if payload is None:
            payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, dict) or payload.get("device_id") != device_id:
        raise HomeStateInvalid("Mismatched entity state metadata")
    state = payload.get("state")
    if not isinstance(state, str) or state not in _ALLOWED_STATES:
        raise HomeStateInvalid("Unsupported or unsafe entity state")
    timestamp = payload.get("sampled_at")
    if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 64:
        raise HomeStateInvalid("Missing time-bound entity state metadata")
    try:
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HomeStateInvalid("Invalid state observation timestamp") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise HomeStateInvalid("State timestamp must have timezone")
    return HomeStateEvidence(
        device_id=device_id, state=state, sampled_at=observed.isoformat(),
        provider_id=expected_provider,
    )


class GovernedHomeAssistantStateReader:
    """No direct Home Assistant API/network, no physical action methods."""

    def __init__(
        self,
        gateway: MCPGateway,
        *,
        authenticated_principal_id: str,
        authorized_inventory: HomeInventory,
    ) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCPGateway required")
        self._gateway = gateway
        self._principal_id = _identity(authenticated_principal_id)
        self._inventory = _validated_inventory(authorized_inventory)

    async def read(self, *, device_id: str) -> HomeStateEvidence:
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("Invalid entity identifier")
        known = next((d for d in self._inventory.devices if d.device_id == device_id), None)
        if known is None or known.available is not True:
            raise HomeStateDenied("Device is unavailable or outside authorized inventory")
        request = MCPGatewayRequest(
            request_id="home-state:" + str(uuid4()),
            principal_id=self._principal_id,
            capability_id="home.entity.state.read",
            operation_id="home.entity.state.read",
            resource_scope=f"home/entities/{device_id}/read-only",
            risk_level=RiskLevel.MEDIUM,
            tool_name="get_entity_state",
            arguments={"device_id": device_id},
            task_id="home:read-entity-state",
        )
        try:
            response = await self._gateway.invoke(request)
        except Exception as exc:
            raise HomeStateInvalid("Home entity state Gateway unavailable") from exc
        return _parse(response, device_id, self._inventory.provider_id)
