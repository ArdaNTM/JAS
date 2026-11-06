"""Bounded Docker ingress for the pinned OSWorld internal-only bridge.

The VM never joins this non-internal ingress network. Only the fixed,
non-root TCP relay is dual-homed; its runtime configuration is re-inspected
and independently audited. This module does not grant an MCP capability.
"""
from __future__ import annotations

import hashlib
import ipaddress
from pathlib import Path
import re

GATEWAY_IMAGE = "python:3.12.16-alpine@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41"
INGRESS_PREFIX = "aura-osworld-v21-ingress-"
GATEWAY_PREFIX = "aura-osworld-v21-gateway-"
PORTS = (5000, 8006, 8080, 9222)
INGRESS_OPTIONS = {"com.docker.network.bridge.enable_ip_masquerade": "false"}
MEMORY_BYTES = 96 * 1024 * 1024
PIDS_LIMIT = 64
GATEWAY_CODE_SHA256 = "4bf0fc7cfe01080958f25789975ba4b8e1a3b3f32847101984db925168a65bed"


class GatewayDenied(PermissionError):
    pass


def proxy_source() -> str:
    file = Path(__file__).resolve().parents[1] / "src" / "aura_core" / "osworld" / "loopback_gateway.py"
    if file.is_symlink() or not file.is_file() or not 100 < file.stat().st_size <= 8192:
        raise GatewayDenied("Missing fixed, sealed gateway relay source")
    code = file.read_text(encoding="utf-8")
    if hashlib.sha256(code.encode("utf-8")).hexdigest() != GATEWAY_CODE_SHA256:
        raise GatewayDenied("Gateway relay code changed from pinned digest")
    return code


def vm_ip_address(container: object, network: str) -> str:
    container.reload()
    nets = (container.attrs.get("NetworkSettings") or {}).get("Networks") or {}
    ip = nets.get(network, {}).get("IPAddress")
    try:
        addr = ipaddress.IPv4Address(ip)
        if not addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError("Not internal IPv4")
    except (ValueError, TypeError) as exc:
        raise GatewayDenied("VM has no valid internal IPv4 destination") from exc
    return str(addr)


def start_gateway(provider: object, *, run_id: str, vm: object, internal: str, internal_id: str, ports: dict[int, int]) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not re.fullmatch(r"[0-9a-f]{64}", internal_id):
        raise GatewayDenied("Invalid gateway ownership or internal network")
    if set(ports) != set(PORTS) or len(set(ports.values())) != 4 or any(
        type(value) is not int or not 1 <= value <= 65535 for value in ports.values()
    ):
        raise GatewayDenied("Only four independently allocated loopback ports allowed")
    provider._aura_gateway = None
    provider._aura_ingress_network = None
    provider._aura_run_id = run_id
    provider._aura_ingress_network_id = None
    dest = vm_ip_address(vm, internal)
    ingress_name = INGRESS_PREFIX + run_id
    network = provider.client.networks.create(
        ingress_name, driver="bridge", internal=False, enable_ipv6=False,
        attachable=False, options=INGRESS_OPTIONS,
        labels={
            "aura.osworld.run_id": run_id,
            "aura.osworld.purpose": "loopback-ingress",
        },
    )
    provider._aura_ingress_network = network
    network.reload()
    ingress_id = network.attrs.get("Id")
    if not isinstance(ingress_id, str) or not re.fullmatch(r"[0-9a-f]{64}", ingress_id):
        raise GatewayDenied("Untrusted newly created ingress network")
    provider._aura_ingress_network_id = ingress_id
    relay = provider.client.containers.run(
        GATEWAY_IMAGE, name=GATEWAY_PREFIX + run_id,
        network=ingress_name,
        entrypoint=["python3", "-B", "-u", "-c"],
        command=[proxy_source(), dest],
        user="65534:65534",
        labels={
            "aura.osworld.run_id": run_id,
            "aura.osworld.role": "loopback-gateway",
        },
        ports={p: ("127.0.0.1", ports[p]) for p in PORTS},
        read_only=True, cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        pids_limit=PIDS_LIMIT, mem_limit="96m",
        detach=True,
    )
    provider._aura_gateway = relay
    provider.client.networks.get(internal).connect(relay)
    verify_gateway(provider, vm, internal, internal_id)


