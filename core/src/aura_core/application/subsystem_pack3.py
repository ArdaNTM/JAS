"""Pack 3: local MQTT robot/sensor boundary and approved physical scenarios.

Deliberately no startup registration or self-granted policy. Owner must explicitly
register the provider's exact tools in existing registries, provision a local
authenticated broker and approve EACH physical call in MCPGateway. Publish
acceptance is not evidence that hardware moved; sensor attestations are separate.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import re
import socket
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
_TOPIC = re.compile(r"aura/(?:robots|sensors)/[A-Za-z0-9_-]{1,64}/[A-Za-z0-9_-]{1,64}\Z")


def _name(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid identifier")
    return value


def _mqtt_utf8(value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > 65535:
        raise ValueError("MQTT string too long")
    return struct.pack("!H", len(data)) + data


def _mqtt_packet(header: int, payload: bytes) -> bytes:
    length, encoded = len(payload), bytearray()
    if length > 64_000:
        raise ValueError("MQTT packet too large")
    while True:
        digit = length % 128
        length //= 128
        encoded.append(digit | (0x80 if length else 0))
        if not length:
            break
    return bytes([header]) + encoded + payload


def _read_exact(conn: socket.socket, n: int) -> bytes:
    result = bytearray()
    while len(result) < n:
        block = conn.recv(n - len(result))
        if not block:
            raise ConnectionError("MQTT connection closed")
        result.extend(block)
    return bytes(result)


def _read_packet(conn: socket.socket) -> tuple[int, bytes]:
    first = _read_exact(conn, 1)[0]
    value, mult = 0, 1
    for _ in range(4):
        digit = _read_exact(conn, 1)[0]
        value += (digit & 127) * mult
        if value > 64_000:
            raise ValueError("oversized MQTT response")
        if not digit & 128:
            return first, _read_exact(conn, value)
        mult *= 128
    raise ValueError("invalid MQTT remaining length")


class LocalMQTT:
    """Real dependency-free MQTT 3.1.1 QoS-0 client, scoped to local broker."""

    def __init__(self, *, port: int, username: str, password: str, client_id: str,
                 timeout: float = 3.0) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid MQTT port")
        if not isinstance(username, str) or not username or not isinstance(password, str) or len(password) < 16:
            raise ValueError("broker must require provisioned credentials")
        self.port, self.username, self.password = port, username, password
        self.client_id = _name(client_id)
        if not 0.1 <= timeout <= 5.0:
            raise ValueError("invalid MQTT timeout")
        self.timeout = timeout

    def _connect(self):
        # Only loopback broker, never a remote network route / user URL.
        connection = socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout)
        connection.settimeout(self.timeout)
        payload = (_mqtt_utf8(self.client_id) + _mqtt_utf8(self.username) +
                   _mqtt_utf8(self.password))
        connect = _mqtt_utf8("MQTT") + bytes([4, 0xC2, 0, 30]) + payload
        try:
            connection.sendall(_mqtt_packet(0x10, connect))
            kind, body = _read_packet(connection)
            if kind != 0x20 or body != b"\x00\x00":
                raise PermissionError("local MQTT broker rejected authentication")
            return connection
        except Exception:
            connection.close()
            raise

    def publish(self, topic: str, message: Mapping[str, Any]) -> None:
        if not isinstance(topic, str) or _TOPIC.fullmatch(topic) is None:
            raise ValueError("MQTT topic not allowed")
        data = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(data) > 4096:
            raise ValueError("MQTT payload too large")
        connection = self._connect()
        try:
            connection.sendall(_mqtt_packet(0x30, _mqtt_utf8(topic) + data))
        finally:
            connection.close()

    def receive(self, topic: str) -> dict[str, Any]:
        if not isinstance(topic, str) or _TOPIC.fullmatch(topic) is None:
            raise ValueError("MQTT topic not allowed")
        connection = self._connect()
        try:
            connection.sendall(_mqtt_packet(0x82, b"\x00\x01" + _mqtt_utf8(topic) + b"\x00"))
            kind, body = _read_packet(connection)
            if kind != 0x90 or body != b"\x00\x01\x00":
                raise ConnectionError("MQTT subscription rejected")
            kind, body = _read_packet(connection)
            if kind != 0x30 or len(body) < 3:
                raise ConnectionError("expected QoS-0 MQTT sensor publication")
            size = int.from_bytes(body[:2], "big")
            if len(body) < 2 + size or body[2:2+size].decode() != topic:
                raise PermissionError("unexpected sensor topic")
            message = json.loads(body[2+size:])
            if not isinstance(message, dict):
                raise ValueError("sensor payload must be a JSON object")
            return message
        finally:
            connection.close()


@dataclass(frozen=True)
class DeviceBinding:
    device_id: str
    command_topic: str
    sensor_topic: str
    commands: tuple[str, ...]
    sensor_key: bytes

    def __post_init__(self) -> None:
        _name(self.device_id)
        if not _TOPIC.fullmatch(self.command_topic) or not _TOPIC.fullmatch(self.sensor_topic):
            raise ValueError("invalid broker topic")
        if self.command_topic == self.sensor_topic or not self.command_topic.startswith(f"aura/robots/{self.device_id}/"):
            raise ValueError("command topic must be device scoped")
        if not self.sensor_topic.startswith(f"aura/sensors/{self.device_id}/"):
            raise ValueError("sensor topic must be device scoped")
        if not self.commands or len(self.commands) > 12 or len(set(self.commands)) != len(self.commands):
            raise ValueError("invalid command allowlist")
        for item in self.commands:
            _name(item)
        if type(self.sensor_key) is not bytes or len(self.sensor_key) < 32:
            raise ValueError("missing strong provisioned sensor key")


class PhysicalDeviceMCP:
    """Deny-by-default MCP provider with two independent explicit capabilities."""

    provider_id = "aura.local-physical-mqtt"
    requires_approval = True

    def __init__(self, *, transport: LocalMQTT, binding: DeviceBinding,
                 nonce_db: str | Path) -> None:
        self.transport, self.binding = transport, binding
        self.nonce_db = Path(nonce_db)
        if not self.nonce_db.parent.is_dir():
            raise ValueError("sensor sequence database parent missing")
        with sqlite3.connect(self.nonce_db) as db:
            db.execute("CREATE TABLE IF NOT EXISTS sensor_seq(device_id TEXT PRIMARY KEY, seq INTEGER NOT NULL)")

    async def list_tools(self):
        return (
            MCPTool("physical_actuate", "Submit approved command to provisioned local robot; not proof of motion",
                    {"type":"object","properties":{
                        "device_id":{"type":"string","maxLength":80},
                        "command":{"type":"string","maxLength":80},
                        "value":{"type":"number"},
                        "request_id":{"type":"string","maxLength":80}},
                     "required":["device_id","command","value","request_id"],"additionalProperties":False}),
            MCPTool("physical_sensor", "Read one HMAC-attested local sensor observation",
                    {"type":"object","properties":{"device_id":{"type":"string","maxLength":80}},
                     "required":["device_id"],"additionalProperties":False}),
        )

    def _authorize(self, name: str) -> None:
        grant = current_dispatch()
        capability = "PhysicalActuation" if name == "physical_actuate" else "PhysicalSensor"
        if (grant is None or grant.capability_id != capability or grant.tool_name != name
                or not grant.approval_consumed or grant.risk_level not in {"high", "critical"}
                or not grant.principal_id):
            raise PermissionError("physical device requires consumed scoped MCP Gateway approval")
        if name == "physical_actuate" and grant.risk_level != "critical":
            raise PermissionError("physical actuation requires critical risk policy")

    async def call_tool(self, name, arguments=None):
        if name not in {"physical_actuate", "physical_sensor"}:
            raise PermissionError("unregistered physical tool")
        self._authorize(name)
        args = arguments if isinstance(arguments, dict) else {}
        if args.get("device_id") != self.binding.device_id:
            raise PermissionError("physical device identity mismatch")
        if name == "physical_actuate":
            if set(args) != {"device_id", "command", "value", "request_id"}:
                raise ValueError("invalid command envelope")
            command = args["command"]
            if not isinstance(command, str) or command not in self.binding.commands:
                raise PermissionError("command is not provisioned")
            value = args["value"]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1.0:
                raise ValueError("normalized actuator value exceeds safe policy bounds")
            request_id = _name(args["request_id"])
            await asyncio.to_thread(self.transport.publish, self.binding.command_topic, {
                "device_id": self.binding.device_id, "command": command,
                "value": value, "request_id": request_id,
            })
            return {"device_id": self.binding.device_id, "status": "submitted_unverified", "request_id": request_id}

        if set(args) != {"device_id"}:
            raise ValueError("invalid sensor envelope")
        observation = await asyncio.to_thread(self.transport.receive, self.binding.sensor_topic)
        if set(observation) != {"device_id", "metric", "value", "sequence", "timestamp", "signature"}:
            raise PermissionError("invalid signed sensor observation")
        if observation["device_id"] != self.binding.device_id:
            raise PermissionError("sensor identity mismatch")
        value, seq, stamp = observation["value"], observation["sequence"], observation["timestamp"]
        if (type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e9 or
                type(seq) is not int or seq < 1 or type(stamp) is not int or
                abs(int(time.time()) - stamp) > 30 or not isinstance(observation["metric"], str) or
                _ID.fullmatch(observation["metric"]) is None):
            raise PermissionError("stale or malformed sensor evidence")
        signed = {k: v for k, v in observation.items() if k != "signature"}
        digest = hmac.new(self.binding.sensor_key,
                          json.dumps(signed, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        if (not isinstance(observation["signature"], str) or
                not hmac.compare_digest(digest, observation["signature"])):
            raise PermissionError("sensor signature rejected")
        with sqlite3.connect(self.nonce_db, timeout=5, isolation_level=None) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "INSERT INTO sensor_seq(device_id,seq) VALUES(?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET seq=excluded.seq WHERE excluded.seq>sensor_seq.seq",
                (self.binding.device_id, seq),
            ).rowcount
            db.execute("COMMIT")
        if changed != 1:
            raise PermissionError("replayed sensor sequence")
        return {"device_id": self.binding.device_id, "metric": signed["metric"],
                "value": value, "sequence": seq, "timestamp": stamp, "attested": True}


@dataclass(frozen=True)
class PhysicalStep:
    step_id: str
    device_id: str
    command: str
    value: float
    action_approval_id: str
    sensor_approval_id: str
    metric: str
    expected_min: float
    expected_max: float
    min_sequence: int = 0


class GovernedPhysicalScenario:
    """Executes an explicitly preapproved sequence, verifying fresh sensor evidence.

    A missing/denied step aborts; approvals are never generated by the scenario.
    """

    def __init__(self, *, gateway: Any, principal_id: str,
                 resource_scope: str = "local_default", event_bus: Any = None):
        self.gateway, self.principal_id, self.scope = gateway, _name(principal_id), _name(resource_scope)
        self.event_bus = event_bus

    async def run(self, steps: tuple[PhysicalStep, ...]) -> tuple[dict[str, Any], ...]:
        from aura_core.kernel.events import KernelEvent

        if not isinstance(steps, tuple) or not 1 <= len(steps) <= 8:
            raise ValueError("scenario length must be 1..8")
        if len({s.step_id for s in steps}) != len(steps):
            raise ValueError("duplicate scenario step")
        results = []
        for step in steps:
            for item in (step.step_id, step.device_id, step.command,
                         step.action_approval_id, step.sensor_approval_id, step.metric):
                _name(item)
            if (type(step.value) not in (int, float) or not math.isfinite(step.value)
                    or abs(step.value) > 1 or type(step.min_sequence) is not int
                    or step.min_sequence < 0 or not all(math.isfinite(x) for x in
                       (step.expected_min, step.expected_max)) or
                    step.expected_min > step.expected_max):
                raise ValueError("invalid step bounds")
            act = await self.gateway.invoke(MCPGatewayRequest(
                request_id="act-"+step.step_id, principal_id=self.principal_id,
                capability_id="PhysicalActuation", operation_id="PhysicalActuation",
                resource_scope=self.scope, risk_level=RiskLevel.CRITICAL,
                tool_name="physical_actuate", approval_id=step.action_approval_id,
                arguments={"device_id":step.device_id,"command":step.command,
                           "value":step.value,"request_id":step.step_id},
            ))
            if act.decision is not AuthorizationDecision.ALLOW or not isinstance(act.result, dict) or act.result.get("status") != "submitted_unverified":
                raise PermissionError("physical action was not accepted by authorized Gateway")
            sensor = await self.gateway.invoke(MCPGatewayRequest(
                request_id="sensor-"+step.step_id, principal_id=self.principal_id,
                capability_id="PhysicalSensor", operation_id="PhysicalSensor",
                resource_scope=self.scope, risk_level=RiskLevel.HIGH,
                tool_name="physical_sensor", approval_id=step.sensor_approval_id,
                arguments={"device_id":step.device_id},
            ))
            reading = sensor.result
            if (sensor.decision is not AuthorizationDecision.ALLOW or not isinstance(reading, dict)
                    or reading.get("attested") is not True or reading.get("device_id") != step.device_id
                    or reading.get("metric") != step.metric or type(reading.get("sequence")) is not int
                    or reading["sequence"] <= step.min_sequence or
                    type(reading.get("value")) not in (int, float) or
                    not math.isfinite(reading["value"]) or
                    not step.expected_min <= reading["value"] <= step.expected_max):
                raise PermissionError("physical action lacks independently attested sensor evidence")
            results.append({"step_id": step.step_id, "state":"sensor_observed",
                            "sequence":reading["sequence"]})
            if self.event_bus is not None:
                self.event_bus.publish(KernelEvent(
                    event_type="PhysicalSensorObserved", source_component="aura.pack3",
                    payload={"step_id":step.step_id,"device_id":step.device_id,
                             "sequence":reading["sequence"]},
                ))
        return tuple(results)
