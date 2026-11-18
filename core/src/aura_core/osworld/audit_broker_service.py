"""Stage F2.1: fail-closed Windows service identity and deployment preflight.

No Docker operations, signing keys, service provisioning or agent privileges
are granted here. The broker will only answer ISOLATION_BLOCKED until a
separately reviewed F2.3 handler is integrated.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable

from .audit_broker_protocol import BrokerDenied
from .audit_broker_windows import current_process_sid

TRUST_ROOT = Path(r"D:\AURA\Trust\DockerBroker")
BIN_ROOT = TRUST_ROOT / "bin"
POLICY_PATH = TRUST_ROOT / "policy" / "service.json"
STATE_ROOT = TRUST_ROOT / "state"
SERVICE_NAME = "AuraOSWorldAuditBroker"
POLICY_SCHEMA = "aura.osworld.broker-service.v1"
SID_PATTERN = re.compile(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+\Z")
DENIED_RESPONSE = b'{"status":"ISOLATION_BLOCKED","signed":false}'


@dataclass(frozen=True, slots=True)
class BrokerServicePolicy:
    service_sid: str
    auditor_sid: str
    agent_sid: str
    mode: str


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BrokerDenied("Duplicate service policy key")
        result[key] = value
    return result


def parse_service_policy(raw: bytes) -> BrokerServicePolicy:
    if type(raw) is not bytes or not 1 <= len(raw) <= 2048:
        raise BrokerDenied("Service policy must be bounded UTF-8")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Malformed service policy") from exc
    if type(data) is not dict or set(data) != {
        "schema", "service_sid", "auditor_sid", "agent_sid", "mode",
    }:
        raise BrokerDenied("Unexpected service policy fields")
    if data["schema"] != POLICY_SCHEMA or data["mode"] != "deny_only":
        raise BrokerDenied("Broker cannot enable live Docker in Stage F2.1")
    ids = (data["service_sid"], data["auditor_sid"], data["agent_sid"])
    if any(type(sid) is not str or SID_PATTERN.fullmatch(sid) is None for sid in ids):
        raise BrokerDenied("All service principals must be distinct user SIDs")
    if len(set(ids)) != 3:
        raise BrokerDenied("Service, auditor and agent identities must differ")
    return BrokerServicePolicy(*ids, mode="deny_only")


def validate_service_identity(policy: BrokerServicePolicy, *, actual_sid: str) -> None:
    if type(policy) is not BrokerServicePolicy:
        raise BrokerDenied("Invalid service policy")
    if type(actual_sid) is not str or actual_sid != policy.service_sid:
        raise BrokerDenied("Windows broker process is not the pinned service account")
    if actual_sid in (policy.auditor_sid, policy.agent_sid):
        raise BrokerDenied("Broker cannot share agent or auditor credentials")


def _assert_protected_path(path: Path, *, is_directory: bool) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise BrokerDenied("Broker trust paths must be absolute non-links")
    if not (path.is_dir() if is_directory else path.is_file()):
        raise BrokerDenied("Required broker trust path is missing")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    require_private_acl(path)


def verify_trusted_runtime(
    *, source_file: Path, python_executable: Path,
    policy_path: Path = POLICY_PATH, bin_root: Path = BIN_ROOT,
) -> None:
    """All executable bytes and policy must reside under broker-private D: bin.

    The service account owns these ACLs; AURA's writable checkout cannot
    satisfy this guard. Does not create/migrate protected state.
    """
    if os.name != "nt":
        raise BrokerDenied("Broker service requires Windows")
    if policy_path != POLICY_PATH or bin_root != BIN_ROOT:
        raise BrokerDenied("Broker policy or runtime path was redirected")
    for item in (TRUST_ROOT, BIN_ROOT, POLICY_PATH.parent, STATE_ROOT):
        _assert_protected_path(item, is_directory=True)
    for item in (policy_path, source_file, python_executable):
        _assert_protected_path(item, is_directory=False)
    for item in (source_file, python_executable):
        if not item.resolve(strict=True).is_relative_to(BIN_ROOT.resolve(strict=True)):
            raise BrokerDenied("Executable outside broker-owned D: code directory")
    if source_file.resolve(strict=True) != source_file.absolute():
        raise BrokerDenied("Broker module path is redirected")


def load_service_policy(path: Path = POLICY_PATH) -> BrokerServicePolicy:
    if path != POLICY_PATH:
        raise BrokerDenied("Unpinned service policy path")
    _assert_protected_path(path, is_directory=False)
    return parse_service_policy(path.read_bytes())


def _sealed_deny_only_service_policy() -> BrokerServicePolicy:
    """Common Windows SCM guard: sealed runtime, real process SID, deny-only.

    A policy file is not proof of the current Windows process identity.
    The separately registered SCM logon identity is checked by the adapter.
    """
    verify_trusted_runtime(
        source_file=Path(__file__), python_executable=Path(sys.executable)
    )
    policy = load_service_policy()
    if type(policy) is not BrokerServicePolicy or policy.mode != "deny_only":
        raise BrokerDenied("SCM service cannot activate audit capabilities")
    validate_service_identity(policy, actual_sid=current_process_sid())
    return policy


def preflight_service() -> BrokerServicePolicy:
    """Legacy Windows Docker Desktop preflight; keep its daemon guard intact."""
    policy = _sealed_deny_only_service_policy()
    from .audit_broker_boundary import inspect_current_principal
    observation = inspect_current_principal(
        role="broker", expected_sid=policy.service_sid,
    )
    if observation.access != "allowed":
        raise BrokerDenied("Broker service cannot access the pinned Docker daemon")
    return policy


def preflight_ubuntu_deny_only_service() -> BrokerServicePolicy:
    """Ubuntu-targeted SCM adapter: identity-checked, strictly deny-only.

    Do not require Windows Docker Desktop access for an Ubuntu transport.
    This path does not instantiate SSH, authorize Docker, or issue receipts.
    Any future audit_only path needs a separate operator-reviewed gate.
    """
    return _sealed_deny_only_service_policy()


def blocked_handler(raw: bytes, peer_sid: str) -> bytes:
    """Deliberately never produces a signed measurement or uses Docker."""
    return DENIED_RESPONSE


def serve_denied_request_once(policy: BrokerServicePolicy) -> None:
    from .audit_broker_windows import serve_once
    validate_service_identity(policy, actual_sid=current_process_sid())
    serve_once(
        auditor_sid=policy.auditor_sid,
        expected_service_sid=policy.service_sid,
        forbidden_agent_sid=policy.agent_sid,
        handler=blocked_handler,
    )
