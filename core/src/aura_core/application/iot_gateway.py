"""Smart switch profiles on the existing local MQTT and signed sensor boundary."""
from __future__ import annotations

import asyncio
import json
import hashlib
import os
from pathlib import Path

from aura_core.application.subsystem_pack3 import DeviceBinding, LocalMQTT, PhysicalDeviceMCP, _ID
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.dispatch_context import current_dispatch

IOT_EVENT = "JarvisIoTStatus"
IOT_SOURCE = "aura.jarvis.iot"


class SmartDeviceMCP(PhysicalDeviceMCP):
    """One explicitly provisioned switch per provider/capability identity."""

    def __init__(self, *, transport, binding, nonce_db, event_bus: EventBus, face_gate=None):
        if set(binding.commands) != {"on", "off"}:
            raise ValueError("Smart switch command profile must contain only on/off")
        super().__init__(transport=transport, binding=binding, nonce_db=nonce_db)
        self.provider_id = "aura.iot." + binding.device_id
        self.actuate_capability = "iot." + binding.device_id + ".actuate"
        self.status_capability = "iot." + binding.device_id + ".status"
        self.scope = "iot/device/" + binding.device_id
        self._events = event_bus
        self._face_gate = face_gate
        self._lock = asyncio.Lock()

    def _authorize(self, name: str) -> None:
        grant = current_dispatch()
        actuate = name == "physical_actuate"
        capability = self.actuate_capability if actuate else self.status_capability
        if (grant is None or grant.capability_id != capability or grant.tool_name != name
                or not grant.approval_consumed or grant.principal_id != "local_owner"
                or grant.risk_level != ("critical" if actuate else "high")):
            raise PermissionError("Consumed device-bound MCP Gateway approval required")
        if actuate and self._face_gate is not None and self._face_gate.restricted(grant.principal_id):
            raise PermissionError("Optional local session restriction blocks device actuation")

    async def call_tool(self, name, arguments=None):
        self._authorize(name)
        args = arguments if isinstance(arguments, dict) else {}
        if name == "physical_actuate":
            command, value = args.get("command"), args.get("value")
            if command not in {"on", "off"} or type(value) not in {int, float} or value != (1 if command == "on" else 0):
                raise ValueError("Smart switch requires exact on/off command value")
        async with self._lock:
            result = await super().call_tool(name, arguments)
        if name == "physical_sensor":
            if result.get("metric") != "power" or result.get("value") not in {0, 1}:
                raise PermissionError("Invalid signed switch state")
            result["state"] = "on" if result["value"] == 1 else "off"
        grant = current_dispatch()
        self._events.publish(KernelEvent(
            event_type=IOT_EVENT, source_component=IOT_SOURCE,
            payload={
                "principal_id": grant.principal_id, "device_id": self.binding.device_id,
                "action": args.get("command", "status"),
                "status": result.get("status", "attested"),
                "state": result.get("state"),
            },
        ))
        return result


def project_iot_event(event: dict, principal: str) -> dict | None:
    data = event.get("data")
    if (event.get("event") != IOT_EVENT or event.get("source") != IOT_SOURCE
            or not isinstance(data, dict) or data.get("principal_id") != principal):
        return None
    device = data.get("device_id")
    action, status, state = data.get("action"), data.get("status"), data.get("state")
    if (not isinstance(device, str) or not _ID.fullmatch(device)
            or not isinstance(action, str) or not isinstance(status, str)
            or (state is not None and not isinstance(state, str))
            or action not in {"on", "off", "status"}
            or status not in {"submitted_unverified", "attested"}
            or state not in {None, "on", "off"}):
        return None
    if not ((action == "status" and status == "attested" and state is not None)
            or (action in {"on", "off"} and status == "submitted_unverified" and state is None)):
        return None
    return {"event": IOT_EVENT, "data": {"device_id": device, "action": action,
                                        "status": status, "state": state}}


def load_smart_devices(*, event_bus: EventBus, face_gate=None) -> dict[str, SmartDeviceMCP]:
    """Only operator-configured loopback broker and exact allowlisted device IDs.

    LAN integration belongs to a separately configured authenticated MQTT bridge;
    no discovery, arbitrary broker URL, wildcard topic or remote shell is allowed.
    """
    raw = os.getenv("AURA_IOT_PROFILES_JSON", "")
    if not raw or len(raw) > 32_000:
        raise ValueError("Bounded explicit IoT profiles required")
    config = json.loads(raw)
    if not isinstance(config, list) or not 1 <= len(config) <= 16:
        raise ValueError("Expected 1..16 provisioned smart switches")
    nonce_db = Path(os.getenv("AURA_IOT_NONCE_DB", "")).expanduser()
    if not nonce_db.is_absolute() or not nonce_db.parent.is_dir():
        raise ValueError("Explicit local nonce database path required")
    # Keep persistent replay evidence outside executable checkout and symlinks.
    checkout = Path(__file__).resolve().parents[4]
    target = nonce_db.resolve()
    if target.is_relative_to(checkout) or any(
        p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
        for p in (nonce_db, *nonce_db.parents)
    ):
        raise ValueError("IoT replay database must be outside checkout and links")
    devices = {}
    for profile in config:
        if not isinstance(profile, dict) or set(profile) != {"device_id", "sensor_key_hex"}:
            raise ValueError("Invalid smart switch profile")
        identity = profile["device_id"]
        if not isinstance(identity, str) or not _ID.fullmatch(identity) or identity in devices:
            raise ValueError("Invalid or duplicate device ID")
        transport = LocalMQTT(
            port=int(os.getenv("AURA_IOT_MQTT_PORT", "1883")),
            username=os.getenv("AURA_IOT_MQTT_USERNAME", ""),
            password=os.getenv("AURA_IOT_MQTT_PASSWORD", ""),
            client_id="aura-iot-" + hashlib.sha256(identity.encode()).hexdigest()[:12],
        )
        # Topic names remain the existing signed physical-device namespaces.
        binding = DeviceBinding(identity, f"aura/robots/{identity}/control",
                                f"aura/sensors/{identity}/power", ("on", "off"),
                                bytes.fromhex(profile["sensor_key_hex"]))
        devices[identity] = SmartDeviceMCP(transport=transport, binding=binding,
                                           nonce_db=nonce_db, event_bus=event_bus, face_gate=face_gate)
    return devices
