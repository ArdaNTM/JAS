"""F2.6 INACTIVE Ubuntu Docker audit transport, never an AURA agent endpoint.

The Windows service can eventually use a pinned OpenSSH host identity and a
root-owned Linux forced command to perform *only* audited inspect/probe calls.
This module does not wire into SCM, change deny_only, provision keys or sign.
A caller cannot supply an SSH host, user, path, command or Docker flags.
"""
from __future__ import annotations

import base64
import binascii
import errno
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
    PROBE_TIMEOUT, _BLOCK_ERRNOS, _DEFAULT_TARGETS, _valid_id,
    _valid_network, _valid_volume,
)
from .audit_broker_service import (
    TRUST_ROOT, BrokerServicePolicy, load_service_policy,
    validate_service_identity, verify_trusted_runtime,
)
from .audit_broker_scm_identity import verify_registered_service_account
from .audit_broker_windows import current_process_sid
from . import network_audit

REQUEST_SCHEMA = "aura.osworld.ubuntu-transport.request.v1"
RESPONSE_SCHEMA = "aura.osworld.ubuntu-transport.response.v1"
SSH_EXE = Path(r"C:\Windows\System32\OpenSSH\ssh.exe")
SSH_KEY = TRUST_ROOT / "keys" / "ubuntu-transport-ed25519"
KNOWN_HOSTS = TRUST_ROOT / "policy" / "ubuntu-known-hosts"
REMOTE_IP = "192.168.247.2"
REMOTE_USER = "aura-transport"
REMOTE_COMMAND = "aura-osworld-transport-v1"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_ALLOWED = frozenset({"inspect_container", "inspect_gateway", "inspect_network", "inspect_volume", "probe"})


def make_request(operation: str, target: str, *, nonce: str, issued_at: int,
                 probe_name: str | None = None, gateway_ip: str | None = None,
                 port: int | None = None) -> bytes:
    """Exact JSON schema: never interpolate caller input into a shell command."""
    if type(operation) is not str or operation not in _ALLOWED:
        raise BrokerDenied("Unapproved Ubuntu transport operation")
    if type(nonce) is not str or _HEX32.fullmatch(nonce) is None or type(issued_at) is not int:
        raise BrokerDenied("Invalid Ubuntu transport freshness")
    if operation == "inspect_container":
        _valid_id(target)
    elif operation == "inspect_gateway":
        if type(target) is not str or not target.startswith(network_audit.GATEWAY_PREFIX) \
                or _HEX32.fullmatch(target[len(network_audit.GATEWAY_PREFIX):]) is None:
            raise BrokerDenied("Unapproved gateway inspection")
    elif operation == "inspect_network":
        _valid_network(target)
    elif operation == "inspect_volume":
        _valid_volume(target)
    else:
        _valid_id(target)
        if type(probe_name) is not str or probe_name not in {*_DEFAULT_TARGETS, "host_gateway_blocked"}:
            raise BrokerDenied("Unapproved Ubuntu network probe")
        if probe_name == "host_gateway_blocked":
            try:
                addr = ipaddress.IPv4Address(gateway_ip)
            except (ValueError, TypeError) as exc:
                raise BrokerDenied("Invalid inspected gateway") from exc
            if not addr.is_private or addr.is_loopback or addr.is_link_local \
                    or type(port) is not int or port not in GATEWAY_PORTS:
                raise BrokerDenied("Unapproved gateway probe target")
            gateway_ip = str(addr)
        elif gateway_ip is not None or port is not None:
            raise BrokerDenied("Caller cannot choose a network target")
    if operation != "probe" and any(v is not None for v in (probe_name, gateway_ip, port)):
        raise BrokerDenied("Unexpected inspection parameters")
    obj = {"schema": REQUEST_SCHEMA, "operation": operation, "target": target,
           "nonce": nonce, "issued_at": issued_at, "probe_name": probe_name,
           "gateway_ip": gateway_ip, "port": port}
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > 1024:
        raise BrokerDenied("Oversized Ubuntu transport request")
    return raw


