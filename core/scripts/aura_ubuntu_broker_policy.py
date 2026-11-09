"""Root-only, exact-schema AURA Ubuntu Docker audit policy (NOT deployed).

This Python 3.12 standard-library module is used ONLY by the root-owned local
Unix-socket helper. Untrusted SSH input cannot choose Docker args, images, mount
paths, Docker context, run ownership, network destinations or privileges.
"""
from __future__ import annotations

import errno
import ipaddress
import json
import os
import re
import stat
import subprocess
import time
from typing import Callable

REQUEST_SCHEMA = "aura.osworld.ubuntu-transport.request.v2"
RESPONSE_SCHEMA = "aura.osworld.ubuntu-transport.response.v2"
PROBE_SCHEMA = "aura.osworld.network-probe.v1"
DOCKER = "/usr/bin/docker"
DOCKER_SOCKET = "unix:///var/run/docker.sock"
DOCKER_CONFIG = "/var/empty"
VM_IMAGE = "happysixd/osworld-docker@sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
PROBE_IMAGE = "python:3.12.16-alpine@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41"
NETWORK = "aura-osworld-v21-lab"
INGRESS = "aura-osworld-v21-ingress-"
GATEWAY = "aura-osworld-v21-gateway-"
STORAGE = "aura-osworld-v21-storage-"
RUN_LABEL = "aura.osworld.run_id"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
GATEWAY_PORTS = (22, 80, 443, 2375, 2376)
TARGETS = {
    "egress_v4_blocked": ("tcp4", "1.1.1.1", 443),
    "metadata_blocked": ("tcp4", "169.254.169.254", 80),
    "external_dns_blocked": ("udp4", "8.8.8.8", 53),
    "ipv6_blocked": ("tcp6", "2606:4700:4700::1111", 443),
}
BLOCK_ERRNOS = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EPERM,
                errno.EACCES, errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL}
MAX_REQUEST = 1400
MAX_RESPONSE = 2_000_000
_PROBE_CODE = """
import errno,json,socket,sys
spec=json.loads(sys.argv[1])
fam=socket.AF_INET6 if spec["kind"]=="tcp6" else socket.AF_INET
typ=socket.SOCK_DGRAM if spec["kind"]=="udp4" else socket.SOCK_STREAM
with socket.socket(fam,typ) as s:
 s.settimeout(3)
 try: rc=s.connect_ex((spec["host"],spec["port"]))
 except OSError as exc: rc=exc.errno
allowed={errno.ENETUNREACH,errno.EHOSTUNREACH,errno.EPERM,errno.EACCES,errno.EAFNOSUPPORT,errno.EADDRNOTAVAIL}
print(json.dumps({"schema":"aura.osworld.network-probe.v1","name":spec["name"],
                  "errno":rc,"blocked":rc in allowed},separators=(",",":")))
"""


