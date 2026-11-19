"""F2.3-A: narrow Docker Engine operations and fail-closed active egress probes.

A service-owned Docker CLI/config is the only supported execution path.
The caller can choose a *validated* container ID, audit operation and inspected
gateway IP. No arbitrary Docker args, images, mounts or shell fragments.

This backend must run only inside the separately provisioned broker identity.
It never grants daemon access, signs an isolation receipt or installs Docker.
"""
from __future__ import annotations

import errno
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
from collections.abc import Callable
from typing import Any

from .audit_broker_protocol import BrokerDenied
from . import network_audit

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_PIN = re.compile(r"[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}\Z")

DOCKER_EXE = Path(r"D:\Apps\DockerDesktop\resources\bin\docker.exe")
DOCKER_CONFIG = Path(r"D:\AURA\Trust\DockerBroker\policy\docker-config")
DOCKER_CONTEXT = "desktop-linux"
# Reuse the already pinned Python-Alpine digest from the reviewed gateway policy;
# no floating Alpine tag or unverified newly invented sha256 is accepted.
PROBE_IMAGE = network_audit.GATEWAY_IMAGE
MAX_OUTPUT = 2_000_000
MAX_PROBE_OUTPUT = 1024
PROBE_TIMEOUT = 30
READ_TIMEOUT = 20
PROBE_SCHEMA = "aura.osworld.network-probe.v1"
GATEWAY_PORTS = (22, 80, 443, 2375, 2376)
_DEFAULT_TARGETS = {
    "egress_v4_blocked": ("tcp4", "1.1.1.1", 443),
    "metadata_blocked": ("tcp4", "169.254.169.254", 80),
    # UDP connect checks a real OS route toward the external DNS server.
    # It is deliberately conservative: reachable or timed-out => NOT PROVEN.
    "external_dns_blocked": ("udp4", "8.8.8.8", 53),
    "ipv6_blocked": ("tcp6", "2606:4700:4700::1111", 443),
}
# Only explicit OS policy/routing denial is evidence. Connection refused,
# successful UDP route, read timeout, DNS resolver error or a missing tool
# is never proof of network isolation.
_BLOCK_ERRNOS = frozenset((
    errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EPERM, errno.EACCES,
    errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL,
))
# Run with a digest-pinned Python image. The immutable code prints a typed
# result, never a success string synthesized by a failing shell command.
_PROBE_CODE = """
import errno, json, socket, sys
spec = json.loads(sys.argv[1])
family = socket.AF_INET6 if spec["kind"] == "tcp6" else socket.AF_INET
type_ = socket.SOCK_DGRAM if spec["kind"] == "udp4" else socket.SOCK_STREAM
allowed = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EPERM, errno.EACCES,
           errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL}
with socket.socket(family, type_) as sock:
    sock.settimeout(3)
    try:
        result = sock.connect_ex((spec["host"], spec["port"]))
    except OSError as exc:
        result = exc.errno
if type(result) is not int:
    sys.exit(4)
print(json.dumps({"schema": "aura.osworld.network-probe.v1",
                  "name": spec["name"], "errno": result,
                  "blocked": result in allowed},
                 sort_keys=True, separators=(",", ":")))
"""


