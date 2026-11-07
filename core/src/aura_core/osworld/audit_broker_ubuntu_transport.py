"""INACTIVE F2.6 Ubuntu audit transport, isolated from Windows Docker Desktop.

No SCM route calls this module. It requires an independently approved future
audit_only service policy; the shipped deny_only parser cannot activate it.
The remote root helper verifies Linux SO_PEERCRED, nonce and exact run/VM
ownership before every Docker inspect/probe. Agent input never controls SSH or
Docker executable, host, user, command, image, mount or arbitrary arguments.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from types import SimpleNamespace
from typing import Any, Callable

from .audit_broker_protocol import BrokerDenied
from .audit_broker_docker import (
    DockerAuditBackend, GATEWAY_PORTS, MAX_OUTPUT, READ_TIMEOUT,
    PROBE_TIMEOUT, _BLOCK_ERRNOS, _DEFAULT_TARGETS,
)
from .audit_broker_service import (
    TRUST_ROOT, BrokerServicePolicy, load_service_policy,
    validate_service_identity, verify_trusted_runtime,
)
from .audit_broker_scm_identity import verify_registered_service_account
from .audit_broker_windows import current_process_sid
from . import network_audit

REQUEST_SCHEMA = "aura.osworld.ubuntu-transport.request.v2"
RESPONSE_SCHEMA = "aura.osworld.ubuntu-transport.response.v2"
SSH_EXE = Path(r"C:\Windows\System32\OpenSSH\ssh.exe")
SSH_KEY = TRUST_ROOT / "keys" / "ubuntu-transport-ed25519"
KNOWN_HOSTS = TRUST_ROOT / "policy" / "ubuntu-known-hosts"
REMOTE_IP = "192.168.247.2"
REMOTE_USER = "aura-transport"
REMOTE_COMMAND = "aura-osworld-transport-v1"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED = frozenset({"inspect_container", "inspect_gateway", "inspect_network", "inspect_volume", "probe"})
MAX_REQUEST = 1400


def _pinned(value: str, pattern: re.Pattern[str], what: str) -> None:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise BrokerDenied("Invalid Ubuntu broker " + what)


def make_request(operation: str, target: str, *, run_id: str, vm_id: str,
                 nonce: str, issued_at: int, probe_name: str | None = None,
                 gateway_ip: str | None = None, port: int | None = None) -> bytes:
    """Return an exact, bounded JSON message with no caller-chosen Docker args."""
    _pinned(run_id, _HEX32, "run")
    _pinned(vm_id, _HEX64, "VM")
    _pinned(nonce, _HEX32, "nonce")
    if type(issued_at) is not int:
        raise BrokerDenied("Invalid Ubuntu transport timestamp")
    if type(operation) is not str or operation not in _ALLOWED or type(target) is not str:
        raise BrokerDenied("Unapproved Ubuntu operation")
    allowed = {
        "inspect_container": {vm_id},
        "inspect_gateway": {network_audit.GATEWAY_PREFIX + run_id},
        "inspect_network": {network_audit.NETWORK_NAME, network_audit.INGRESS_PREFIX + run_id},
        "inspect_volume": {network_audit.STORAGE_VOLUME_PREFIX + run_id},
        "probe": {vm_id},
    }
    # The dual-homed relay is a separate container whose full ID is learned
    # from the verified gateway inspect; the Linux helper checks its identity.
    if operation == "probe":
        _pinned(target, _HEX64, "probe container")
    elif target not in allowed[operation]:
        raise BrokerDenied("Target does not belong to pinned OSWorld run")
    if operation == "probe":
        if type(probe_name) is not str or probe_name not in {*_DEFAULT_TARGETS, "host_gateway_blocked"}:
            raise BrokerDenied("Unapproved fixed probe")
        if probe_name == "host_gateway_blocked":
            try:
                addr = ipaddress.IPv4Address(gateway_ip)
            except (TypeError, ValueError) as exc:
                raise BrokerDenied("Invalid gateway address") from exc
            if not addr.is_private or addr.is_loopback or addr.is_link_local \
                    or type(port) is not int or port not in GATEWAY_PORTS:
                raise BrokerDenied("Unapproved gateway probe target")
            gateway_ip = str(addr)
        elif gateway_ip is not None or port is not None:
            raise BrokerDenied("Probe target cannot be overridden")
    elif any(x is not None for x in (probe_name, gateway_ip, port)):
        raise BrokerDenied("Unexpected inspection parameters")
    request = {
        "schema": REQUEST_SCHEMA, "operation": operation, "target": target,
        "run_id": run_id, "vm_id": vm_id, "nonce": nonce, "issued_at": issued_at,
        "probe_name": probe_name, "gateway_ip": gateway_ip, "port": port,
    }
    raw = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_REQUEST:
        raise BrokerDenied("Oversized Ubuntu transport request")
    return raw


def parse_response(raw: bytes, *, nonce: str, operation: str) -> object:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_OUTPUT:
        raise BrokerDenied("Invalid Ubuntu response bounds")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise BrokerDenied("Duplicate Ubuntu response field")
            out[key] = value
        return out
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(BrokerDenied("Nonfinite reply")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Malformed Ubuntu response") from exc
    if (type(data) is not dict
            or set(data) != {"schema", "operation", "nonce", "result"}
            or data["schema"] != RESPONSE_SCHEMA
            or data["operation"] != operation or data["nonce"] != nonce):
        raise BrokerDenied("Wrong protocol, operation or nonce")
    result = data["result"]
    if operation == "probe":
        if (type(result) is not dict
                or set(result) != {"schema", "name", "errno", "blocked"}
                or result["schema"] != "aura.osworld.network-probe.v1"
                or type(result["name"]) is not str or type(result["errno"]) is not int
                or type(result["blocked"]) is not bool):
            raise BrokerDenied("Invalid probe response")
    elif type(result) is not list or len(result) != 1 or type(result[0]) is not dict:
        raise BrokerDenied("Invalid inspect response")
    return result


def _verify_pinned_known_hosts(data: bytes) -> None:
    try:
        rows = data.decode("ascii").strip().splitlines()
        if len(rows) != 1:
            raise ValueError("Expected one pinned host")
        fields = rows[0].split()
        if len(fields) != 3 or fields[:2] != [REMOTE_IP, "ssh-ed25519"]:
            raise ValueError("Unpinned host identity")
        key = base64.b64decode(fields[2], validate=True)
        if len(key) != 51 or key[:15] != b"\x00\x00\x00\x0bssh-ed25519" or key[15:19] != b"\x00\x00\x00 ":
            raise ValueError("Invalid Ed25519 host public key")
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise BrokerDenied("Ubuntu SSH host key not independently pinned") from exc


def _require_sealed_ssh_files() -> None:
    if os.name != "nt":
        raise BrokerDenied("SSH transport requires a real Windows broker")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    for p in (SSH_EXE, SSH_KEY, KNOWN_HOSTS):
        if not p.is_absolute() or not p.is_file() or p.is_symlink():
            raise BrokerDenied("Pinned SSH executable or trust file unavailable")
    for p in (SSH_KEY, KNOWN_HOSTS, SSH_KEY.parent, KNOWN_HOSTS.parent):
        require_private_acl(p)
    if SSH_KEY.stat().st_size > 8192 or KNOWN_HOSTS.stat().st_size > 4096:
        raise BrokerDenied("Oversized SSH trust material")
    _verify_pinned_known_hosts(KNOWN_HOSTS.read_bytes())


def _trusted_env() -> dict[str, str]:
    return {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ}


def _ssh_argv() -> list[str]:
    return [str(SSH_EXE), "-F", "none", "-T", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "UpdateHostKeys=no",
            "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
            "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
            "-o", "PermitLocalCommand=no", "-o", "ProxyCommand=none",
            "-o", "ProxyJump=none", "-o", "LogLevel=ERROR",
            "-o", "UserKnownHostsFile=" + str(KNOWN_HOSTS),
            "-o", "GlobalKnownHostsFile=none", "-i", str(SSH_KEY),
            "-l", REMOTE_USER, "--", REMOTE_IP, REMOTE_COMMAND]


def _production_preflight() -> None:
    """No real SSH call is authorized by the shipped deny_only SCM policy."""
    verify_trusted_runtime(source_file=Path(__file__), python_executable=Path(os.sys.executable))
    policy = load_service_policy()
    if type(policy) is not BrokerServicePolicy or policy.mode != "audit_only":
        raise BrokerDenied("Operator-reviewed Ubuntu audit activation missing")
    validate_service_identity(policy, actual_sid=current_process_sid())
    verify_registered_service_account(policy)
    _require_sealed_ssh_files()


class UbuntuBrokerSshTransport:
    """Future broker-only caller. No agent IPC route or activation exists."""

    def __init__(self, *, runner: Callable[..., Any] = subprocess.run) -> None:
        self._runner = runner

    def exchange(self, operation: str, target: str, *, run_id: str, vm_id: str,
                 probe_name: str | None = None, gateway_ip: str | None = None,
                 port: int | None = None) -> object:
        raw_nonce = secrets.token_hex(16)
        raw = make_request(operation, target, run_id=run_id, vm_id=vm_id,
                           nonce=raw_nonce, issued_at=int(time.time()),
                           probe_name=probe_name, gateway_ip=gateway_ip, port=port)
        _production_preflight()
        try:
            result = self._runner(
                _ssh_argv(), input=raw, shell=False, check=False,
                capture_output=True, timeout=READ_TIMEOUT if operation != "probe" else PROBE_TIMEOUT,
                env=_trusted_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrokerDenied("Ubuntu broker SSH unavailable") from exc
        if (type(result.returncode) is not int or result.returncode != 0
                or type(result.stdout) is not bytes or len(result.stdout) > MAX_OUTPUT
                or type(result.stderr) is not bytes or len(result.stderr) > 4096):
            raise BrokerDenied("Ubuntu transport request failed closed")
        return parse_response(result.stdout, nonce=raw_nonce, operation=operation)


class UbuntuDockerAuditBackend(DockerAuditBackend):
    """Bound to one exact run and VM, compatible with complete topology audits."""

    def __init__(self, *, transport: UbuntuBrokerSshTransport,
                 run_id: str, vm_id: str) -> None:
        if type(transport) is not UbuntuBrokerSshTransport:
            raise BrokerDenied("Untrusted Ubuntu transport instance")
        _pinned(run_id, _HEX32, "run")
        _pinned(vm_id, _HEX64, "VM")
        self._transport = transport
        self._run_id = run_id
        self._vm_id = vm_id
        self._gateway_id: str | None = None

    def _invoke(self, args: list[str], *, timeout: int) -> SimpleNamespace:
        if type(args) is not list or any(type(x) is not str for x in args):
            raise BrokerDenied("Invalid internal Docker operation")
        if len(args) == 2 and args[0] == "inspect":
            operation = "inspect_container" if args[1] == self._vm_id else "inspect_gateway"
            target = args[1]
        elif len(args) == 3 and args[:2] == ["network", "inspect"]:
            operation, target = "inspect_network", args[2]
        elif len(args) == 3 and args[:2] == ["volume", "inspect"]:
            operation, target = "inspect_volume", args[2]
        else:
            raise BrokerDenied("Docker action does not match read-only audit allowlist")
        reply = self._transport.exchange(operation, target, run_id=self._run_id, vm_id=self._vm_id)
        if operation == "inspect_gateway" and type(reply) is list and len(reply) == 1:
            item = reply[0]
            if type(item) is not dict or type(item.get("Id")) is not str:
                raise BrokerDenied("Gateway inspect returned no full ID")
            _pinned(item["Id"], _HEX64, "gateway container")
            self._gateway_id = item["Id"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr="")

    def _one_probe(self, container_id: str, *, name: str, kind: str, host: str, port: int) -> bool:
        if container_id != self._vm_id and container_id != self._gateway_id:
            return False
        if name == "host_gateway_blocked":
            try:
                addr = ipaddress.IPv4Address(host)
            except (TypeError, ValueError):
                return False
            if (kind != "tcp4" or not addr.is_private or addr.is_loopback
                    or addr.is_link_local or type(port) is not int or port not in GATEWAY_PORTS):
                return False
            ip, requested_port = str(addr), port
        elif name in _DEFAULT_TARGETS and (kind, host, port) == _DEFAULT_TARGETS[name]:
            ip, requested_port = None, None
        else:
            return False
        try:
            value = self._transport.exchange(
                "probe", container_id, run_id=self._run_id, vm_id=self._vm_id,
                probe_name=name, gateway_ip=ip, port=requested_port,
            )
            return (type(value) is dict and value["name"] == name
                    and type(value["errno"]) is int and value["errno"] in _BLOCK_ERRNOS
                    and value["blocked"] is True)
        except (BrokerDenied, KeyError, TypeError, ValueError):
            return False
