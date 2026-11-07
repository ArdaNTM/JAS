"""F2.6 INACTIVE Linux OpenSSH forced-command Docker audit worker.

Python 3.12 stdlib only. Future operator provisioning MUST install this file as
root-owned and non-writable to the restricted SSH principal and restrict a
single SSH public key to this command; the SSH user must NOT join docker.
No installation, sudoers or authorization is performed by this file.

Invoked only after an independently reviewed deployment, through a forced
command with SSH_ORIGINAL_COMMAND=aura-osworld-transport-v1. This process
requires a separately locked-down service identity to access the root-owned
Unix Docker socket. All Docker operations are generated from a strict allowlist.
"""
from __future__ import annotations

import errno
import ipaddress
import json
import os
import re
import subprocess
import sys
import time

REQUEST_SCHEMA = "aura.osworld.ubuntu-transport.request.v1"
RESPONSE_SCHEMA = "aura.osworld.ubuntu-transport.response.v1"
REMOTE_COMMAND = "aura-osworld-transport-v1"
DOCKER = "/usr/bin/docker"
DOCKER_SOCKET = "unix:///var/run/docker.sock"
DOCKER_CONFIG = "/var/empty"
NETWORK = "aura-osworld-v21-lab"
INGRESS = "aura-osworld-v21-ingress-"
GATEWAY = "aura-osworld-v21-gateway-"
STORAGE = "aura-osworld-v21-storage-"
# Must remain equal to aura_core.osworld.network_audit.GATEWAY_IMAGE.
PROBE_IMAGE = "python:3.12.16-alpine@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TARGETS = {
    "egress_v4_blocked": ("tcp4", "1.1.1.1", 443),
    "metadata_blocked": ("tcp4", "169.254.169.254", 80),
    "external_dns_blocked": ("udp4", "8.8.8.8", 53),
    "ipv6_blocked": ("tcp6", "2606:4700:4700::1111", 443),
}
GATEWAY_PORTS = (22, 80, 443, 2375, 2376)
MAX_REQUEST = 1024
MAX_STDOUT = 2_000_000
BLOCK_ERRNOS = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EPERM,
                errno.EACCES, errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL}
_PROBE_CODE = """
import errno,json,socket,sys
spec=json.loads(sys.argv[1])
fam=socket.AF_INET6 if spec["kind"]=="tcp6" else socket.AF_INET
typ=socket.SOCK_DGRAM if spec["kind"]=="udp4" else socket.SOCK_STREAM
with socket.socket(fam,typ) as s:
 s.settimeout(3)
 try: rc=s.connect_ex((spec["host"],spec["port"]))
 except OSError as exc: rc=exc.errno
print(json.dumps({"schema":"aura.osworld.network-probe.v1","name":spec["name"],
                  "errno":rc,"blocked":rc in {101,113,1,13,97,99}},separators=(",",":")))
"""


class Denied(Exception):
    pass


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, val in pairs:
        if key in data:
            raise Denied("duplicate field")
        data[key] = val
    return data


def parse_request(raw: bytes, *, now: int | None = None) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST:
        raise Denied("invalid request length")
    try:
        data = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Denied("nonfinite")))
    except (UnicodeError, ValueError) as exc:
        raise Denied("invalid request JSON") from exc
    keys = {"schema", "operation", "target", "nonce", "issued_at", "probe_name", "gateway_ip", "port"}
    if type(data) is not dict or set(data) != keys or data["schema"] != REQUEST_SCHEMA:
        raise Denied("unsupported request")
    op, target = data["operation"], data["target"]
    if (type(op) is not str or op not in {"inspect_container", "inspect_gateway", "inspect_network", "inspect_volume", "probe"}
            or type(target) is not str or type(data["nonce"]) is not str
            or HEX32.fullmatch(data["nonce"]) is None or type(data["issued_at"]) is not int):
        raise Denied("unsupported identity")
    current = int(time.time()) if now is None else now
    if not current - 30 <= data["issued_at"] <= current + 5:
        raise Denied("stale request")
    name, gateway_ip, port = data["probe_name"], data["gateway_ip"], data["port"]
    if op == "inspect_container" or op == "probe":
        if HEX64.fullmatch(target) is None:
            raise Denied("container id not pinned")
    elif op == "inspect_gateway":
        if not target.startswith(GATEWAY) or HEX32.fullmatch(target[len(GATEWAY):]) is None:
            raise Denied("gateway name not allowed")
    elif op == "inspect_network":
        if target != NETWORK and not (target.startswith(INGRESS) and HEX32.fullmatch(target[len(INGRESS):])):
            raise Denied("network name not allowed")
    elif op == "inspect_volume":
        if not target.startswith(STORAGE) or HEX32.fullmatch(target[len(STORAGE):]) is None:
            raise Denied("volume name not allowed")
    if op != "probe":
        if any(x is not None for x in (name, gateway_ip, port)):
            raise Denied("inspection flags forbidden")
    elif name == "host_gateway_blocked":
        try:
            addr = ipaddress.IPv4Address(gateway_ip)
        except (TypeError, ValueError) as exc:
            raise Denied("invalid gateway") from exc
        if (not addr.is_private or addr.is_loopback or addr.is_link_local
                or type(port) is not int or port not in GATEWAY_PORTS):
            raise Denied("unapproved gateway probe")
        data["gateway_ip"] = str(addr)
    elif type(name) is not str or name not in TARGETS or gateway_ip is not None or port is not None:
        raise Denied("unapproved negative probe")
    return data


