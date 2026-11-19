"""Provider-agnostic read-only home device inventory via existing MCP Gateway.

Never scans networks, discovers hosts, controls a device, requests credentials,
registers a capability or grants Owner authority. A trusted Core caller binds an
already-authenticated principal; every inventory read requires a separate
PermissionEngine ALLOW via the registered MCP Gateway.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest, MCPGatewayResponse

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_PROVIDER_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_SAFE_CATEGORIES = frozenset({"light", "switch", "sensor", "climate", "other"})


class HomeInventoryDenied(PermissionError):
    """The authoritative Gateway did not grant a scoped discovery read."""


class HomeInventoryInvalid(ValueError):
    """The registered provider returned unsafe or malformed inventory metadata."""


@dataclass(frozen=True, slots=True)
class HomeDeviceHint:
    device_id: str
    category: str
    available: bool
    trust: str = "UNTRUSTED_DEVICE_METADATA"


@dataclass(frozen=True, slots=True)
class HomeInventory:
    devices: tuple[HomeDeviceHint, ...]
    provider_id: str
    scope: str = "home/devices/read-only"
    read_only: bool = True


def _principal(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value)
    ):
        raise ValueError("Invalid authenticated home inventory principal")
    return value


def _parse(response: object) -> HomeInventory:
    if not isinstance(response, MCPGatewayResponse):
        raise HomeInventoryInvalid("Invalid MCP Gateway inventory response")
    if response.decision is not AuthorizationDecision.ALLOW:
        raise HomeInventoryDenied("Explicit home inventory read permission required")
    result = response.result
    if (result is None or getattr(result, "is_error", False) is True
            or getattr(result, "isError", False) is True):
        raise HomeInventoryInvalid("Home inventory provider returned failure")
    if isinstance(result, dict):
        if result.get("isError") is True or result.get("status") == "failed":
            raise HomeInventoryInvalid("Home inventory provider returned failure")
        payload = result.get("structuredContent", result.get("structured_content", result))
    else:
        payload = getattr(result, "structured_content", None)
        if payload is None:
            payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, dict):
        raise HomeInventoryInvalid("Home inventory must be structured")
    # Errors may be inside MCP structured_content rather than the outer
    # SDK envelope. They are never a successful empty device inventory.
    if payload.get("status") == "failed" or payload.get("isError") is True:
        raise HomeInventoryInvalid("Home inventory provider returned failure")
    devices = payload.get("devices")
    if not isinstance(devices, list) or len(devices) > 64:
        raise HomeInventoryInvalid("Home inventory exceeds bounded size")
    provider_id = response.provider_id
    if not isinstance(provider_id, str) or not _PROVIDER_ID.fullmatch(provider_id):
        raise HomeInventoryInvalid("Missing registered provider identity")
    seen: set[str] = set()
    hints: list[HomeDeviceHint] = []
    for device in devices:
        if not isinstance(device, dict):
            raise HomeInventoryInvalid("Malformed device metadata")
        dev_id = device.get("device_id")
        category = device.get("category")
        available = device.get("available")
        if not isinstance(dev_id, str) or not _ID.fullmatch(dev_id):
            raise HomeInventoryInvalid("Invalid ephemeral device identifier")
        if dev_id in seen:
            raise HomeInventoryInvalid("Duplicate device identifier")
        if not isinstance(category, str) or category not in _SAFE_CATEGORIES:
            # Camera, lock and device-command metadata require a separately
            # reviewed higher-risk capability; not part of this read scope.
            raise HomeInventoryInvalid("Unsupported sensitive device category")
        if type(available) is not bool:
            raise HomeInventoryInvalid("Invalid availability indicator")
        seen.add(dev_id)
        hints.append(HomeDeviceHint(dev_id, category, available))
    hints.sort(key=lambda d: d.device_id)
    return HomeInventory(tuple(hints), provider_id=provider_id)


class GovernedHomeInventoryReader:
    """Read-only MCP facade; does not perform HA/HomeKit/device actions."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCPGateway required")
        self._gateway = gateway
        self._principal_id = _principal(authenticated_principal_id)

    async def discover(self) -> HomeInventory:
        request = MCPGatewayRequest(
            request_id="home-inventory:" + str(uuid4()),
            principal_id=self._principal_id,
            capability_id="home.device.discover",
            operation_id="home.device.discover",
            resource_scope="home/devices/read-only",
            risk_level=RiskLevel.MEDIUM,
            tool_name="list_devices",
            arguments={},
            task_id="home:readonly-discovery",
        )
        try:
            response = await self._gateway.invoke(request)
        except Exception as exc:
            raise HomeInventoryInvalid("Home inventory Gateway operation unavailable") from exc
        return _parse(response)
