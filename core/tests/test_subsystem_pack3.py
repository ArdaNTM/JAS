import asyncio
import hashlib
import hmac
import json
import socketserver
import threading
import time
from types import SimpleNamespace

import pytest

from aura_core.application.subsystem_pack3 import (
    DeviceBinding, GovernedPhysicalScenario, LocalMQTT, PhysicalDeviceMCP,
    PhysicalStep, _mqtt_packet, _mqtt_utf8, _read_packet,
)
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


def binding():
    return DeviceBinding("arm1", "aura/robots/arm1/control", "aura/sensors/arm1/position",
                         ("halt", "setpoint"), b"s" * 32)


def signed_observation(*, sequence=1, value=0.25):
    observation = {"device_id":"arm1", "metric":"position", "value":value,
                   "sequence":sequence, "timestamp":int(time.time())}
    observation["signature"] = hmac.new(b"s" * 32,
        json.dumps(observation, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    return observation


class DeviceTransport:
    def __init__(self, observation=None):
        self.sent = []
        self.observation = observation or signed_observation()

    def publish(self, topic, message):
        self.sent.append((topic, message))

    def receive(self, topic):
        return self.observation


def grant(*, cap="PhysicalActuation", name="physical_actuate", approved=True, risk="critical"):
    return enter_dispatch(DispatchGrant(principal_id="owner", capability_id=cap, tool_name=name,
                                        approval_consumed=approved, risk_level=risk))


def test_physical_provider_default_denies_no_dispatch(tmp_path):
    transport = DeviceTransport()
    device = PhysicalDeviceMCP(transport=transport, binding=binding(), nonce_db=tmp_path / "seq.db")
    with pytest.raises(PermissionError, match="approval"):
        asyncio.run(device.call_tool("physical_actuate", {"device_id":"arm1","command":"halt",
                                                          "value":0,"request_id":"stop1"}))
    assert transport.sent == []


def test_physical_provider_requires_critical_separate_capability(tmp_path):
    transport = DeviceTransport()
    device = PhysicalDeviceMCP(transport=transport, binding=binding(), nonce_db=tmp_path / "seq.db")
    for settings in [{"approved":False}, {"risk":"high"}, {"cap":"PhysicalSensor"}]:
        token = grant(**settings)
        try:
            with pytest.raises(PermissionError):
                asyncio.run(device.call_tool("physical_actuate", {"device_id":"arm1",
                    "command":"halt","value":0,"request_id":"stop1"}))
        finally:
            leave_dispatch(token)
    assert transport.sent == []


def test_physical_actuation_is_submitted_not_verified(tmp_path):
    transport = DeviceTransport()
    device = PhysicalDeviceMCP(transport=transport,binding=binding(),nonce_db=tmp_path/"seq.db")
    token = grant()
    try:
        result = asyncio.run(device.call_tool("physical_actuate", {"device_id":"arm1",
            "command":"setpoint","value":0.3,"request_id":"move1"}))
        assert result["status"] == "submitted_unverified"
        assert transport.sent[0][0] == binding().command_topic
        with pytest.raises(PermissionError):
            asyncio.run(device.call_tool("physical_actuate", {"device_id":"arm1",
                "command":"wipe","value":0.3,"request_id":"move2"}))
        with pytest.raises(ValueError):
            asyncio.run(device.call_tool("physical_actuate", {"device_id":"arm1",
                "command":"setpoint","value":2.0,"request_id":"move2"}))
    finally:
        leave_dispatch(token)
    assert len(transport.sent) == 1


def test_sensor_signature_sequence_is_persistent(tmp_path):
    transport = DeviceTransport()
    provider = PhysicalDeviceMCP(transport=transport,binding=binding(),nonce_db=tmp_path/"seq.db")
    token = grant(cap="PhysicalSensor",name="physical_sensor",risk="high")
    try:
        response = asyncio.run(provider.call_tool("physical_sensor", {"device_id":"arm1"}))
        assert response["attested"] is True
        with pytest.raises(PermissionError,match="replayed"):
            asyncio.run(PhysicalDeviceMCP(transport=transport,binding=binding(),
                nonce_db=tmp_path/"seq.db").call_tool("physical_sensor", {"device_id":"arm1"}))
        transport.observation = signed_observation(sequence=2)
        assert asyncio.run(provider.call_tool("physical_sensor", {"device_id":"arm1"}))["sequence"] == 2
    finally:
        leave_dispatch(token)


def test_sensor_tamper_and_stale_denied(tmp_path):
    transport = DeviceTransport()
    provider = PhysicalDeviceMCP(transport=transport,binding=binding(),nonce_db=tmp_path/"seq.db")
    token = grant(cap="PhysicalSensor",name="physical_sensor",risk="high")
    try:
        transport.observation = signed_observation()
        transport.observation["value"] = -999
        with pytest.raises(PermissionError,match="signature"):
            asyncio.run(provider.call_tool("physical_sensor", {"device_id":"arm1"}))
        transport.observation = signed_observation()
        transport.observation["timestamp"] = 0
        with pytest.raises(PermissionError,match="stale"):
            asyncio.run(provider.call_tool("physical_sensor", {"device_id":"arm1"}))
    finally:
        leave_dispatch(token)


def test_local_mqtt_real_loopback_protocol_publish_and_subscribe():
    observed = []
    sensor = signed_observation()
    topic = "aura/sensors/arm1/position"

    class Broker(socketserver.BaseRequestHandler):
        def handle(self):
            kind, content = _read_packet(self.request)
            assert kind == 0x10 and b"MQTT" in content
            self.request.sendall(_mqtt_packet(0x20,b"\x00\x00"))
            kind, content = _read_packet(self.request)
            if kind == 0x30:
                observed.append(content)
            elif kind == 0x82:
                assert content.startswith(b"\x00\x01")
                self.request.sendall(_mqtt_packet(0x90,b"\x00\x01\x00"))
                self.request.sendall(_mqtt_packet(0x30,_mqtt_utf8(topic) +
                    json.dumps(sensor).encode()))
            else:
                raise AssertionError("unexpected MQTT type")

    server = socketserver.ThreadingTCPServer(("127.0.0.1",0),Broker)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        broker = LocalMQTT(port=server.server_address[1],username="aura",
                           password="local-secret-password",client_id="client-1")
        broker.publish("aura/robots/arm1/control",{"command":"halt"})
        assert broker.receive(topic)["sequence"] == sensor["sequence"]
        assert b"halt" in observed[0]
        with pytest.raises(ValueError):
            broker.publish("other/host",{"a":1})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class Gateway:
    def __init__(self, *, denied=False, attested=True):
        self.calls=[]
        self.denied=denied
        self.attested=attested
    async def invoke(self, request):
        self.calls.append(request)
        if self.denied and len(self.calls)==2:
            return SimpleNamespace(decision=AuthorizationDecision.DENY,result=None)
        if request.tool_name=="physical_actuate":
            payload={"status":"submitted_unverified"}
        else:
            payload={"device_id":"arm1","metric":"position","value":0.4,
                     "sequence":2,"attested":self.attested}
        return SimpleNamespace(decision=AuthorizationDecision.ALLOW,result=payload)


def step():
    return PhysicalStep("step1","arm1","setpoint",0.4,"action-approval","sensor-approval",
                        "position",0.3,0.5,1)


def test_scenario_calls_gateway_twice_with_distinct_approvals():
    gateway = Gateway()
    result = asyncio.run(GovernedPhysicalScenario(gateway=gateway,principal_id="owner")
                         .run((step(),)))
    assert result[0]["state"]=="sensor_observed"
    assert len(gateway.calls)==2
    assert gateway.calls[0].capability_id=="PhysicalActuation"
    assert gateway.calls[1].capability_id=="PhysicalSensor"
    assert gateway.calls[0].approval_id != gateway.calls[1].approval_id


def test_scenario_denied_sensor_cannot_be_claimed_verified():
    for opts in ({"denied":True},{"attested":False}):
        gateway=Gateway(**opts)
        with pytest.raises(PermissionError,match="attested"):
            asyncio.run(GovernedPhysicalScenario(gateway=gateway,principal_id="owner")
                        .run((step(),)))


def test_scenario_fails_on_bad_range_before_execution():
    gateway=Gateway()
    invalid=PhysicalStep("x","arm1","setpoint",0.5,"action","sensor",
                         "position",2,1)
    with pytest.raises(ValueError,match="bounds"):
        asyncio.run(GovernedPhysicalScenario(gateway=gateway,principal_id="owner")
                    .run((invalid,)))
    assert gateway.calls==[]


def test_bindings_restrict_topic_and_keys():
    with pytest.raises(ValueError):
        DeviceBinding("arm1","other/dev","aura/sensors/arm1/position",("halt",),b"s"*32)
    with pytest.raises(ValueError):
        DeviceBinding("arm1","aura/robots/arm1/control","aura/sensors/arm1/position",
                      ("halt",),b"weak")
