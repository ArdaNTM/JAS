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
    boot = BootIdentity("a" * 64, "b" * 64, "c" * 64, IMAGE, "d" * 64, "e" * 64)
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


@pytest.mark.parametrize(("key", "value"), [
    ("NETWORK", "nat"),
    ("NETWORK", "slirp"),
    ("USER_PORTS", ""),
    ("USER_PORTS", "5000,8080,9222,22"),
    ("HOST_PORTS", ""),
    ("HOST_PORTS", "5000"),
])
def test_network_attestor_rejects_unapproved_slirp_environment(monkeypatch, key, value):
    container, network = _docker_inspection()
    env = container["Config"]["Env"]
    env[:] = [entry for entry in env if not entry.startswith(key + "=")]
    env.append(key + "=" + value)
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="QEMU network"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_network_attestor_rejects_duplicate_slirp_environment(monkeypatch):
    container, network = _docker_inspection()
    container["Config"]["Env"].append("NETWORK=user")
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="QEMU network"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_signed_receipt_exact_container_and_expiring_five_minutes():
    evidence, trusted = _fixture_receipt()
    assert IsolationReceipt.from_dict(evidence.to_dict()) == evidence
    verify_receipt(evidence, expected=evidence.boot, trusted_public_keys=trusted)
    with pytest.raises(IsolationDenied, match="different"):
        verify_receipt(evidence, expected=BootIdentity(
            "f" * 64, evidence.boot.network_id, evidence.boot.vm_sha256,
            IMAGE, evidence.boot.gateway_container_id, evidence.boot.gateway_network_id,
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
        patch(gateway_container_id="f" * 64),
        patch(gateway_network_id="f" * 64),
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
    run_id = "f" * 32
    storage_name = network_audit.STORAGE_VOLUME_PREFIX + run_id
    container = {
        "Id": cid,
        "State": {"Running": True},
        "Config": {
            "Image": IMAGE,
            "Labels": {"aura.osworld.run_id": run_id},
            "Env": [
                "NETWORK=user", "USER_PORTS=5000,8080,9222",
                "HOST_PORTS=8006", "KVM=N",
            ],
        },
        "HostConfig": {
            "Privileged": False, "NetworkMode": NETWORK_NAME,
            "PortBindings": {}, "CapAdd": ["CHOWN", "NET_ADMIN"],
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/var/log/nginx": network_audit.NGINX_LOG_TMPFS},
            "Devices": [{
                "PathOnHost": "/dev/net/tun",
                "PathInContainer": "/dev/net/tun",
                "CgroupPermissions": "rwm",
            }],
            "PidMode": "", "IpcMode": "private",
        },
        "NetworkSettings": {
            "Networks": {NETWORK_NAME: {
                "NetworkID": nid, "Gateway": "172.22.0.1", "IPAddress": "172.22.0.3",
            }},
            "Ports": {f"{port}/tcp": None for port in EXPECTED_PORTS},
        },
        "Mounts": [{
            "Source": "/approved/osworld-v2-ubuntu-x86.qcow2",
            "Destination": "/System.qcow2", "RW": False,
        }, {
            "Type": "volume", "Name": storage_name, "Driver": "local",
            "Destination": "/storage", "RW": True,
        }],
    }
    network = {
        "Id": nid, "Name": NETWORK_NAME, "Internal": True,
        "EnableIPv6": False, "Driver": "bridge",
    }
    return container, network


def _fake_docker_json(args, container, network):
    run_id = container["Config"]["Labels"]["aura.osworld.run_id"]
    ingress = network_audit.INGRESS_PREFIX + run_id
    gateway_name = network_audit.GATEWAY_PREFIX + run_id
    if args[:2] == ["network", "inspect"]:
        if args[2] == NETWORK_NAME:
            return [network]
        assert args[2] == ingress
        return [{
            "Id": "e" * 64, "Name": ingress, "Driver": "bridge",
            "Internal": False, "EnableIPv6": False, "Attachable": False,
            "Options": dict(network_audit.INGRESS_OPTIONS),
            "Labels": {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": "loopback-ingress",
            },
            "IPAM": {"Config": [{"Gateway": "172.25.0.1"}]},
        }]
    if args[:2] == ["volume", "inspect"]:
        return [{
            "Name": network_audit.STORAGE_VOLUME_PREFIX + run_id,
            "Driver": "local", "Scope": "local", "Options": None,
            "Labels": {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": "vm-storage",
            },
        }]
    if args[:2] == ["inspect", gateway_name]:
        return [container.get("_mock_gateway", {
            "Id": "d" * 64,
            "Name": "/" + gateway_name,
            "State": {"Running": True},
            "Config": {
                "Image": network_audit.GATEWAY_IMAGE,
                "User": "65534:65534",
                "Entrypoint": ["python3", "-B", "-u", "-c"],
                "Cmd": [
                    (Path(__file__).resolve().parents[1] / "src" / "aura_core" /
                     "osworld" / "loopback_gateway.py").read_text(encoding="utf-8"),
                    "172.22.0.3",
                ],
                "Labels": {
                    "aura.osworld.run_id": run_id,
                    "aura.osworld.role": "loopback-gateway",
                },
            },
            "HostConfig": {
                "NetworkMode": ingress, "Privileged": False,
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"], "CapAdd": [],
                "SecurityOpt": ["no-new-privileges:true"],
                "Memory": 96 * 1024 * 1024,
                "PidsLimit": 64, "Devices": [], "Tmpfs": {},
                "PortBindings": {
                    f"{port}/tcp": [{
                        "HostIp": "127.0.0.1",
                        "HostPort": str(20000 + port),
                    }] for port in EXPECTED_PORTS
                },
            },
            "NetworkSettings": {
                "Networks": {
                    NETWORK_NAME: {"NetworkID": "b" * 64},
                    ingress: {"NetworkID": "e" * 64, "Gateway": "172.25.0.1"},
                },
                "Ports": {
                    f"{port}/tcp": [{
                        "HostIp": "127.0.0.1",
                        "HostPort": str(20000 + port),
                    }] for port in EXPECTED_PORTS
                },
            },
            "Mounts": [],
        })]
    return [container]



@pytest.mark.parametrize("mutate", [
    lambda g: g["HostConfig"].update(Privileged=True),
    lambda g: g["HostConfig"].update(ReadonlyRootfs=False),
    lambda g: g["HostConfig"].update(CapAdd=["NET_ADMIN"]),
    lambda g: g["HostConfig"].update(CapDrop=[]),
    lambda g: g["HostConfig"].update(Memory=0),
    lambda g: g["Config"].update(User="0:0"),
    lambda g: g["Config"].update(Cmd=["unaudited-code", "172.22.0.3"]),
    lambda g: g["Config"].update(Image="python:latest"),
    lambda g: g["NetworkSettings"]["Networks"].update(bridge={"NetworkID": "9" * 64}),
    lambda g: g["HostConfig"]["PortBindings"]["5000/tcp"][0].update(HostIp="0.0.0.0"),
    lambda g: g["NetworkSettings"]["Ports"]["5000/tcp"][0].update(HostIp="0.0.0.0"),
])
def test_gateway_topology_fails_closed_on_privileges_mutation_and_port_escape(monkeypatch, mutate):
    import copy
    vm, network = _docker_inspection()
    name = network_audit.GATEWAY_PREFIX + "f" * 32
    proxy = copy.deepcopy(_fake_docker_json(["inspect", name], vm, network)[0])
    mutate(proxy)
    vm["_mock_gateway"] = proxy
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, vm, network),
    )
    with pytest.raises(IsolationDenied):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_receipt_signatures_bind_gateway_and_ingress_ids():
    evidence, trusted = _fixture_receipt()
    for change in ("gateway_container_id", "gateway_network_id"):
        modified = evidence.to_dict()
        modified[change] = "9" * 64
        altered = IsolationReceipt.from_dict(modified)
        with pytest.raises(IsolationDenied, match="different"):
            verify_receipt(altered, expected=evidence.boot, trusted_public_keys=trusted)
    legacy = evidence.to_dict()
    legacy["schema"] = "aura.osworld.network-isolation.v1"
    with pytest.raises(IsolationDenied, match="schema"):
        IsolationReceipt.from_dict(legacy)


