"""Independent OSWorld Docker network auditor (host-owned, never inside VM).

IMPORTANT: An internal Docker bridge plus negative probes cannot prove the
absence of every possible covert channel or host compromise. This bounded
receipt describes the *exact* checks performed, and binds one running VM.
The signer key lives outside the AURA checkout and is used only by an
independently launched host-auditor CLI. Unverified audit results never grant
MCP or Owner capabilities.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .isolation import (
    BootIdentity, EXPECTED_PORTS, IMAGE, IsolationDenied, NETWORK_NAME,
    REQUIRED_CHECKS,
)

ALPINE = "alpine:3.21"
# HostConfig.Tmpfs must match the worker policy EXACTLY.
NGINX_LOG_TMPFS = "rw,nosuid,nodev,noexec,size=16m,mode=0755"
STORAGE_VOLUME_PREFIX = "aura-osworld-v21-storage-"
STORAGE_VOLUME_PURPOSE = "vm-storage"
# Independent host policy: explicit SLIRP must forward only approved guest
# services, never the container-hosted 8006 web UI.
GUEST_NETWORK_MODE = "user"
GUEST_FORWARD_PORTS = "5000,8080,9222"
CONTAINER_ONLY_PORTS = "8006"
MAX_DOCKER_OUTPUT = 2_000_000
GATEWAY_IMAGE = "python:3.12.16-alpine@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41"
INGRESS_PREFIX = "aura-osworld-v21-ingress-"
GATEWAY_PREFIX = "aura-osworld-v21-gateway-"
INGRESS_OPTIONS = {"com.docker.network.bridge.enable_ip_masquerade": "false"}
GATEWAY_MEMORY = 96 * 1024 * 1024
GATEWAY_PIDS = 64
GATEWAY_CODE_SHA256 = "4bf0fc7cfe01080958f25789975ba4b8e1a3b3f32847101984db925168a65bed"


def docker_json(argv: list[str], *, timeout: int = 20) -> object:
    proc = subprocess.run(
        ["docker", *argv], capture_output=True, text=True,
        timeout=timeout, check=False, shell=False,
    )
    if proc.returncode != 0 or len(proc.stdout) > MAX_DOCKER_OUTPUT:
        raise IsolationDenied(f"Docker inspection failed ({argv[0]}), exit={proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise IsolationDenied("Docker inspection produced invalid JSON") from exc


def _gateway_topology(
    obj: dict[str, Any], internal_id: str, *, docker_json_fn=None,
) -> tuple[str, str, dict[str, str], str]:
    """Independent audit of the exact dual-homed relay and its egress bridge."""
    call_docker = docker_json if docker_json_fn is None else docker_json_fn
    config_vm = obj.get("Config") or {}
    run_id = (config_vm.get("Labels") or {}).get("aura.osworld.run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise IsolationDenied("Missing VM run ownership for ingress")
    ingress_name = INGRESS_PREFIX + run_id
    gateway_name = GATEWAY_PREFIX + run_id
    data = call_docker(["inspect", gateway_name])
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise IsolationDenied("Missing unambiguous loopback gateway")
    gateway = data[0]
    gateway_id = gateway.get("Id")
    if not isinstance(gateway_id, str) or not re.fullmatch(r"[0-9a-f]{64}", gateway_id):
        raise IsolationDenied("Invalid gateway container identity")
    config = gateway.get("Config") or {}
    host = gateway.get("HostConfig") or {}
    nets = (gateway.get("NetworkSettings") or {}).get("Networks") or {}
    vm_network = (obj.get("NetworkSettings") or {}).get("Networks") or {}
    vm_ip = vm_network.get(NETWORK_NAME, {}).get("IPAddress")
    try:
        ip = ipaddress.IPv4Address(vm_ip)
        if not ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Unexpected VM IP")
    except (TypeError, ValueError) as exc:
        raise IsolationDenied("VM address is not a private internal IPv4") from exc
    source_path = Path(__file__).with_name("loopback_gateway.py")
    if source_path.is_symlink() or not source_path.is_file() or source_path.stat().st_size > 8192:
        raise IsolationDenied("Sealed gateway source missing")
    code = source_path.read_text(encoding="utf-8")
    if hashlib.sha256(code.encode("utf-8")).hexdigest() != GATEWAY_CODE_SHA256:
        raise IsolationDenied("Gateway executable differs from release-pinned source")
    if (gateway.get("Name") != "/" + gateway_name
            or gateway.get("State", {}).get("Running") is not True
            or config.get("Image") != GATEWAY_IMAGE
            or config.get("User") != "65534:65534"
            or config.get("Entrypoint") != ["python3", "-B", "-u", "-c"]
            or config.get("Cmd") != [code, vm_ip]
            or config.get("Labels") != {
                "aura.osworld.run_id": run_id,
                "aura.osworld.role": "loopback-gateway",
            }
            or host.get("NetworkMode") != ingress_name
            or set(nets) != {NETWORK_NAME, ingress_name}
            or nets[NETWORK_NAME].get("NetworkID") != internal_id):
        raise IsolationDenied("Untrusted ingress relay command, identity or network")
    ingress_network = call_docker(["network", "inspect", ingress_name])
    if (not isinstance(ingress_network, list) or len(ingress_network) != 1
            or not isinstance(ingress_network[0], dict)):
        raise IsolationDenied("Untrusted ingress bridge")
    nw = ingress_network[0]
    ingress_id = nw.get("Id")
    if (not isinstance(ingress_id, str) or not re.fullmatch(r"[0-9a-f]{64}", ingress_id)
            or nets[ingress_name].get("NetworkID") != ingress_id
            or nw.get("Name") != ingress_name
            or nw.get("Driver") != "bridge"
            or nw.get("Internal") is not False
            or nw.get("EnableIPv6") is not False
            or nw.get("Attachable") is not False
            or any((nw.get("Options") or {}).get(k) != v for k, v in INGRESS_OPTIONS.items())
            or nw.get("Labels") != {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": "loopback-ingress",
            }):
        raise IsolationDenied("Unsafe gateway bridge or mutated ownership")
    if (host.get("Privileged") is not False
            or host.get("ReadonlyRootfs") is not True
            or host.get("CapDrop") not in (["ALL"], ["CAP_ALL"])
            or host.get("CapAdd") not in (None, [])
            or not any(v in ("no-new-privileges", "no-new-privileges:true")
                       for v in (host.get("SecurityOpt") or []))
            or host.get("Memory") != GATEWAY_MEMORY
            or host.get("PidsLimit") != GATEWAY_PIDS
            or host.get("Devices") or host.get("Tmpfs") or gateway.get("Mounts")):
        raise IsolationDenied("Gateway privilege or mount policy changed")
    expected = {f"{port}/tcp" for port in EXPECTED_PORTS}
    bindings = host.get("PortBindings") or {}
    actual_ports = (gateway.get("NetworkSettings") or {}).get("Ports") or {}
    if set(bindings) != expected or set(actual_ports) != expected:
        raise IsolationDenied("Unexpected gateway published ports")
    ports = {}
    for port in EXPECTED_PORTS:
        key = f"{port}/tcp"
        b = bindings[key]
        a = actual_ports[key]
        if (not isinstance(b, list) or len(b) != 1
                or not isinstance(a, list) or a != b
                or b[0].get("HostIp") != "127.0.0.1"):
            raise IsolationDenied("Gateway port escaped localhost or was not published")
        number = str(b[0].get("HostPort", ""))
        if not number.isdigit() or not 1 <= int(number) <= 65535:
            raise IsolationDenied("Invalid gateway host port")
        ports[str(port)] = "127.0.0.1:" + number
    gateway_ip = nets[ingress_name].get("Gateway") or ""
    try:
        addr = ipaddress.IPv4Address(gateway_ip)
        if not addr.is_private or addr.is_loopback:
            raise ValueError("Gateway host IP invalid")
    except (ValueError, TypeError) as exc:
        raise IsolationDenied("Invalid gateway ingress router") from exc
    return gateway_id, ingress_id, ports, str(addr)



def inspect_topology(
    container_id: str, *, expected_vm_hash: str, docker_json_fn=None,
) -> tuple[BootIdentity, dict[str, str], str]:
    """Validate live Docker container identity, ports and only isolated net."""
    call_docker = docker_json if docker_json_fn is None else docker_json_fn
    if not isinstance(container_id, str) or len(container_id) != 64 or any(c not in "0123456789abcdef" for c in container_id):
        raise IsolationDenied("Invalid full Docker container id")
    info = call_docker(["inspect", container_id])
    if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
        raise IsolationDenied("Docker returned no unambiguous container")
    obj = info[0]
    config = obj.get("Config") or {}
    env = config.get("Env")
    if not isinstance(env, list) or not all(isinstance(item, str) for item in env):
        raise IsolationDenied("Missing governed QEMU network environment")
    for key, expected in (
        ("NETWORK", GUEST_NETWORK_MODE),
        ("USER_PORTS", GUEST_FORWARD_PORTS),
        ("HOST_PORTS", CONTAINER_ONLY_PORTS),
    ):
        if [item[len(key) + 1:] for item in env if item.startswith(key + "=")] != [expected]:
            raise IsolationDenied("Unapproved QEMU network mode or guest port forwarding")
    host = obj.get("HostConfig") or {}
    network_settings = obj.get("NetworkSettings") or {}
    nets = network_settings.get("Networks") or {}
    if (obj.get("Id") != container_id or not obj.get("State", {}).get("Running")
            or set(nets) != {NETWORK_NAME} or host.get("NetworkMode") != NETWORK_NAME):
        raise IsolationDenied("Container is not running exclusively on the lab network")
    net = nets[NETWORK_NAME]
    nid = net.get("NetworkID", "")
    network = call_docker(["network", "inspect", NETWORK_NAME])
    if not isinstance(network, list) or len(network) != 1:
        raise IsolationDenied("No unambiguous Docker network")
    nw = network[0]
    if (nw.get("Id") != nid or nw.get("Internal") is not True
            or nw.get("EnableIPv6") is not False or nw.get("Driver") != "bridge"):
        raise IsolationDenied("Docker network is not strict internal IPv4 bridge")
    # Require exactly the minimal privilege set, not merely a subset.
    # Docker Engine may return capability names as CHOWN or CAP_CHOWN.
    raw_caps = host.get("CapAdd")
    caps = ({cap.removeprefix("CAP_") for cap in raw_caps}
            if isinstance(raw_caps, list)
            and all(isinstance(cap, str) for cap in raw_caps) else set())
    if (host.get("Privileged") is not False
            or host.get("PidMode") not in ("", None)
            or host.get("IpcMode") not in ("", None, "private")
            or host.get("NetworkMode") == "host"
            or caps != {"CHOWN", "NET_ADMIN"}
            or len(raw_caps or []) != 2
            or host.get("CapDrop") not in (["ALL"], ["CAP_ALL"])
            or not any(
                value in ("no-new-privileges", "no-new-privileges:true")
                for value in (host.get("SecurityOpt") or [])
            )):
        raise IsolationDenied("Unexpected elevated Docker sandbox host privileges")
    # Empty bounded tmpfs masks the pinned image's unwritable Nginx log file,
    # without granting DAC_OVERRIDE or mounting a writable host path.
    # Docker Engine can report the tmpfs only in HostConfig.Tmpfs or also in
    # Mounts depending on the creation API and Engine version.
    if (host.get("Tmpfs") or {}) != {"/var/log/nginx": NGINX_LOG_TMPFS}:
        raise IsolationDenied("Unexpected Nginx log tmpfs policy")
    # Docker Desktop must expose /dev/net/tun as a *specific* host character
    # device; allowing MKNOD or privileged container is prohibited. KVM is
    # optional only on capable non-Windows Docker engines.
    devices = host.get("Devices") or []
    if not isinstance(devices, list) or not all(isinstance(d, dict) for d in devices):
        raise IsolationDenied("Malformed host device policy")
    device_tuples = {
        (d.get("PathOnHost"), d.get("PathInContainer"), d.get("CgroupPermissions"))
        for d in devices
    }
    tun = ("/dev/net/tun", "/dev/net/tun", "rwm")
    kvm = ("/dev/kvm", "/dev/kvm", "rwm")
    if (tun not in device_tuples
            or len(device_tuples) != len(devices)
            or device_tuples - {tun, kvm}):
        raise IsolationDenied("Missing TUN device or unapproved host device mapping")
    labels = config.get("Labels") or {}
    run_id = labels.get("aura.osworld.run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise IsolationDenied("Missing exact Docker storage run identity")
    volume_name = STORAGE_VOLUME_PREFIX + run_id
    mounts = obj.get("Mounts") or []
    if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
        raise IsolationDenied("Malformed Docker mount inventory")
    disk_mounts = [m for m in mounts if m.get("Destination") == "/System.qcow2"]
    log_mounts = [m for m in mounts if m.get("Destination") == "/var/log/nginx"]
    storage_mounts = [m for m in mounts if m.get("Destination") == "/storage"]
    if (len(disk_mounts) != 1 or disk_mounts[0].get("RW") is not False
            or disk_mounts[0].get("Type") not in (None, "bind")
            or len(storage_mounts) != 1
            or storage_mounts[0].get("Type") != "volume"
            or storage_mounts[0].get("Name") != volume_name
            or storage_mounts[0].get("Driver") not in (None, "local")
            or storage_mounts[0].get("RW") is not True
            or len(log_mounts) > 1
            or any(m.get("Type") != "tmpfs" or m.get("RW") is not True
                   for m in log_mounts)
            or len(mounts) != len(disk_mounts) + len(log_mounts) + len(storage_mounts)
            or any("docker.sock" in str(m.get("Source", "")) for m in mounts)):
        raise IsolationDenied("Container mounts exceed pinned disk, ephemeral storage and Nginx tmpfs")
    # The independently signed receipt must not accept a user-supplied or
    # remote driver volume masquerading as our ephemeral /storage.
    details = call_docker(["volume", "inspect", volume_name])
    if not isinstance(details, list) or len(details) != 1:
        raise IsolationDenied("Ephemeral OSWorld storage not inspectable")
    volume = details[0]
    if (volume.get("Name") != volume_name
            or volume.get("Driver") != "local"
            or volume.get("Scope") not in ("local", None)
            or volume.get("Options") not in ({}, None)
            or volume.get("Labels") != {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": STORAGE_VOLUME_PURPOSE,
            }):
        raise IsolationDenied("Untrusted or unpinned OSWorld storage volume")
    if config.get("Image") != IMAGE:
        raise IsolationDenied("Runtime image not pinned to approved digest")
    # The application VM must never be attached to ingress or publish host
    # ports. Docker may show its exposed-but-unpublished ports as null.
    if (host.get("PortBindings") or any(
            b for b in (network_settings.get("Ports") or {}).values())):
        raise IsolationDenied("Internal OSWorld VM unexpectedly publishes host ports")
    gateway_id, ingress_id, ports, _ = _gateway_topology(obj, nid, docker_json_fn=call_docker)
    gateway = net.get("Gateway") or ""
    try:
        ip = ipaddress.ip_address(gateway)
        if not isinstance(ip, ipaddress.IPv4Address) or ip.is_global or ip.is_loopback:
            raise ValueError("Unexpected internal gateway")
    except ValueError as exc:
        raise IsolationDenied("Missing internal network gateway") from exc
    return BootIdentity(
        container_id, nid, expected_vm_hash, IMAGE, gateway_id, ingress_id,
    ), ports, gateway


def _probe(container_id: str, script: str) -> bool:
    """Execute a negative probe inside the *same Docker network namespace*.

    The disposable Alpine sidecar shares only the network namespace. Its
    process/PID/volume namespaces remain separate from the OSWorld container.
    Its check must explicitly print AURA_DENIED; transport/tool errors fail.
    """
    proc = subprocess.run(
        [
            "docker", "run", "--rm",
            "--network", f"container:{container_id}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "32", "--memory", "64m",
            ALPINE, "sh", "-eu", "-c", script,
        ],
        capture_output=True, text=True, timeout=30, check=False, shell=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "AURA_DENIED"


def negative_network_probes(
    container_id: str, gateway: str, *, probe_check=None,
) -> dict[str, bool]:
    """Strict representative network probes; failed/unknown => NO signed receipt."""
    if probe_check is not None:
        # The broker checks the identical CHECK schema without invoking the
        # legacy floating-image shell probe. Never catch/convert exceptions:
        # failed backend measurements abort the whole audit.
        return {
            "egress_v4_blocked": probe_check(container_id, "egress_v4_blocked", None),
            "metadata_blocked": probe_check(container_id, "metadata_blocked", None),
            "external_dns_blocked": probe_check(container_id, "external_dns_blocked", None),
            "ipv6_blocked": probe_check(container_id, "ipv6_blocked", None),
            "host_gateway_blocked": probe_check(container_id, "host_gateway_blocked", gateway),
        }
    def connect(host: str, port: int) -> str:
        if host != gateway and host not in {
            "1.1.1.1", "169.254.169.254", "8.8.8.8", "192.168.1.1", "10.0.0.1",
        }:
            raise IsolationDenied("Unexpected network probe target")
        return (
            f"if nc -z -w 3 {host} {port} >/dev/null 2>&1; "
            "then exit 3; else printf AURA_DENIED; fi"
        )
    checks = {
        "egress_v4_blocked": _probe(container_id, connect("1.1.1.1", 443)),
        "metadata_blocked": _probe(container_id, connect("169.254.169.254", 80)),
        "external_dns_blocked": _probe(
            container_id,
            "if timeout 5 nslookup example.com 8.8.8.8 >/dev/null 2>&1; "
            "then exit 3; else printf AURA_DENIED; fi",
        ),
        "ipv6_blocked": _probe(
            container_id,
            "if ip -6 route show default | grep -q default; "
            "then exit 3; else printf AURA_DENIED; fi",
        ),
        "host_gateway_blocked": all(_probe(container_id, connect(gateway, p))
                                    for p in (22, 80, 443, 2375, 2376)),
    }
    return checks


def sha256_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise IsolationDenied("Expected regular verified QCOW2 image file")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(2 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_network(
    *, container_id: str, vm_image: Path, docker_json_fn=None, probe_check=None,
) -> tuple[BootIdentity, dict[str, str], dict[str, bool]]:
    """Host audit rejects fake/evasive network topology before invoking probes."""
    call_docker = docker_json if docker_json_fn is None else docker_json_fn
    image_hash = sha256_file(vm_image.resolve(strict=True))
    boot, ports, gateway = inspect_topology(
        container_id, expected_vm_hash=image_hash, docker_json_fn=call_docker,
    )
    # Probe the relay separately; the VM must remain internal-only, while
    # the dual-homed ingress exposes only explicitly signed localhost ports.
    ingress_details = call_docker(["network", "inspect", INGRESS_PREFIX + (
        call_docker(["inspect", container_id])[0]["Config"]["Labels"]["aura.osworld.run_id"]
    )])
    ingress_gateway = ingress_details[0]["IPAM"]["Config"][0]["Gateway"]
    vm_checks = negative_network_probes(container_id, gateway, probe_check=probe_check)
    gateway_checks = negative_network_probes(boot.gateway_container_id, ingress_gateway, probe_check=probe_check)
    checks = {
        "network_internal": True, "single_network": True,
        "loopback_ports": True, "unprivileged": True,
        "no_docker_socket": True, "image_pinned": True,
        "gateway_topology": True,
        **vm_checks,
        **{"gateway_" + k: v for k, v in gateway_checks.items()},
    }
    if set(checks) != REQUIRED_CHECKS or not all(checks.values()):
        raise IsolationDenied("Negative egress or network topology check failed")
    return boot, ports, checks
