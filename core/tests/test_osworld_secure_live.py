"""Guardrails for the actual OSWorld-V2.1 3.12/3.13 runtime boundary.

No Docker, KVM, Hugging Face token, physical machine, private Owner key or
real signed network receipt is required in CI; fake OS responses verify that
the privileged runner fails closed. Tests never claim physical isolation.
"""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld import network_audit
from aura_core.osworld.isolation import (
    BootIdentity, EXPECTED_PORTS, IMAGE, IsolationDenied, IsolationReceipt,
    NETWORK_NAME, REQUIRED_CHECKS, verify_receipt,
)
from aura_core.osworld.runtime_bridge import (
    ALLOWED_ENV, COMMIT, VMBridgeError, pinned_python,
)


def _script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("test_osworld_" + name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixture_receipt(now: int | None = None):
    now = int(time.time()) if now is None else now
    key = Ed25519PrivateKey.generate()
    boot = BootIdentity("a" * 64, "b" * 64, "c" * 64, IMAGE)
    ports = {str(i): f"127.0.0.1:{i + 20000}" for i in EXPECTED_PORTS}
    provisional = IsolationReceipt(
        "host_auditor", boot, now, now + 180, secrets.token_hex(16),
        {k: True for k in REQUIRED_CHECKS}, ports, "unsigned",
    )
    signed = IsolationReceipt(
        provisional.signer_id, boot, now, now + 180, provisional.nonce,
        provisional.checks, provisional.host_ports,
        base64.b64encode(key.sign(provisional.signing_payload())).decode("ascii"),
    )
    from cryptography.hazmat.primitives import serialization
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return signed, {"host_auditor": public}


def test_signed_receipt_exact_container_and_expiring_five_minutes():
    evidence, trusted = _fixture_receipt()
    assert IsolationReceipt.from_dict(evidence.to_dict()) == evidence
    verify_receipt(evidence, expected=evidence.boot, trusted_public_keys=trusted)
    with pytest.raises(IsolationDenied, match="different"):
        verify_receipt(evidence, expected=BootIdentity(
            "d" * 64, evidence.boot.network_id, evidence.boot.vm_sha256, IMAGE,
        ), trusted_public_keys=trusted)
    with pytest.raises(IsolationDenied):
        verify_receipt(evidence, expected=evidence.boot, trusted_public_keys={
            "host_auditor": b"e" * 32,
        })


def test_signed_receipt_tampering_stale_nonce_and_false_checks():
    sample, trust = _fixture_receipt()
    def patch(**kwargs):
        d = sample.to_dict()
        d.update(kwargs)
        return IsolationReceipt.from_dict(d)
    for r in (
        patch(checks={**sample.checks, "metadata_blocked": False}),
        patch(host_ports={**sample.host_ports, "5000": "0.0.0.0:5000"}),
        patch(expires_at=sample.checked_at + 301),
        patch(nonce="n" * 32),
    ):
        with pytest.raises(IsolationDenied):
            verify_receipt(r, expected=sample.boot, trusted_public_keys=trust)
    with pytest.raises(IsolationDenied):
        verify_receipt(sample, expected=sample.boot, trusted_public_keys=trust,
                       now=sample.expires_at + 1)


def test_signed_receipt_rejects_unknown_or_misbound_schema():
    sample, _ = _fixture_receipt()
    data = sample.to_dict()
    data["network_name"] = "bridge"
    with pytest.raises(IsolationDenied):
        IsolationReceipt.from_dict(data)
    data = sample.to_dict()
    data["owner_approved"] = True
    with pytest.raises(IsolationDenied):
        IsolationReceipt.from_dict(data)


def _docker_inspection():
    cid = "a" * 64
    nid = "b" * 64
    binding = {
        f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(20000 + port)}]
        for port in EXPECTED_PORTS
    }
    container = {
        "Id": cid,
        "State": {"Running": True},
        "Config": {"Image": IMAGE},
        "HostConfig": {
            "Privileged": False, "NetworkMode": NETWORK_NAME,
            "PortBindings": binding, "CapAdd": ["NET_ADMIN"],
            "PidMode": "", "IpcMode": "private",
        },
        "NetworkSettings": {
            "Networks": {NETWORK_NAME: {
                "NetworkID": nid, "Gateway": "172.22.0.1",
            }},
            "Ports": binding,
        },
        "Mounts": [{
            "Source": "/approved/osworld-v2-ubuntu-x86.qcow2",
            "Destination": "/System.qcow2", "RW": False,
        }],
    }
    network = {
        "Id": nid, "Name": NETWORK_NAME, "Internal": True,
        "EnableIPv6": False, "Driver": "bridge",
    }
    return container, network