def verify_gateway(provider: object, vm: object, internal: str, internal_id: str) -> None:
    gateway = getattr(provider, "_aura_gateway", None)
    run_id = getattr(provider, "_aura_run_id", None)
    ingress_id = getattr(provider, "_aura_ingress_network_id", None)
    if gateway is None or not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise GatewayDenied("Missing governed ingress relay")
    gateway.reload()
    config = gateway.attrs.get("Config") or {}
    host = gateway.attrs.get("HostConfig") or {}
    nets = (gateway.attrs.get("NetworkSettings") or {}).get("Networks") or {}
    ingress = INGRESS_PREFIX + run_id
    dest = vm_ip_address(vm, internal)
    vm_run_id = (vm.attrs.get("Config") or {}).get("Labels", {}).get("aura.osworld.run_id")
    if (vm_run_id != run_id
            or gateway.attrs.get("State", {}).get("Running") is not True
            or gateway.attrs.get("Name") != "/" + GATEWAY_PREFIX + run_id
            or config.get("Image") != GATEWAY_IMAGE
            or config.get("User") != "65534:65534"
            or config.get("Entrypoint") != ["python3", "-B", "-u", "-c"]
            or config.get("Cmd") != [proxy_source(), dest]
            or config.get("Labels") != {
                "aura.osworld.run_id": run_id,
                "aura.osworld.role": "loopback-gateway",
            }
            or host.get("NetworkMode") != ingress
            or set(nets) != {internal, ingress}
            or nets[internal].get("NetworkID") != internal_id
            or nets[ingress].get("NetworkID") != ingress_id):
        raise GatewayDenied("Gateway identity, route, command or linked VM changed")
    if (host.get("Privileged") is not False
            or host.get("ReadonlyRootfs") is not True
            or host.get("CapDrop") not in (["ALL"], ["CAP_ALL"])
            or host.get("CapAdd") not in (None, [])
            or not any(v in ("no-new-privileges", "no-new-privileges:true")
                       for v in (host.get("SecurityOpt") or []))
            or host.get("PidsLimit") != PIDS_LIMIT
            or host.get("Memory") != MEMORY_BYTES
            or host.get("Devices") or gateway.attrs.get("Mounts") or host.get("Tmpfs")):
        raise GatewayDenied("Gateway privileges or mounts deviate from sealed policy")
    published = host.get("PortBindings") or {}
    actual = (gateway.attrs.get("NetworkSettings") or {}).get("Ports") or {}
    if set(published) != {str(p) + "/tcp" for p in PORTS}:
        raise GatewayDenied("Gateway has unexpected ports")
    for port in PORTS:
        key = str(port) + "/tcp"
        requested = published[key]
        observed = actual.get(key)
        if (not isinstance(requested, list) or len(requested) != 1
                or not isinstance(observed, list) or observed != requested
                or requested[0].get("HostIp") != "127.0.0.1"
                or not str(requested[0].get("HostPort", "")).isdigit()
                or not 1 <= int(requested[0]["HostPort"]) <= 65535):
            raise GatewayDenied("Gateway host port is not uniquely loopback bound")
    network = getattr(provider, "_aura_ingress_network", None)
    if network is None:
        raise GatewayDenied("Gateway ingress network object missing")
    network.reload()
    attrs = network.attrs
    if (attrs.get("Id") != ingress_id
            or attrs.get("Name") != ingress
            or attrs.get("Driver") != "bridge"
            or attrs.get("Internal") is not False
            or attrs.get("EnableIPv6") is not False
            or attrs.get("Attachable") is not False
            or any(attrs.get("Options", {}).get(k) != v
                   for k, v in INGRESS_OPTIONS.items())
            or attrs.get("Labels") != {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": "loopback-ingress",
            }):
        raise GatewayDenied("Untrusted Docker ingress network")


def cleanup_gateway(provider: object) -> None:
    run_id = getattr(provider, "_aura_run_id", None)
    gateway = getattr(provider, "_aura_gateway", None)
    if gateway is not None:
        try:
            gateway.reload()
            if gateway.attrs.get("Config", {}).get("Labels") == {
                "aura.osworld.run_id": run_id,
                "aura.osworld.role": "loopback-gateway",
            }:
                gateway.stop(timeout=3)
                gateway.remove(force=False)
        except Exception:
            pass
        provider._aura_gateway = None
    network = getattr(provider, "_aura_ingress_network", None)
    if network is not None:
        try:
            network.reload()
            if network.attrs.get("Labels") == {
                "aura.osworld.run_id": run_id,
                "aura.osworld.purpose": "loopback-ingress",
            }:
                network.remove()
        except Exception:
            pass
        provider._aura_ingress_network = None
