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
MAX_DOCKER_OUTPUT = 2_000_000


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


def inspect_topology(container_id: str, *, expected_vm_hash: str) -> tuple[BootIdentity, dict[str, str], str]:
    """Validate live Docker container identity, ports and only isolated net."""
    if not isinstance(container_id, str) or len(container_id) != 64 or any(c not in "0123456789abcdef" for c in container_id):
        raise IsolationDenied("Invalid full Docker container id")
    info = docker_json(["inspect", container_id])
    if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
        raise IsolationDenied("Docker returned no unambiguous container")
    obj = info[0]
    config = obj.get("Config") or {}
    host = obj.get("HostConfig") or {}
    network_settings = obj.get("NetworkSettings") or {}
    nets = network_settings.get("Networks") or {}
    if (obj.get("Id") != container_id or not obj.get("State", {}).get("Running")
            or set(nets) != {NETWORK_NAME} or host.get("NetworkMode") != NETWORK_NAME):
        raise IsolationDenied("Container is not running exclusively on the lab network")
    net = nets[NETWORK_NAME]
    nid = net.get("NetworkID", "")
    network = docker_json(["network", "inspect", NETWORK_NAME])
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
    mounts = obj.get("Mounts") or []
    if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
        raise IsolationDenied("Malformed Docker mount inventory")
    disk_mounts = [m for m in mounts if m.get("Destination") == "/System.qcow2"]
    log_mounts = [m for m in mounts if m.get("Destination") == "/var/log/nginx"]
    if (len(disk_mounts) != 1 or disk_mounts[0].get("RW") is not False
            or disk_mounts[0].get("Type") not in (None, "bind")
            or len(log_mounts) > 1
            or any(m.get("Type") != "tmpfs" or m.get("RW") is not True
                   for m in log_mounts)
            or len(mounts) != len(disk_mounts) + len(log_mounts)
            or any("docker.sock" in str(m.get("Source", "")) for m in mounts)):
        raise IsolationDenied("Container mounts exceed pinned disk and bounded Nginx tmpfs")
    if config.get("Image") != IMAGE:
        raise IsolationDenied("Runtime image not pinned to approved digest")
    bindings = host.get("PortBindings") or {}
    if set(bindings) != {f"{port}/tcp" for port in EXPECTED_PORTS}:
        raise IsolationDenied("Host port bindings do not exactly match four endpoints")
    ports: dict[str, str] = {}
    for port in EXPECTED_PORTS:
        entries = bindings[f"{port}/tcp"]
        actual = (network_settings.get("Ports") or {}).get(f"{port}/tcp")
        if (not isinstance(entries, list) or len(entries) != 1
                or entries[0].get("HostIp") != "127.0.0.1"
                or not isinstance(actual, list) or len(actual) != 1
                or actual[0].get("HostIp") != "127.0.0.1"
                or entries[0].get("HostPort") != actual[0].get("HostPort")):
            raise IsolationDenied("VM control endpoints are not exclusively loopback")
        portnum = str(entries[0].get("HostPort", ""))
        if not portnum.isdigit() or not 1 <= int(portnum) <= 65535:
            raise IsolationDenied("Invalid loopback published port")
        ports[str(port)] = f"127.0.0.1:{portnum}"
    gateway = net.get("Gateway") or ""
    try:
        ip = ipaddress.ip_address(gateway)
        if not isinstance(ip, ipaddress.IPv4Address) or ip.is_global or ip.is_loopback:
            raise ValueError("Unexpected gateway")
    except ValueError as exc:
        raise IsolationDenied("Missing internal network gateway") from exc
    return BootIdentity(container_id, nid, expected_vm_hash, IMAGE), ports, gateway


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


def negative_network_probes(container_id: str, gateway: str) -> dict[str, bool]:
    """Strict representative network probes; failed/unknown => NO signed receipt."""
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
    *, container_id: str, vm_image: Path,
) -> tuple[BootIdentity, dict[str, str], dict[str, bool]]:
    """Host audit rejects fake/evasive network topology before invoking probes."""
    image_hash = sha256_file(vm_image.resolve(strict=True))
    boot, ports, gateway = inspect_topology(container_id, expected_vm_hash=image_hash)
    checks = {
        "network_internal": True, "single_network": True,
        "loopback_ports": True, "unprivileged": True,
        "no_docker_socket": True, "image_pinned": True,
        **negative_network_probes(container_id, gateway),
    }
    if set(checks) != REQUIRED_CHECKS or not all(checks.values()):
        raise IsolationDenied("Negative egress or network topology check failed")
    return boot, ports, checks