def test_network_inspection_rejects_external_ports_networks_and_privilege(monkeypatch):
    c, n = _docker_inspection()
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: [n] if args[:2] == ["network", "inspect"] else [c],
    )
    identity, ports, gateway = network_audit.inspect_topology(
        "a" * 64, expected_vm_hash="c" * 64,
    )
    assert identity == BootIdentity("a" * 64, "b" * 64, "c" * 64, IMAGE)
    assert len(ports) == 4 and gateway == "172.22.0.1"
    c["HostConfig"]["PortBindings"]["5000/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(IsolationDenied, match="loopback"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)
    c, n = _docker_inspection()
    c["NetworkSettings"]["Networks"]["bridge"] = {"NetworkID": "d" * 64}
    with pytest.raises(IsolationDenied):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)
    c, n = _docker_inspection()
    c["HostConfig"]["Privileged"] = True
    with pytest.raises(IsolationDenied):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_network_negative_checks_are_never_optimistic(monkeypatch):
    monkeypatch.setattr(network_audit, "_probe", lambda container, code: False)
    checks = network_audit.negative_network_probes("a" * 64, "172.22.0.1")
    assert not any(checks.values())
    assert "host_gateway_blocked" in checks


@pytest.mark.parametrize("action", [
    {"action": "click", "x": -1, "y": 0},
    {"action": "type", "text": "\n"},
    {"action": "type", "text": "A" * 501},
    {"action": "key", "key": "win"},
    {"action": "click", "x": 1, "y": True},
    {"action": "done", "command": "powershell"},
])
def test_python_312_worker_never_accepts_arbitrary_code(action):
    worker = _script("osworld_secure_worker")
    with pytest.raises(worker.WorkerDenied):
        worker._action(action)


def test_worker_json_action_only_and_pinned_task_path(tmp_path):
    worker = _script("osworld_secure_worker")
    assert worker._action({"action": "click", "x": 4, "y": 5}) == "pyautogui.click(4, 5)"
    assert worker._action({"action": "done"}) == "DONE"
    assert worker._action({"action": "type", "text": "hello; import os"}).startswith("pyautogui.write(")
    with pytest.raises(worker.WorkerDenied):
        worker.load_official_task(tmp_path, "../etc/passwd", "c" * 64)
    with pytest.raises(worker.WorkerDenied):
        worker.load_official_task(tmp_path, "001", "bad hash")