def test_host_audit_denies_when_gateway_egress_probe_is_not_blocked(monkeypatch, tmp_path):
    vm, network = _docker_inspection()
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, vm, network),
    )
    monkeypatch.setattr(network_audit, "sha256_file", lambda path: "c" * 64)
    def probes(container, gateway):
        result = {key: True for key in (
            "egress_v4_blocked", "metadata_blocked", "external_dns_blocked",
            "ipv6_blocked", "host_gateway_blocked",
        )}
        if container == "d" * 64:
            result["egress_v4_blocked"] = False
        return result
    monkeypatch.setattr(network_audit, "negative_network_probes", probes)
    image = tmp_path / "qcow2"
    image.write_bytes(b"disk")
    with pytest.raises(IsolationDenied, match="Negative egress"):
        network_audit.audit_network(container_id="a" * 64, vm_image=image)


def test_network_inspection_rejects_external_ports_networks_and_privilege(monkeypatch):
    c, n = _docker_inspection()
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, c, n),
    )
    identity, ports, gateway = network_audit.inspect_topology(
        "a" * 64, expected_vm_hash="c" * 64,
    )
    assert identity == BootIdentity("a" * 64, "b" * 64, "c" * 64, IMAGE, "d" * 64, "e" * 64)
    assert len(ports) == 4 and gateway == "172.22.0.1"
    c["HostConfig"]["PortBindings"]["5000/tcp"] = [{
        "HostIp": "0.0.0.0", "HostPort": "25000",
    }]
    with pytest.raises(IsolationDenied, match="unexpectedly publishes"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)
    c, n = _docker_inspection()
    c["NetworkSettings"]["Networks"]["bridge"] = {"NetworkID": "d" * 64}
    with pytest.raises(IsolationDenied):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)
    c, n = _docker_inspection()
    c["HostConfig"]["Privileged"] = True
    with pytest.raises(IsolationDenied):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


