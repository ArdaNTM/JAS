"""F2.7 independent, signed operator activation; fail closed by default.

The operator Ed25519 private key MUST remain OFF the AURA host. The raw
32-byte public key is trusted ONLY because an independent Windows operator
sealed D:\\AURA\\Trust\\DockerBroker\\keys. A JSON mode flip alone cannot grant
an audit: all code/runtime bytes, identities, host pin and exact VM/run must
be bound by the signature and protected Windows ACLs.

The signer never authorizes ISOLATION_SIGNED. This approval only allows a
single request of read-only Docker inspect and fixed negative network probes.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .audit_broker_protocol import BrokerDenied
from .audit_broker_service import (
    BIN_ROOT, POLICY_PATH, STATE_ROOT, TRUST_ROOT, BrokerServicePolicy,
    _reject_duplicate_keys, parse_service_policy, verify_trusted_runtime,
)

DOMAIN = b"AURA:F2.7:INDEPENDENT-OPERATOR-AUDIT-APPROVAL:v1\n"
APPROVAL_SCHEMA = "aura.osworld.f27-operator-approval.v1"
INVENTORY_SCHEMA = "aura.osworld.f27-runtime-inventory.v1"
APPROVAL_PATH = TRUST_ROOT / "policy" / "operator-approval.json"
OPERATOR_PUBLIC_KEY = TRUST_ROOT / "keys" / "operator-approval-ed25519.pub"
RUNTIME_INVENTORY = TRUST_ROOT / "policy" / "f27-runtime-inventory.json"
KNOWN_HOSTS = TRUST_ROOT / "policy" / "ubuntu-known-hosts"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_POLICY_KEYS = {"schema", "service_sid", "auditor_sid", "agent_sid", "mode"}
_CLAIMS = {
    "mode", "service_sid", "auditor_sid", "agent_sid", "run_id", "vm_id",
    "vm_disk_sha256", "policy_sha256", "runtime_inventory_sha256",
    "known_hosts_sha256", "approval_nonce", "issued_at", "expires_at",
}


@dataclass(frozen=True, slots=True)
class ApprovedActivation:
    policy: BrokerServicePolicy
    run_id: str
    vm_id: str
    vm_disk_sha256: str
    nonce: str
    expires_at: int


def _json(raw: bytes, *, limit: int) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise BrokerDenied("Unbounded or absent operator approval input")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                         parse_constant=lambda _: (_ for _ in ()).throw(BrokerDenied("Nonfinite approval")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Invalid operator activation JSON") from exc
    if type(obj) is not dict:
        raise BrokerDenied("Operator activation must be an object")
    return obj


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _approved_policy(raw: bytes) -> BrokerServicePolicy:
    doc = _json(raw, limit=2048)
    if set(doc) != _POLICY_KEYS or doc["mode"] != "audit_only":
        raise BrokerDenied("Service policy has no explicit audit_only intent")
    # Reuse all strict F2.1 SID and field predicates without changing the
    # public deny_only parser (which must continue to reject audit_only).
    denial = {**doc, "mode": "deny_only"}
    base = parse_service_policy(json.dumps(denial, sort_keys=True).encode("ascii"))
    return replace(base, mode="audit_only")


def signed_approval_bytes(claims: dict[str, object]) -> bytes:
    if type(claims) is not dict or set(claims) != _CLAIMS:
        raise BrokerDenied("Operator approval contains unknown or missing fields")
    return DOMAIN + json.dumps(claims, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("ascii")


def verify_operator_approval(
    envelope_raw: bytes, public_key: bytes, *,
    policy_raw: bytes, runtime_inventory_raw: bytes, known_hosts_raw: bytes,
    now: int,
) -> ApprovedActivation:
    """Pure verification, separately unit tested with test-only Ed25519 keys.

    This is NOT an activation switch. The production caller additionally
    verifies the protected file ACLs, actual SCM token, fully hashed runtime,
    and atomically consumes a durable approval nonce before connecting.
    """
    if type(now) is not int or type(public_key) is not bytes or len(public_key) != 32:
        raise BrokerDenied("Missing independently pinned operator public key")
    envelope = _json(envelope_raw, limit=4096)
    if set(envelope) != {"schema", "claims", "signature_b64"} or envelope["schema"] != APPROVAL_SCHEMA:
        raise BrokerDenied("Operator approval envelope schema mismatch")
    claims = envelope["claims"]
    signed = signed_approval_bytes(claims)
    b64 = envelope["signature_b64"]
    if type(b64) is not str:
        raise BrokerDenied("Missing operator signature")
    try:
        sig = base64.b64decode(b64, validate=True)
        if len(sig) != 64:
            raise BrokerDenied("Invalid operator signature length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(sig, signed)
    except (ValueError, TypeError, InvalidSignature, binascii.Error) as exc:
        raise BrokerDenied("Operator approval signature is not trusted") from exc

    policy = _approved_policy(policy_raw)
    if (claims["mode"] != "audit_only" or claims["service_sid"] != policy.service_sid
            or claims["auditor_sid"] != policy.auditor_sid
            or claims["agent_sid"] != policy.agent_sid):
        raise BrokerDenied("Operator signature does not authorize this Windows identity or mode")
    for field, value in (
        ("policy_sha256", _sha(policy_raw)),
        ("runtime_inventory_sha256", _sha(runtime_inventory_raw)),
        ("known_hosts_sha256", _sha(known_hosts_raw)),
    ):
        if type(claims[field]) is not str or claims[field] != value:
            raise BrokerDenied("Operator approval is not bound to sealed " + field)

    for field, pattern in (
        ("run_id", _HEX32), ("vm_id", _HEX64),
        ("vm_disk_sha256", _HEX64), ("approval_nonce", _HEX32),
    ):
        if type(claims[field]) is not str or pattern.fullmatch(claims[field]) is None:
            raise BrokerDenied("Invalid signed operator " + field)

    issued, expiry = claims["issued_at"], claims["expires_at"]
    if (type(issued) is not int or type(expiry) is not int
            or not now - 60 <= issued <= now + 5
            or not issued < expiry <= issued + 900 or now >= expiry):
        raise BrokerDenied("Operator activation expired, backdated or overlong")
    return ApprovedActivation(
        policy=policy, run_id=claims["run_id"], vm_id=claims["vm_id"],
        vm_disk_sha256=claims["vm_disk_sha256"],
        nonce=claims["approval_nonce"], expires_at=expiry,
    )


def _protected_bytes(path: Path, *, max_bytes: int) -> bytes:
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise BrokerDenied("Operator trust file redirected")
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise BrokerDenied("Sealed operator trust file unavailable")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        require_private_acl(path)
    return path.read_bytes()


def _unsafe(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def verify_exact_runtime_inventory(inventory_raw: bytes, *, root: Path) -> None:
    """Rehash the WHOLE sealed runtime. One file modified or added fails."""
    manifest = _json(inventory_raw, limit=2_000_000)
    if set(manifest) != {"schema", "files"} or manifest["schema"] != INVENTORY_SCHEMA:
        raise BrokerDenied("Wrong F2.7 runtime inventory")
    entries = manifest["files"]
    if type(entries) is not list or not 1 <= len(entries) <= 12000:
        raise BrokerDenied("Unexpected runtime inventory count")
    if not root.is_absolute() or not root.is_dir() or _unsafe(root):
        raise BrokerDenied("Runtime directory is untrusted")
    seen: set[str] = set()
    for record in entries:
        if type(record) is not dict or set(record) != {"path", "sha256"}:
            raise BrokerDenied("Unexpected runtime file inventory field")
        relative, digest = record["path"], record["sha256"]
        if type(relative) is not str or type(digest) is not str or _HEX64.fullmatch(digest) is None:
            raise BrokerDenied("Malformed runtime file inventory")
        parts = relative.replace("\\", "/").split("/")
        if (not parts or any(p in {"", ".", ".."} or p.endswith((".", " ")) or ":" in p for p in parts)
                or relative.startswith(("/", "\\")) or any(c in relative for c in "\x00\n\r*?|<>")):
            raise BrokerDenied("Unsafe runtime inventory path")
        canonical = "/".join(parts).lower()
        if canonical in seen:
            raise BrokerDenied("Duplicate runtime path")
        seen.add(canonical)
        file = root.joinpath(*parts)
        if not file.is_file() or _unsafe(file) or _sha(file.read_bytes()) != digest:
            raise BrokerDenied("Runtime file is missing, redirected or mutated")
    actual = set()
    for f in root.rglob("*"):
        if _unsafe(f):
            raise BrokerDenied("Runtime reparse point")
        if f.is_file():
            actual.add(f.relative_to(root).as_posix().lower())
    if actual != seen:
        raise BrokerDenied("Uninventoried runtime files or missing payload")


def load_operator_approved_activation(*, now: int | None = None,
                                      verify_inventory: bool = True) -> ApprovedActivation:
    """Production-only, immutable system paths; no caller path injection."""
    if os.name != "nt":
        raise BrokerDenied("Signed operator activation only valid on Windows SCM")
    verify_trusted_runtime(source_file=Path(__file__), python_executable=Path(sys.executable))
    policy_raw = _protected_bytes(POLICY_PATH, max_bytes=2048)
    inventory_raw = _protected_bytes(RUNTIME_INVENTORY, max_bytes=2_000_000)
    envelope = _protected_bytes(APPROVAL_PATH, max_bytes=4096)
    key = _protected_bytes(OPERATOR_PUBLIC_KEY, max_bytes=32)
    hosts = _protected_bytes(KNOWN_HOSTS, max_bytes=4096)
    approved = verify_operator_approval(
        envelope, key, policy_raw=policy_raw, runtime_inventory_raw=inventory_raw,
        known_hosts_raw=hosts, now=int(time.time()) if now is None else now,
    )
    root = Path(sys.executable).parent
    if root.resolve(strict=True) != root.absolute() or not root.is_relative_to(BIN_ROOT):
        raise BrokerDenied("Approved code is not in protected broker bin")
    if verify_inventory:
        verify_exact_runtime_inventory(inventory_raw, root=root)
    return approved