def test_worker_network_patch_forces_isolated_ports_and_no_kvm(monkeypatch, tmp_path):
    worker = _script("osworld_secure_worker")
    import types

    class FakeLock:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False

    fake_provider_module = types.ModuleType("desktop_env.providers.docker.provider")
    class FakeDockerProvider:
        pass
    fake_provider_module.DockerProvider = FakeDockerProvider
    fake_provider_module.FileLock = FakeLock
    monkeypatch.setitem(sys.modules, "desktop_env", types.ModuleType("desktop_env"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers", types.ModuleType("desktop_env.providers"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers.docker", types.ModuleType("desktop_env.providers.docker"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers.docker.provider", fake_provider_module)
    disk = tmp_path / "osworld-v2-ubuntu-x86.qcow2"
    disk.write_bytes(b"offline disk fixture; not a real VM")
    class FakeContainer:
        id = "a" * 64
        attrs = {}
        def reload(self): pass
    class FakeContainers:
        def run(self, *args, **kwargs):
            self.call = (args, kwargs)
            return FakeContainer()
    class FakeNetwork:
        attrs = {"Name": NETWORK_NAME, "Internal": True, "EnableIPv6": False,
                 "Driver": "bridge", "Id": "b" * 64}
        def reload(self): pass
    class FakeClient:
        def __init__(self):
            self.containers = FakeContainers()
            self.networks = SimpleNamespace(get=lambda name: FakeNetwork())
    worker.secure_docker_patch(900, force_no_kvm=True)
    provider = FakeDockerProvider()
    provider.client = FakeClient()
    provider.lock_file = tmp_path / "lock"
    provider.environment = {"RAM_SIZE": "4G"}
    provider._get_available_port = lambda start: start + 1000
    provider._wait_for_vm_ready = lambda timeout: setattr(provider, "seen_timeout", timeout)
    monkeypatch.setattr(worker, "verify_running_container", lambda *a, **k: None)
    provider.start_emulator(str(disk), True, "Ubuntu")
    _, options = provider.client.containers.call
    assert options["network"] == NETWORK_NAME
    assert options["ports"][5000] == ("127.0.0.1", 6000)
    assert options["ports"][8006] == ("127.0.0.1", 9006)
    assert options["environment"]["KVM"] == "N"
    assert options["volumes"][str(disk)]["mode"] == "ro"
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert provider.seen_timeout == 900


def test_bridge_denies_unpinned_runtime_before_spawn(tmp_path):
    with pytest.raises(FileNotFoundError):
        pinned_python(tmp_path / "nonexistent_osworld")
    assert "HF_TOKEN" not in ALLOWED_ENV
    assert "AURA_APPROVAL_FINGERPRINT_KEY_HEX" not in ALLOWED_ENV
    assert "AURA_OWNER_PRIVATE_KEY" not in ALLOWED_ENV


def test_operator_attestor_never_auto_self_signs(tmp_path):
    from aura_core.osworld.isolation import load_pinned_public_keys
    with pytest.raises(IsolationDenied):
        load_pinned_public_keys(tmp_path / "not-provisioned.json")


def test_live_entry_requires_operator_consent_before_spawn():
    import asyncio
    runner = _script("run_osworld_v2_live")
    args = SimpleNamespace(allow_real_vm=False)
    with pytest.raises(PermissionError, match="--allow-real-vm"):
        asyncio.run(runner.run(args))


def test_official_v21_evaluate_has_no_logger_argument():
    import asyncio
    from aura_core.enterprise.approval_store import SQLiteApprovalStore, ApprovalStatus
    from aura_core.osworld.runtime import compose_vm_gateway
    from aura_core.osworld.live_vm import evaluate_live_vm

    class FakeVM:
        def reset(self, task_config):
            return {"accessibility_tree": "offline"}
        def step(self, action, pause=0):
            return {"accessibility_tree": "offline"}, 0, action == "DONE", {}
        def evaluate(self):
            return 1.0

    class Planner:
        async def next_action(self, **kwargs):
            return {"action": "done"}

    class TestOwner:
        def __init__(self, store): self.store = store
        async def wait_for_owner_approval(self, approval_id, timeout_seconds):
            rec = self.store.get(approval_id)
            self.store.decide(
                rec.approval_id, expected_version=rec.version,
                approver_id="human:local-owner",
                decision=ApprovalStatus.APPROVED,
            )
            return True

    async def run():
        with SQLiteApprovalStore(":memory:") as store:
            gateway = compose_vm_gateway(
                environment=FakeVM(), store=store, fingerprint_key=b"j" * 32,
            )
            result = await evaluate_live_vm(
                environment=FakeVM(), gateway=gateway,
                planner=Planner(), approvals=TestOwner(store),
                task_config={"id": "unit-fixture", "instruction": "offline"},
            )
            assert result.score == 1.0
    asyncio.run(run())