class Denied(PermissionError):
    """Reject requests without disclosing Docker output or secrets."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise Denied("Duplicate JSON field")
        out[key] = value
    return out


def parse_request(raw: bytes, *, now: int | None = None) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST:
        raise Denied("Invalid bounded request")
    try:
        data = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Denied("Nonfinite JSON")))
    except (ValueError, UnicodeError) as exc:
        raise Denied("Invalid JSON") from exc
    fields = {"schema", "operation", "target", "run_id", "vm_id", "nonce",
              "issued_at", "probe_name", "gateway_ip", "port"}
    if type(data) is not dict or set(data) != fields or data["schema"] != REQUEST_SCHEMA:
        raise Denied("Unexpected protocol shape")
    op, target, run_id, vm_id = (
        data["operation"], data["target"], data["run_id"], data["vm_id"])
    if (type(op) is not str or op not in {
        "inspect_container", "inspect_gateway", "inspect_network", "inspect_volume", "probe"}
            or type(target) is not str or type(run_id) is not str
            or HEX32.fullmatch(run_id) is None or type(vm_id) is not str
            or HEX64.fullmatch(vm_id) is None or type(data["nonce"]) is not str
            or HEX32.fullmatch(data["nonce"]) is None or type(data["issued_at"]) is not int):
        raise Denied("Untrusted request identity")
    current = int(time.time()) if now is None else now
    if not current - 30 <= data["issued_at"] <= current + 5:
        raise Denied("Expired or future request")
    expected = {
        "inspect_container": {vm_id},
        "inspect_gateway": {GATEWAY + run_id},
        "inspect_network": {NETWORK, INGRESS + run_id},
        "inspect_volume": {STORAGE + run_id},
        "probe": {vm_id},
    }
    # Gateway namespace is a second, separately measured target. Its full
    # container ID is verified against the name+labels inside execute().
    if op == "probe":
        if HEX64.fullmatch(target) is None:
            raise Denied("Probe requires full pinned VM/gateway ID")
    elif target not in expected[op]:
        raise Denied("Target not owned by pinned run")
    probe_name, gateway_ip, port = data["probe_name"], data["gateway_ip"], data["port"]
    if op != "probe":
        if any(x is not None for x in (probe_name, gateway_ip, port)):
            raise Denied("Inspect does not accept probe fields")
    elif probe_name == "host_gateway_blocked":
        try:
            addr = ipaddress.IPv4Address(gateway_ip)
        except (ValueError, TypeError) as exc:
            raise Denied("Untrusted gateway address") from exc
        if (not addr.is_private or addr.is_loopback or addr.is_link_local
                or type(port) is not int or port not in GATEWAY_PORTS):
            raise Denied("Untrusted gateway probe")
        data["gateway_ip"] = str(addr)
    elif type(probe_name) is not str or probe_name not in TARGETS or gateway_ip is not None or port is not None:
        raise Denied("Unapproved probe")
    return data


def docker_json(args: list[str], *, timeout: int = 20) -> object:
    """Only generated literal templates may call this internal function."""
    if not os.path.isfile(DOCKER) or os.path.islink(DOCKER):
        raise Denied("Pinned Docker CLI unavailable")
    metadata = os.stat(DOCKER)
    if metadata.st_uid != 0 or metadata.st_mode & 0o022 or not stat.S_ISREG(metadata.st_mode):
        raise Denied("Untrusted Docker executable")
    cmd = [DOCKER, "--host", DOCKER_SOCKET, "--config", DOCKER_CONFIG, *args]
    try:
        proc = subprocess.run(cmd, check=False, shell=False, capture_output=True,
                              timeout=timeout, env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LANG": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Denied("Docker operation failed closed") from exc
    if proc.returncode != 0 or len(proc.stdout) > MAX_RESPONSE or len(proc.stderr) > 4096:
        raise Denied("Docker operation failed closed")
    try:
        return json.loads(proc.stdout)
    except (ValueError, UnicodeDecodeError) as exc:
        raise Denied("Malformed Docker reply") from exc


def _single(value: object) -> dict:
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise Denied("Expected exactly one Docker resource")
    return value[0]


def _get_vm(run_id: str, vm_id: str, docker: Callable[..., object]) -> dict:
    vm = _single(docker(["inspect", vm_id]))
    config = vm.get("Config") or {}
    host = vm.get("HostConfig") or {}
    nets = (vm.get("NetworkSettings") or {}).get("Networks") or {}
    labels = config.get("Labels") or {}
    if (vm.get("Id") != vm_id or labels.get(RUN_LABEL) != run_id
            or config.get("Image") != VM_IMAGE
            or (vm.get("State") or {}).get("Running") is not True
            or host.get("NetworkMode") != NETWORK or set(nets) != {NETWORK}):
        raise Denied("Container fails pinned AURA run ownership")
    return vm


def _get_network(name: str, run_id: str, vm_id: str, vm: dict,
                 docker: Callable[..., object]) -> dict:
    net = _single(docker(["network", "inspect", name]))
    if net.get("Name") != name or net.get("Driver") != "bridge":
        raise Denied("Untrusted Docker network identity")
    if name == NETWORK:
        if net.get("Internal") is not True:
            raise Denied("AURA VM network not internal")
        if (vm.get("NetworkSettings") or {}).get("Networks", {}).get(NETWORK, {}).get("NetworkID") != net.get("Id"):
            raise Denied("AURA VM attached to unexpected internal network")
    elif name == INGRESS + run_id:
        if (net.get("Labels") != {RUN_LABEL: run_id, "aura.osworld.purpose": "loopback-ingress"}
                or net.get("Internal") is not False or net.get("EnableIPv6") is not False):
            raise Denied("Ingress network not owned by pinned run")
        gateway = _get_gateway(run_id, docker)
        gateway_nets = (gateway.get("NetworkSettings") or {}).get("Networks") or {}
        if (gateway_nets.get(name, {}).get("NetworkID") != net.get("Id")
                or gateway_nets.get(NETWORK, {}).get("NetworkID") !=
                   (vm.get("NetworkSettings") or {}).get("Networks", {}).get(NETWORK, {}).get("NetworkID")):
            raise Denied("Ingress network not attached to measured gateway")
    else:
        raise Denied("Arbitrary network")
    return net


def _get_gateway(run_id: str, docker: Callable[..., object]) -> dict:
    name = GATEWAY + run_id
    obj = _single(docker(["inspect", name]))
    labels = (obj.get("Config") or {}).get("Labels")
    nets = (obj.get("NetworkSettings") or {}).get("Networks") or {}
    if (obj.get("Name") != "/" + name
            or type(obj.get("Id")) is not str or HEX64.fullmatch(obj["Id"]) is None
            or labels != {RUN_LABEL: run_id, "aura.osworld.role": "loopback-gateway"}
            or (obj.get("State") or {}).get("Running") is not True
            or set(nets) != {NETWORK, INGRESS + run_id}):
        raise Denied("Gateway not owned by pinned run")
    return obj


def _get_volume(run_id: str, vm: dict, docker: Callable[..., object]) -> dict:
    name = STORAGE + run_id
    volume = _single(docker(["volume", "inspect", name]))
    mounts = vm.get("Mounts") or []
    if (volume.get("Name") != name or volume.get("Driver") != "local"
            or volume.get("Labels") != {RUN_LABEL: run_id, "aura.osworld.purpose": "vm-storage"}
            or sum(m.get("Destination") == "/storage" and m.get("Name") == name
                   and m.get("Type") == "volume" for m in mounts if type(m) is dict) != 1):
        raise Denied("Volume not owned/mounted by pinned VM")
    return volume


def _trusted_gateway_address(requested: str, run_id: str, vm_id: str, vm: dict,
                             docker: Callable[..., object]) -> bool:
    internal = _get_network(NETWORK, run_id, vm_id, vm, docker)
    ingress = _get_network(INGRESS + run_id, run_id, vm_id, vm, docker)
    _get_gateway(run_id, docker)
    # Inspect two authoritative bridge gateway fields; never use a caller's
    # private IP as sufficient proof by itself.
    ips = set()
    for net in (internal, ingress):
        for item in (net.get("IPAM") or {}).get("Config") or []:
            if type(item) is dict and type(item.get("Gateway")) is str:
                ips.add(item["Gateway"])
    return requested in ips


def execute(data: dict[str, object], *, docker: Callable[..., object] = docker_json) -> object:
    run_id, vm_id = data["run_id"], data["vm_id"]
    vm = _get_vm(run_id, vm_id, docker)
    op, target = data["operation"], data["target"]
    if op == "inspect_container":
        return [vm]
    if op == "inspect_gateway":
        return [_get_gateway(run_id, docker)]
    if op == "inspect_network":
        return [_get_network(target, run_id, vm_id, vm, docker)]
    if op == "inspect_volume":
        return [_get_volume(run_id, vm, docker)]
    if op != "probe":
        raise Denied("Unapproved Docker operation")
    # Network probes may share the AURA VM namespace or the run-owned
    # dual-homed gateway namespace. Do not accept other container IDs.
    if target != vm_id and _get_gateway(run_id, docker).get("Id") != target:
        raise Denied("Probe container is not the measured VM/gateway")
    name = data["probe_name"]
    if name == "host_gateway_blocked":
        if not _trusted_gateway_address(data["gateway_ip"], run_id, vm_id, vm, docker):
            raise Denied("Gateway IP does not belong to measured network")
        kind, host, port = "tcp4", data["gateway_ip"], data["port"]
    else:
        kind, host, port = TARGETS[name]
    spec = json.dumps({"name": name, "kind": kind, "host": host, "port": port},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    value = docker([
        "run", "--rm", "--pull", "never", "--network", "container:" + target,
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--user", "65534:65534", "--pids-limit", "32",
        "--memory", "64m", "--entrypoint", "python3", PROBE_IMAGE,
        "-I", "-S", "-B", "-c", _PROBE_CODE, spec,
    ], timeout=30)
    if (type(value) is not dict or set(value) != {"schema", "name", "errno", "blocked"}
            or value["schema"] != PROBE_SCHEMA or value["name"] != name
            or type(value["errno"]) is not int or type(value["blocked"]) is not bool):
        raise Denied("Untrusted negative probe result")
    # A timeout, refused connection or wrong type never proves egress denial.
    return {**value, "blocked": value["blocked"] is True and value["errno"] in BLOCK_ERRNOS}


def process_request(raw: bytes, *, claim_nonce: Callable[..., bool],
                    docker: Callable[..., object] = docker_json, now: int | None = None) -> bytes:
    data = parse_request(raw, now=now)
    if claim_nonce(data["nonce"], data["run_id"], data["vm_id"]) is not True:
        raise Denied("Replayed or invalid nonce")
    result = execute(data, docker=docker)
    envelope = {"schema": RESPONSE_SCHEMA, "operation": data["operation"],
                "nonce": data["nonce"], "result": result}
    response = json.dumps(envelope, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(response) > MAX_RESPONSE:
        raise Denied("Unbounded Docker response")
    return response