def _docker(args: list[str], *, timeout: int = 20) -> object:
    if not os.path.isfile(DOCKER) or os.path.islink(DOCKER):
        raise Denied("pinned Docker executable missing")
    command = [DOCKER, "--host", DOCKER_SOCKET, "--config", DOCKER_CONFIG, *args]
    try:
        proc = subprocess.run(command, shell=False, check=False,
                              capture_output=True, timeout=timeout,
                              env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LANG": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Denied("Docker unavailable") from exc
    if proc.returncode != 0 or len(proc.stdout) > MAX_STDOUT or len(proc.stderr) > 4096:
        raise Denied("Docker operation unsuccessful")
    try:
        return json.loads(proc.stdout)
    except (UnicodeDecodeError, ValueError) as exc:
        raise Denied("Malformed Docker JSON") from exc


def _require_aura_container(container: str) -> None:
    info = _docker(["inspect", container])
    if type(info) is not list or len(info) != 1 or type(info[0]) is not dict:
        raise Denied("untrusted container")
    obj = info[0]
    labels = (obj.get("Config") or {}).get("Labels") or {}
    run_id = labels.get("aura.osworld.run_id")
    if obj.get("Id") != container or type(run_id) is not str or HEX32.fullmatch(run_id) is None \
            or (obj.get("State") or {}).get("Running") is not True:
        raise Denied("container is not a running AURA-owned VM")


def execute(data: dict[str, object]) -> object:
    operation, target = data["operation"], data["target"]
    if operation == "inspect_container":
        _require_aura_container(target)
        return _docker(["inspect", target])
    if operation == "inspect_gateway":
        return _docker(["inspect", target])
    if operation == "inspect_network":
        return _docker(["network", "inspect", target])
    if operation == "inspect_volume":
        return _docker(["volume", "inspect", target])
    if operation != "probe":
        raise Denied("unapproved operation")
    _require_aura_container(target)
    name = data["probe_name"]
    if name == "host_gateway_blocked":
        kind, host, port = "tcp4", data["gateway_ip"], data["port"]
    else:
        kind, host, port = TARGETS[name]
    spec = json.dumps({"name": name, "kind": kind, "host": host, "port": port},
                      sort_keys=True, separators=(",", ":"))
    result = _docker([
        "run", "--rm", "--pull", "never", "--network", "container:" + target,
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--user", "65534:65534", "--pids-limit", "32",
        "--memory", "64m", "--entrypoint", "python3", PROBE_IMAGE,
        "-I", "-S", "-B", "-c", _PROBE_CODE, spec,
    ], timeout=30)
    if (type(result) is not dict or set(result) != {"schema", "name", "errno", "blocked"}
            or result["schema"] != "aura.osworld.network-probe.v1"
            or result["name"] != name or type(result["errno"]) is not int
            or type(result["blocked"]) is not bool):
        raise Denied("invalid negative probe evidence")
    # A successful connect, refused connection or timeout is not a denial.
    result["blocked"] = result["blocked"] is True and result["errno"] in BLOCK_ERRNOS
    return result


def main() -> int:
    # sshd's forced command must ignore any caller command; require exactly our
    # literal marker so changing the SSH command cannot access a shell.
    if os.environ.get("SSH_ORIGINAL_COMMAND") != REMOTE_COMMAND:
        return 2
    if os.geteuid() != 0:
        return 2
    try:
        data = parse_request(sys.stdin.buffer.read(MAX_REQUEST + 1))
        value = execute(data)
        envelope = {"schema": RESPONSE_SCHEMA, "operation": data["operation"],
                    "nonce": data["nonce"], "result": value}
        output = json.dumps(envelope, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(output) > MAX_STDOUT:
            raise Denied("oversized response")
        sys.stdout.buffer.write(output)
        return 0
    except (Denied, OSError, ValueError, TypeError, KeyError):
        # Never echo Docker errors, secrets or credentials to SSH client.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