@pytest.mark.parametrize("capabilities", [
    ["NET_ADMIN"],  # Missing CHOWN, Nginx cannot chown its working directory
    ["CHOWN"],      # Missing NET_ADMIN for the pinned VM runtime
    [],
    ["CHOWN", "NET_ADMIN", "SYS_ADMIN"],
    ["CHOWN", "NET_ADMIN", "DAC_OVERRIDE"],
    ["ALL"],
    ["CHOWN", "NET_ADMIN", "CHOWN"],
])
def test_network_attestation_rejects_unapproved_capabilities(monkeypatch, capabilities):
    container, network = _docker_inspection()
    container["HostConfig"]["CapAdd"] = capabilities
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="privileges"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


@pytest.mark.parametrize(("field", "value"), [
    ("CapDrop", None),
    ("CapDrop", []),
    ("CapDrop", ["NET_RAW"]),
    ("SecurityOpt", None),
    ("SecurityOpt", []),
])
def test_network_attestation_rejects_weak_container_sandbox(monkeypatch, field, value):
    container, network = _docker_inspection()
    container["HostConfig"][field] = value
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="privileges"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_network_attestation_accepts_normalized_cap_names(monkeypatch):
    container, network = _docker_inspection()
    container["HostConfig"]["CapAdd"] = ["CAP_CHOWN", "CAP_NET_ADMIN"]
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    boot, ports, gateway = network_audit.inspect_topology(
        "a" * 64, expected_vm_hash="c" * 64,
    )
    assert boot.network_id == "b" * 64
    assert len(ports) == 4 and gateway == "172.22.0.1"


