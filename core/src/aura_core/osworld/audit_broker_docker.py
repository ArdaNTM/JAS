"""Constrained Docker CLI primitives for an independently protected broker.

Only narrow inspect operations and hard-coded negative probes are exposed.
This is a building block: it MUST be used with the full network_audit topology
policy, independently authenticated service identity and signed measurements.
"""
from __future__ import annotations

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

DOCKER_EXE = Path(r"D:\Apps\DockerDesktop\resources\bin\docker.exe")
MAX_OUTPUT = 2_000_000
PROBE_TIMEOUT = 30
READ_TIMEOUT = 20

# Only these fixed scripts may execute. No caller-provided command or shell.
_PROBES = {
    "egress_v4_blocked": "if nc -z -w 3 1.1.1.1 443 >/dev/null 2>&1; then exit 3; else printf AURA_DENIED; fi",
    "metadata_blocked": "if nc -z -w 3 169.254.169.254 80 >/dev/null 2>&1; then exit 3; else printf AURA_DENIED; fi",
    "external_dns_blocked": "if timeout 5 nslookup example.com 8.8.8.8 >/dev/null 2>&1; then exit 3; else printf AURA_DENIED; fi",
    "ipv6_blocked": "if ip -6 route show default | grep -q default; then exit 3; else printf AURA_DENIED; fi",
}


def _valid_id(value: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise BrokerDenied("Full 64-character container ID required")
    return value


def _valid_network(value: str) -> str:
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


class DockerAuditBackend:
    """Enforce a pinned executable and fixed command construction."""

    def __init__(
        self,
        *,
        executable: Path = DOCKER_EXE,
        runner: Callable[..., Any] = subprocess.run,
    ):
        if not isinstance(executable, Path) or str(executable).lower() != str(DOCKER_EXE).lower():
            raise BrokerDenied("Docker executable does not match pinned D: path")
        if os.name == "nt" and runner is subprocess.run and (not executable.is_file() or executable.is_symlink()):
            raise BrokerDenied("Pinned Docker CLI is missing or redirected")
        self._exe = str(executable)
        self._runner = runner

    def _invoke(self, args: list[str], *, timeout: int) -> subprocess.CompletedProcess:
        try:
            process = self._runner(
                [self._exe, *args],
                check=False, capture_output=True, text=True,
                shell=False, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrokerDenied("Docker inspection/probe unavailable") from exc
        if (process.returncode != 0 or len(process.stdout) > MAX_OUTPUT
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

    def fixed_probe(
        self,
        *,
        container_id: str,
        name: str,
        gateway_ip: str | None = None,
    ) -> bool:
        _valid_id(container_id)
        if name == "host_gateway_blocked":
            try:
                addr = ipaddress.IPv4Address(gateway_ip)
            except (ValueError, TypeError) as exc:
                raise BrokerDenied("Invalid inspected gateway address") from exc
            if not addr.is_private or addr.is_loopback or addr.is_link_local:
                raise BrokerDenied("Gateway address violates internal network policy")
            script = (
                "for p in 22 80 443 2375 2376; do "
                f"if nc -z -w 3 {addr} $p >/dev/null 2>&1; "
                "then exit 3; fi; done; printf AURA_DENIED"
            )
        else:
            if type(name) is not str or name not in _PROBES:
                raise BrokerDenied("Unapproved negative probe")
            if gateway_ip is not None:
                raise BrokerDenied("Unexpected gateway IP")
            script = _PROBES[name]
        argv = [
            "run", "--rm", "--network", "container:" + container_id,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "32", "--memory", "64m",
            network_audit.ALPINE, "sh", "-eu", "-c", script,
        ]
        try:
            result = self._invoke(argv, timeout=PROBE_TIMEOUT)
            return result.stdout.strip() == "AURA_DENIED"
        except BrokerDenied:
            return False