def _valid_id(value: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise BrokerDenied("Full 64-character container ID required")
    return value


def _valid_network(value: str) -> str:
    if type(value) is not str:
        raise BrokerDenied("Unexpected Docker network")
    if value == network_audit.NETWORK_NAME:
        return value
    for prefix in (network_audit.INGRESS_PREFIX,):
        suffix = value.removeprefix(prefix)
        if value.startswith(prefix) and _HEX32.fullmatch(suffix):
            return value
    raise BrokerDenied("Unexpected Docker network")


def _valid_volume(value: str) -> str:
    prefix = network_audit.STORAGE_VOLUME_PREFIX
    if type(value) is str and value.startswith(prefix) and _HEX32.fullmatch(value[len(prefix):]):
        return value
    raise BrokerDenied("Unexpected Docker volume")


def _trusted_docker_environment() -> dict[str, str]:
    """Never inherit DOCKER_HOST/TLS_CERT_PATH/CLI plugin or shell overrides."""
    keys = ("SYSTEMROOT", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP")
    return {key: os.environ[key] for key in keys if key in os.environ}


class DockerAuditBackend:
    """Bounded allowlisted inspect and negative-probe Docker operations."""

    def __init__(
        self,
        *,
        executable: Path = DOCKER_EXE,
        runner: Callable[..., Any] = subprocess.run,
    ):
        if not isinstance(executable, Path) or str(executable).lower() != str(DOCKER_EXE).lower():
            raise BrokerDenied("Docker executable does not match pinned D: path")
        if _PIN.fullmatch(PROBE_IMAGE) is None:
            raise BrokerDenied("Probe image must have immutable OCI SHA-256")
        if os.name == "nt" and runner is subprocess.run:
            if not executable.is_file() or executable.is_symlink():
                raise BrokerDenied("Pinned Docker CLI missing or redirected")
            from aura_core.evolution.windows_owner_storage import require_private_acl
            require_private_acl(DOCKER_CONFIG)
        self._exe = str(executable)
        self._runner = runner

    def _invoke(self, args: list[str], *, timeout: int) -> subprocess.CompletedProcess:
        # Explicit service-owned Docker config + context. AURA/agent env cannot
        # redirect commands to arbitrary DOCKER_HOST or DOCKER_CONTEXT.
        command = [
            self._exe, "--config", str(DOCKER_CONFIG), "--context", DOCKER_CONTEXT, *args,
        ]
        try:
            process = self._runner(
                command, check=False, capture_output=True, text=True,
                shell=False, timeout=timeout, env=_trusted_docker_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrokerDenied("Docker inspection/probe unavailable") from exc
        if (type(process.returncode) is not int or process.returncode != 0
                or type(process.stdout) is not str
                or type(process.stderr) is not str
                or len(process.stdout) > MAX_OUTPUT
                or len(process.stderr) > 8192):
            raise BrokerDenied("Docker inspection/probe failed")
        return process

    def inspect_container(self, container_id: str) -> object:
        return self._json(["inspect", _valid_id(container_id)])

    def inspect_gateway(self, run_id: str) -> object:
        if type(run_id) is not str or not _HEX32.fullmatch(run_id):
            raise BrokerDenied("Invalid run identifier")
        return self._json(["inspect", network_audit.GATEWAY_PREFIX + run_id])

    def inspect_network(self, name: str) -> object:
        return self._json(["network", "inspect", _valid_network(name)])

    def inspect_volume(self, name: str) -> object:
        return self._json(["volume", "inspect", _valid_volume(name)])

    def _json(self, args: list[str]) -> object:
        try:
            return json.loads(self._invoke(args, timeout=READ_TIMEOUT).stdout)
        except json.JSONDecodeError as exc:
            raise BrokerDenied("Malformed Docker inspection result") from exc

    def policy_inspect(self, argv: list[str]) -> object:
        """Only the exhaustive network_audit policy may request these commands."""
        if type(argv) is not list or any(type(a) is not str for a in argv):
            raise BrokerDenied("Malformed internal Docker inspection")
        if len(argv) == 2 and argv[0] == "inspect":
            if _HEX64.fullmatch(argv[1]):
                return self.inspect_container(argv[1])
            prefix = network_audit.GATEWAY_PREFIX
            if argv[1].startswith(prefix) and _HEX32.fullmatch(argv[1][len(prefix):]):
                return self.inspect_gateway(argv[1][len(prefix):])
        if len(argv) == 3 and argv[0:2] == ["network", "inspect"]:
            return self.inspect_network(argv[2])
        if len(argv) == 3 and argv[0:2] == ["volume", "inspect"]:
            return self.inspect_volume(argv[2])
        raise BrokerDenied("Docker inspect operation violates the audit allowlist")

    def _one_probe(self, container_id: str, *, name: str, kind: str, host: str, port: int) -> bool:
        spec = json.dumps(
            {"name": name, "kind": kind, "host": host, "port": port},
            sort_keys=True, separators=(",", ":"),
        )
        argv = [
            "run", "--rm", "--pull", "never",
            "--network", "container:" + container_id,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--read-only", "--user", "65534:65534",
            "--pids-limit", "32", "--memory", "64m",
            "--entrypoint", "python3",
            PROBE_IMAGE, "-I", "-S", "-B", "-c", _PROBE_CODE, spec,
        ]
        try:
            output = self._invoke(argv, timeout=PROBE_TIMEOUT).stdout
            if len(output) > MAX_PROBE_OUTPUT:
                return False
            result = json.loads(output)
            return (
                type(result) is dict
                and set(result) == {"schema", "name", "errno", "blocked"}
                and result["schema"] == PROBE_SCHEMA
                and result["name"] == name
                and type(result["errno"]) is int
                and result["errno"] in _BLOCK_ERRNOS
                and result["blocked"] is True
            )
        except (BrokerDenied, ValueError, TypeError, json.JSONDecodeError):
            return False

    def fixed_probe(self, *, container_id: str, name: str, gateway_ip: str | None = None) -> bool:
        _valid_id(container_id)
        if name == "host_gateway_blocked":
            try:
                ip = ipaddress.IPv4Address(gateway_ip)
            except (ValueError, TypeError) as exc:
                raise BrokerDenied("Invalid inspected gateway address") from exc
            if not ip.is_private or ip.is_loopback or ip.is_link_local:
                raise BrokerDenied("Gateway violates internal network policy")
            return all(
                self._one_probe(container_id, name=name, kind="tcp4", host=str(ip), port=p)
                for p in GATEWAY_PORTS
            )
        if type(name) is not str or name not in _DEFAULT_TARGETS or gateway_ip is not None:
            raise BrokerDenied("Unapproved negative probe")
        kind, host, port = _DEFAULT_TARGETS[name]
        return self._one_probe(container_id, name=name, kind=kind, host=host, port=port)