@pytest.mark.parametrize("tmpfs", [
    None,
    {},
    {"/var/log/nginx": "rw,size=16m,mode=1777"},
    {"/var/log/nginx": "rw,nosuid,nodev,noexec,size=1g,mode=0755"},
    {"/var/log/nginx": network_audit.NGINX_LOG_TMPFS,
     "/var/log": network_audit.NGINX_LOG_TMPFS},
    {"/var/log/nginx": "rw,exec,suid,dev,size=16m,mode=0755"},
])
def test_attestor_denies_missing_or_weakened_nginx_tmpfs(monkeypatch, tmpfs):
    container, network = _docker_inspection()
    container["HostConfig"]["Tmpfs"] = tmpfs
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="tmpfs"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_attestor_accepts_nginx_tmpfs_in_mount_inventory(monkeypatch):
    container, network = _docker_inspection()
    container["Mounts"].append({
        "Type": "tmpfs", "Destination": "/var/log/nginx",
        "RW": True, "Source": "",
    })
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    boot, ports, gateway = network_audit.inspect_topology(
        "a" * 64, expected_vm_hash="c" * 64,
    )
    assert boot.network_id == "b" * 64
    assert len(ports) == 4 and gateway == "172.22.0.1"


@pytest.mark.parametrize("invalid_mount", [
    {"Type": "bind", "Destination": "/var/log/nginx", "RW": True,
     "Source": "/host/secret"},
    {"Type": "tmpfs", "Destination": "/etc/nginx", "RW": True,
     "Source": ""},
])
def test_attestor_rejects_unapproved_writable_mounts(monkeypatch, invalid_mount):
    container, network = _docker_inspection()
    container["Mounts"].append(invalid_mount)
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="mounts"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


@pytest.mark.parametrize("changed_policy", [
    None,
    {},
    {"/var/log/nginx": "rw,exec,suid,size=16m,mode=0777"},
    {"/var/log/nginx": "rw,nosuid,nodev,noexec,size=64m,mode=0755"},
])
def test_worker_revalidates_exact_nginx_log_tmpfs_before_vm_action(changed_policy):
    worker = _script("osworld_secure_worker")

    class StubContainer:
        def __init__(self, policy):
            self.attrs = {
                "State": {"Running": True},
                "Config": {"Image": worker.IMAGE, "Labels": {
                    "aura.osworld.run_id": "f" * 32,
                }, "Env": [
                    "NETWORK=user", "USER_PORTS=5000,8080,9222",
                    "HOST_PORTS=8006", "KVM=N",
                ]},
                "HostConfig": {
                    "Privileged": False, "NetworkMode": worker.NETWORK,
                    "Tmpfs": policy,
                    "Devices": [{
                        "PathOnHost": "/dev/net/tun",
                        "PathInContainer": "/dev/net/tun",
                        "CgroupPermissions": "rwm",
                    }],
                    "PortBindings": {},
                },
                "NetworkSettings": {
                    "Networks": {worker.NETWORK: {"NetworkID": "b" * 64}},
                },
                "Mounts": [{
                    "Destination": "/System.qcow2", "Type": "bind",
                    "RW": False,
                }, {
                    "Destination": "/storage", "Type": "volume",
                    "Name": worker.STORAGE_VOLUME_PREFIX + "f" * 32,
                    "RW": True,
                }],
            }

        def reload(self):
            pass

    valid = StubContainer({"/var/log/nginx": worker.NGINX_LOG_TMPFS})
    worker.verify_running_container(valid, "b" * 64)

    invalid = StubContainer(changed_policy)
    with pytest.raises(worker.WorkerDenied, match="tmpfs"):
        worker.verify_running_container(invalid, "b" * 64)