def parse_response(raw: bytes, *, nonce: str, operation: str) -> object:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_OUTPUT:
        raise BrokerDenied("Invalid Ubuntu transport response size")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise BrokerDenied("Duplicate Ubuntu transport reply field")
            out[key] = value
        return out
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(BrokerDenied("Nonfinite reply")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Malformed Ubuntu transport reply") from exc
    if (type(obj) is not dict or set(obj) != {"schema", "operation", "nonce", "result"}
            or obj["schema"] != RESPONSE_SCHEMA or obj["operation"] != operation
            or obj["nonce"] != nonce):
        raise BrokerDenied("Unauthenticated or mismatched Ubuntu reply")
    value = obj["result"]
    if operation == "probe":
        if (type(value) is not dict
                or set(value) != {"schema", "name", "errno", "blocked"}
                or value["schema"] != "aura.osworld.network-probe.v1"
                or type(value["name"]) is not str
                or type(value["errno"]) is not int
                or type(value["blocked"]) is not bool):
            raise BrokerDenied("Malformed probe result")
    elif type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise BrokerDenied("Malformed Docker inspect result")
    return value


def _verify_pinned_known_hosts(data: bytes) -> None:
    try:
        items = data.decode("ascii").strip().splitlines()
        if len(items) != 1:
            raise ValueError("Expected one pinned Ubuntu host")
        fields = items[0].split()
        if len(fields) != 3 or fields[:2] != [REMOTE_IP, "ssh-ed25519"]:
            raise ValueError("Unexpected SSH host key pin")
        key = base64.b64decode(fields[2], validate=True)
        if len(key) != 51 or key[:15] != b"\x00\x00\x00\x0bssh-ed25519" or key[15:19] != b"\x00\x00\x00 ":
            raise ValueError("Invalid SSH Ed25519 public key wire format")
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise BrokerDenied("Ubuntu host-key pin is invalid") from exc


def _require_sealed_ssh_files() -> None:
    if os.name != "nt":
        raise BrokerDenied("Ubuntu SSH transport requires real Windows broker token")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    for p in (SSH_EXE, SSH_KEY, KNOWN_HOSTS):
        if not p.is_file() or p.is_symlink() or not p.is_absolute():
            raise BrokerDenied("Missing or redirected trusted SSH asset")
    for p in (SSH_KEY, KNOWN_HOSTS, SSH_KEY.parent, KNOWN_HOSTS.parent):
        require_private_acl(p)
    if SSH_KEY.stat().st_size > 8192 or KNOWN_HOSTS.stat().st_size > 4096:
        raise BrokerDenied("Oversized broker SSH trust data")
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


class UbuntuBrokerSshTransport:
    """Inactive trusted broker-only caller; never exposed to agent IPC."""

    def __init__(self, *, runner: Callable[..., Any] = subprocess.run) -> None:
        self._runner = runner

    def exchange(self, operation: str, target: str, *, probe_name: str | None = None,
                 gateway_ip: str | None = None, port: int | None = None) -> object:
        nonce = secrets.token_hex(16)
        raw = make_request(operation, target, nonce=nonce, issued_at=int(time.time()),
                           probe_name=probe_name, gateway_ip=gateway_ip, port=port)
        # The production path always checks the real service identity, SCM and
        # ACLs, and never relies on the agent's claimed role or env variables.
        if self._runner is subprocess.run:
            from .audit_broker_scm_identity import verify_registered_service_account
            # Unlike preflight_service(), this never requires Desktop daemon access.
            verify_trusted_runtime(source_file=Path(__file__), python_executable=Path(os.sys.executable))
            policy = load_service_policy()
            if type(policy) is not BrokerServicePolicy or policy.mode != "deny_only":
                raise BrokerDenied("Ubuntu transport cannot activate audit policy")
            validate_service_identity(policy, actual_sid=current_process_sid())
            verify_registered_service_account(policy)
            _require_sealed_ssh_files()
        try:
            proc = self._runner(_ssh_argv(), input=raw, shell=False,
                                capture_output=True, timeout=READ_TIMEOUT if operation != "probe" else PROBE_TIMEOUT,
                                check=False, env=_trusted_env())
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrokerDenied("Ubuntu SSH transport unavailable") from exc
        if (type(proc.returncode) is not int or proc.returncode != 0
                or type(proc.stdout) is not bytes or len(proc.stdout) > MAX_OUTPUT
                or type(proc.stderr) is not bytes or len(proc.stderr) > 4096):
            raise BrokerDenied("Ubuntu SSH operation failed closed")
        return parse_response(proc.stdout, nonce=nonce, operation=operation)


class UbuntuDockerAuditBackend(DockerAuditBackend):
    """Opt-in backend reusing the EXISTING exact topology policy and probes.

    This subclass is not instantiated by the deployed deny_only service.
    It does not change the Windows Desktop pipe boundary or grant a daemon.
    """

    def __init__(self, *, transport: UbuntuBrokerSshTransport) -> None:
        if type(transport) is not UbuntuBrokerSshTransport:
            raise BrokerDenied("Untrusted Ubuntu transport")
        self._transport = transport

    def _invoke(self, args: list[str], *, timeout: int) -> SimpleNamespace:
        if type(args) is not list or any(type(x) is not str for x in args):
            raise BrokerDenied("Unapproved Docker inspection")
        if len(args) == 2 and args[0] == "inspect":
            operation = "inspect_container" if re.fullmatch(r"[0-9a-f]{64}", args[1]) else "inspect_gateway"
            target = args[1]
        elif len(args) == 3 and args[:2] == ["network", "inspect"]:
            operation, target = "inspect_network", args[2]
        elif len(args) == 3 and args[:2] == ["volume", "inspect"]:
            operation, target = "inspect_volume", args[2]
        else:
            raise BrokerDenied("Ubuntu transport forbids arbitrary Docker commands")
        reply = self._transport.exchange(operation, target)
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr="")

    def _one_probe(self, container_id: str, *, name: str, kind: str, host: str, port: int) -> bool:
        # Reject any attempt to call this internal method with a caller-chosen
        # host, protocol or port. The server independently revalidates again.
        _valid_id(container_id)
        if name == "host_gateway_blocked":
            try:
                addr = ipaddress.IPv4Address(host)
            except (ValueError, TypeError):
                return False
            if kind != "tcp4" or not addr.is_private or addr.is_loopback or addr.is_link_local or port not in GATEWAY_PORTS:
                return False
            ip = str(addr)
            requested_port = port
        elif name in _DEFAULT_TARGETS and (kind, host, port) == _DEFAULT_TARGETS[name]:
            ip, requested_port = None, None
        else:
            return False
        try:
            result = self._transport.exchange("probe", container_id, probe_name=name,
                                              gateway_ip=ip, port=requested_port)
            return (type(result) is dict and result["name"] == name
                    and type(result["errno"]) is int and result["errno"] in _BLOCK_ERRNOS
                    and result["blocked"] is True)
        except (BrokerDenied, KeyError, TypeError, ValueError):
            return False