@pytest.mark.parametrize("devices", [
    [],
    [{"PathOnHost": "/dev/kvm", "PathInContainer": "/dev/kvm",
      "CgroupPermissions": "rwm"}],
    [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/net/tun",
      "CgroupPermissions": "rwm"},
     {"PathOnHost": "/dev/sda", "PathInContainer": "/dev/sda",
      "CgroupPermissions": "rwm"}],
    [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/net/tun",
      "CgroupPermissions": "rw"}],
    [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/fake",
      "CgroupPermissions": "rwm"}],
])
def test_attestor_refuses_missing_or_overscoped_tun(monkeypatch, devices):
    container, network = _docker_inspection()
    container["HostConfig"]["Devices"] = devices
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="device"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_attestor_permits_only_exact_tun_and_optional_pinned_kvm(monkeypatch):
    container, network = _docker_inspection()
    container["HostConfig"]["Devices"].append({
        "PathOnHost": "/dev/kvm", "PathInContainer": "/dev/kvm",
        "CgroupPermissions": "rwm",
    })
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    boot, _, _ = network_audit.inspect_topology(
        "a" * 64, expected_vm_hash="c" * 64,
    )
    assert boot.network_id == "b" * 64


@pytest.mark.parametrize("change", ["name", "type", "writable", "extra"])
def test_attestor_refuses_untrusted_vm_storage_mount(monkeypatch, change):
    container, network = _docker_inspection()
    storage = next(m for m in container["Mounts"]
                   if m["Destination"] == "/storage")
    if change == "name":
        storage["Name"] = "external-foreign-volume"
    elif change == "type":
        storage["Type"] = "bind"
    elif change == "writable":
        storage["RW"] = False
    else:
        container["Mounts"].append({
            "Type": "volume", "Name": "foreign", "RW": True,
            "Destination": "/home",
        })
    monkeypatch.setattr(
        network_audit, "docker_json",
        lambda args, **kwargs: _fake_docker_json(args, container, network),
    )
    with pytest.raises(IsolationDenied, match="mounts"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


@pytest.mark.parametrize("bad", [
    {"Name": "unexpected", "Driver": "local", "Scope": "local",
     "Options": None, "Labels": {
         "aura.osworld.run_id": "f" * 32, "aura.osworld.purpose": "vm-storage",
     }},
    {"Name": network_audit.STORAGE_VOLUME_PREFIX + "f" * 32,
     "Driver": "nfs", "Scope": "local", "Options": None, "Labels": {
         "aura.osworld.run_id": "f" * 32, "aura.osworld.purpose": "vm-storage",
     }},
    {"Name": network_audit.STORAGE_VOLUME_PREFIX + "f" * 32,
     "Driver": "local", "Scope": "local",
     "Options": {"device": "/some/host/path"}, "Labels": {
         "aura.osworld.run_id": "f" * 32, "aura.osworld.purpose": "vm-storage",
     }},
    {"Name": network_audit.STORAGE_VOLUME_PREFIX + "f" * 32,
     "Driver": "local", "Scope": "local", "Options": None,
     "Labels": {"aura.osworld.run_id": "another"}},
])
def test_attestor_refuses_untrusted_volume_driver_and_labels(monkeypatch, bad):
    container, network = _docker_inspection()
    def docker_query(args, **kwargs):
        if args[:2] == ["volume", "inspect"]:
            return [bad]
        return _fake_docker_json(args, container, network)
    monkeypatch.setattr(network_audit, "docker_json", docker_query)
    with pytest.raises(IsolationDenied, match="volume"):
        network_audit.inspect_topology("a" * 64, expected_vm_hash="c" * 64)


def test_worker_fails_closed_when_tun_disappears():
    worker = _script("osworld_secure_worker")
    class Fake:
        def reload(self):
            return None
    container = Fake()
    c, _ = _docker_inspection()
    c["Config"]["Image"] = worker.IMAGE
    c["HostConfig"]["Tmpfs"] = {"/var/log/nginx": worker.NGINX_LOG_TMPFS}
    c["HostConfig"]["Devices"] = []
    container.attrs = c
    with pytest.raises(worker.WorkerDenied, match="TUN"):
        worker.verify_running_container(container, "b" * 64)


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
        def stop_emulator(self, *args, **kwargs):
            self.stopped = True
    fake_provider_module.DockerProvider = FakeDockerProvider
    fake_provider_module.FileLock = FakeLock
    monkeypatch.setitem(sys.modules, "desktop_env", types.ModuleType("desktop_env"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers", types.ModuleType("desktop_env.providers"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers.docker", types.ModuleType("desktop_env.providers.docker"))
    monkeypatch.setitem(sys.modules, "desktop_env.providers.docker.provider", fake_provider_module)
    disk = tmp_path / "osworld-v2-ubuntu-x86.qcow2"
    disk.write_bytes(b"offline disk fixture; not a real VM")
    class FakeContainer:
        def __init__(self, role):
            self.id = ("d" if role == "proxy" else "a") * 64
            self.attrs = {
                "Config": {"Labels": {
                    "aura.osworld.run_id": "0" * 32,
                    **({"aura.osworld.role": "loopback-gateway"} if role == "proxy" else {}),
                }},
                "NetworkSettings": {"Networks": {
                    NETWORK_NAME: {"NetworkID": "b" * 64, "IPAddress": "172.22.0.3"},
                }},
            }
        def reload(self): pass
        def stop(self, timeout=3): self.stopped = True
        def remove(self, force=False): self.removed = True
    class FakeContainers:
        def __init__(self):
            self.calls = []
        def run(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return FakeContainer("proxy" if len(self.calls) == 3 else "vm")

    class FakeVolume:
        def __init__(self, name, labels):
            self.name = name
            self.labels = labels
            self.removed = False
        def remove(self, force=False):
            assert force is False
            self.removed = True

    class FakeVolumes:
        def __init__(self):
            self.created = None
        def create(self, *, name, driver, labels):
            assert driver == "local"
            self.created = FakeVolume(name, labels)
            return self.created
    class FakeNetwork:
        def __init__(self, name=NETWORK_NAME):
            self.attrs = {
                "Name": name, "Internal": name == NETWORK_NAME,
                "EnableIPv6": False, "Driver": "bridge",
                "Id": ("b" if name == NETWORK_NAME else "e") * 64,
                "Labels": {
                    "aura.osworld.run_id": "0" * 32,
                    "aura.osworld.purpose": "loopback-ingress",
                },
            }
        def reload(self): pass
        def connect(self, relay): self.attached = relay
        def remove(self): self.removed = True
    class FakeNetworks:
        def __init__(self):
            self.internal = FakeNetwork()
            self.ingress = None
        def get(self, name):
            return self.internal if name == NETWORK_NAME else self.ingress
        def create(self, name, **kwargs):
            self.ingress = FakeNetwork(name)
            self.creation = (name, kwargs)
            return self.ingress
    class FakeClient:
        def __init__(self):
            self.containers = FakeContainers()
            self.volumes = FakeVolumes()
            self.networks = FakeNetworks()
    worker.secure_docker_patch(900, force_no_kvm=True)
    provider = FakeDockerProvider()
    provider.client = FakeClient()
    provider.lock_file = tmp_path / "lock"
    provider.environment = {"RAM_SIZE": "4G"}
    provider._get_available_port = lambda start: start + 1000
    provider._wait_for_vm_ready = lambda timeout: setattr(provider, "seen_timeout", timeout)
    import osworld_gateway_support as gateway_support
    monkeypatch.setattr(gateway_support, "verify_gateway", lambda *a, **k: None)
    monkeypatch.setattr(worker, "verify_gateway", lambda *a, **k: None)
    monkeypatch.setattr(worker, "verify_running_container", lambda *a, **k: None)
    provider.start_emulator(str(disk), True, "Ubuntu")
    calls = provider.client.containers.calls
    assert len(calls) == 3
    seed_args, seed_opts = calls[0]
    assert seed_args == (worker.IMAGE,)
    assert seed_opts["network_mode"] == "none"
    assert seed_opts["cap_drop"] == ["ALL"]
    assert seed_opts["security_opt"] == ["no-new-privileges:true"]
    assert seed_opts["entrypoint"] == ["/bin/sh", "-ec"]
    assert seed_opts["command"] == [worker.STORAGE_SEED_SCRIPT]
    assert "chmod 0644 /storage/uefi.rom" in seed_opts["command"][0]
    assert "chmod 0755 /storage" in seed_opts["command"][0]
    assert "cp /usr/share/OVMF/edk2-x86_64-code.fd" in seed_opts["command"][0]
    _, options = calls[1]
    assert options["network"] == NETWORK_NAME
    assert options["ports"] == {}
    assert options["environment"]["KVM"] == "N"
    assert options["environment"]["NETWORK"] == "user"
    assert options["environment"]["USER_PORTS"] == "5000,8080,9222"
    assert options["environment"]["HOST_PORTS"] == "8006"
    assert options["volumes"][str(disk)]["mode"] == "ro"
    volume = provider.client.volumes.created
    assert volume.name == worker.STORAGE_VOLUME_PREFIX + "0" * 32
    assert volume.labels == {
        "aura.osworld.run_id": "0" * 32,
        "aura.osworld.purpose": "vm-storage",
    }
    assert options["volumes"][volume.name] == {"bind": "/storage", "mode": "rw"}
    assert options["devices"] == ["/dev/net/tun:/dev/net/tun:rwm"]
    assert options["cap_drop"] == ["ALL"]
    assert options["cap_add"] == ["CHOWN", "NET_ADMIN"]
    assert options["tmpfs"] == {"/var/log/nginx": worker.NGINX_LOG_TMPFS}
    assert options["security_opt"] == ["no-new-privileges:true"]
    gateway_args, gateway_options = calls[2]
    assert gateway_args == (gateway_support.GATEWAY_IMAGE,)
    assert gateway_options["network"] == gateway_support.INGRESS_PREFIX + "0" * 32
    assert gateway_options["ports"][5000] == ("127.0.0.1", 6000)
    assert gateway_options["ports"][8006] == ("127.0.0.1", 9006)
    assert gateway_options["cap_drop"] == ["ALL"]
    assert gateway_options["read_only"] is True
    assert gateway_options["user"] == "65534:65534"
    assert gateway_options["command"][1] == "172.22.0.3"
    assert gateway_options["command"][0] == gateway_support.proxy_source()
    assert provider.seen_timeout == 900
    provider.stop_emulator("ignored")
    assert volume.removed is True
    assert provider.client.networks.ingress.removed is True


@pytest.mark.parametrize("authorized_label", [True, False])
def test_bridge_cleanup_never_removes_foreign_docker_volume(monkeypatch, authorized_label):
    import subprocess as sp
    from aura_core.osworld.runtime_bridge import OSWorldSubprocessVM

    bridge = OSWorldSubprocessVM.__new__(OSWorldSubprocessVM)
    bridge._run_id = "f" * 32
    volume_name = "aura-osworld-v21-storage-" + bridge._run_id
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        if argv[:3] == ["docker", "ps", "-aq"]:
            return SimpleNamespace(returncode=0, stdout="a" * 64 + "\n")
        if argv[:3] == ["docker", "network", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="")
        if argv[:3] == ["docker", "volume", "inspect"]:
            label = bridge._run_id if authorized_label else "foreign-run"
            return SimpleNamespace(returncode=0, stdout=json.dumps([{
                "Name": volume_name, "Driver": "local",
                "Labels": {
                    "aura.osworld.run_id": label,
                    "aura.osworld.purpose": "vm-storage",
                },
            }]))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(sp, "run", run)
    bridge._cleanup_run_containers()
    assert ["docker", "rm", "-f", "a" * 64] in commands
    assert ["docker", "volume", "inspect", volume_name] in commands
    removed = ["docker", "volume", "rm", volume_name] in commands
    assert removed is authorized_label


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
