"""F2.4: independent host attestor accepts only authenticated broker measurements.

The agent never handles the auditor's host Ed25519 key. The Windows broker's
signed measurement must be verified by the named-pipe client using an
independently pinned broker public key, before a *different* host key signs
the ordinary OSWorld isolation receipt.

This is an auditor component, not a Windows broker service installer and not
authorization to skip the separate owner/MCP permission boundaries.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit_broker_client import BrokerPipeTransport, request_signed_measurement
from .audit_broker_protocol import BrokerDenied
from .audit_broker_receipt import SCHEMA, signing_bytes
from .audit_broker_service import SID_PATTERN
from .isolation import (
    BootIdentity, IsolationDenied, IsolationReceipt, verify_receipt,
)
from .network_audit import sha256_file

TRUST_SCHEMA = "aura.osworld.broker-trust.v1"
_TRUST_FIELDS = frozenset({
    "schema", "auditor_sid", "broker_service_sid", "broker_public_key_hex",
})
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class BrokerTrust:
    auditor_sid: str
    broker_service_sid: str
    public_key: bytes


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BrokerDenied("Duplicate broker trust policy key")
        result[key] = value
    return result


def parse_broker_trust(raw: bytes) -> BrokerTrust:
    """Exactly one protected broker public key; never accept in-band pinning."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 1024:
        raise BrokerDenied("Broker trust policy has invalid size")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Malformed protected broker trust policy") from exc
    if (type(obj) is not dict or set(obj) != _TRUST_FIELDS
            or obj["schema"] != TRUST_SCHEMA):
        raise BrokerDenied("Unexpected broker trust schema")
    sid1, sid2 = obj["auditor_sid"], obj["broker_service_sid"]
    if (type(sid1) is not str or type(sid2) is not str
            or SID_PATTERN.fullmatch(sid1) is None
            or SID_PATTERN.fullmatch(sid2) is None or sid1 == sid2):
        raise BrokerDenied("Auditor and broker Windows SIDs must differ")
    key_hex = obj["broker_public_key_hex"]
    if type(key_hex) is not str or _HEX64.fullmatch(key_hex) is None:
        raise BrokerDenied("Broker key must be a separately pinned Ed25519 public key")
    return BrokerTrust(sid1, sid2, bytes.fromhex(key_hex))


def _protected_operator_file(path: Path) -> None:
    """Never load a pin/key file from the mutable AURA checkout or a link."""
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or path.parent.is_symlink()
            or not path.is_file() or path.resolve().is_relative_to(_REPO)):
        raise BrokerDenied("Broker trust file must be protected outside AURA checkout")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        require_private_acl(path)
    elif (path.stat().st_mode & 0o077) or (path.parent.stat().st_mode & 0o077):
        raise BrokerDenied("Broker trust file cannot be group/world accessible")


def load_broker_trust(path: Path) -> BrokerTrust:
    _protected_operator_file(path)
    if path.stat().st_size > 1024:
        raise BrokerDenied("Oversized pinned broker policy")
    return parse_broker_trust(path.read_bytes())


def _require_d_disk(vm_image: Path) -> None:
    """Production-only Windows drive gate; do not weaken for CI fixtures."""
    if os.name == "nt" and vm_image.drive.upper() != "D:":
        raise BrokerDenied("Auditor VM disk must remain on D:")


def _pinned_vm_hash(vm_image: Path) -> str:
    if (not isinstance(vm_image, Path) or not vm_image.is_absolute()
            or not vm_image.is_file() or vm_image.is_symlink()
            or vm_image.parent.is_symlink()):
        raise BrokerDenied("Auditor VM disk must be an absolute regular file")
    _require_d_disk(vm_image)
    return sha256_file(vm_image)


def _auditor_public_key(key: Ed25519PrivateKey) -> bytes:
    if not isinstance(key, Ed25519PrivateKey):
        raise BrokerDenied("Independent host Ed25519 signing key is unavailable")
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _sign_verified_broker_claims(
    claims: object, *, run_id: str, container_id: str, vm_sha256: str,
    signer_id: str, signer: Ed25519PrivateKey,
    trusted_public_keys: Mapping[str, bytes],
    broker_public_key: bytes, now: int,
) -> IsolationReceipt:
    """The only host receipt conversion path; never accepts mere PASS flags."""
    if (type(now) is not int or type(claims) is not dict
            or type(run_id) is not str or _HEX32.fullmatch(run_id) is None
            or type(container_id) is not str or _HEX64.fullmatch(container_id) is None
            or type(vm_sha256) is not str or _HEX64.fullmatch(vm_sha256) is None):
        raise BrokerDenied("Invalid or incomplete verified measurement identity")
    # Apply the complete broker measurement contract again at the signing
    # boundary. Cryptographic verification was mandatory in IPC client.
    signing_bytes(claims)
    if (claims["schema"] != SCHEMA or claims["run_id"] != run_id
            or claims["container_id"] != container_id
            or not now - 30 <= claims["checked_at"] <= now + 5):
        raise BrokerDenied("Broker measurement cannot be bound to this attestation")
    boot = BootIdentity(**claims["boot"])
    if boot.container_id != container_id or boot.vm_sha256 != vm_sha256:
        raise BrokerDenied("Broker VM disk or container identity mismatch")
    host_public = _auditor_public_key(signer)
    if (type(broker_public_key) is not bytes or len(broker_public_key) != 32
            or broker_public_key == host_public):
        raise BrokerDenied("Broker and host attestor must use distinct pinned keys")
    if (not isinstance(trusted_public_keys, Mapping)
            or trusted_public_keys.get(signer_id) != host_public):
        raise BrokerDenied("Independent host signer key does not match pinned ID")
    ts = claims["checked_at"]
    # Broker nonce binds this receipt to the exact IPC request and
    # cryptographically verified measurement.
    preliminary = IsolationReceipt(
        signer_id=signer_id, boot=boot, checked_at=ts,
        expires_at=ts + 180, nonce=claims["nonce"],
        checks=dict(claims["checks"]), host_ports=dict(claims["host_ports"]),
        signature_b64="pending",
    )
    import base64
    receipt = IsolationReceipt(
        signer_id=preliminary.signer_id, boot=preliminary.boot,
        checked_at=preliminary.checked_at, expires_at=preliminary.expires_at,
        nonce=preliminary.nonce, checks=preliminary.checks,
        host_ports=preliminary.host_ports,
        signature_b64=base64.b64encode(
            signer.sign(preliminary.signing_payload()),
        ).decode("ascii"),
    )
    verify_receipt(
        receipt, expected=boot, trusted_public_keys=trusted_public_keys, now=now,
    )
    return receipt


def attest_via_broker(
    *, run_id: str, container_id: str, vm_image: Path,
    trust: BrokerTrust, signer_id: str, signer: Ed25519PrivateKey,
    trusted_public_keys: Mapping[str, bytes],
    transport: BrokerPipeTransport | None = None,
) -> IsolationReceipt:
    """Only broker-signed and disk-bound measurements can be host-signed.

    transport is an offline test seam. Production always uses
    WindowsBrokerPipe and authenticated OS process tokens.
    """
    if type(trust) is not BrokerTrust:
        raise BrokerDenied("Missing independently pinned broker trust configuration")
    host_public = _auditor_public_key(signer)
    if trust.public_key == host_public:
        raise BrokerDenied("Broker cannot share host Ed25519 key")
    if trusted_public_keys.get(signer_id) != host_public:
        raise BrokerDenied("Host signer identity is not pinned")
    # Independently hash the disk both before and after the IPC measurement:
    # a changed/redirected local QCOW2 invalidates the signed claim.
    before = _pinned_vm_hash(vm_image)
    claims = request_signed_measurement(
        run_id=run_id, container_id=container_id,
        expected_auditor_sid=trust.auditor_sid,
        expected_service_sid=trust.broker_service_sid,
        pinned_broker_public_key=trust.public_key,
        transport=transport,
    )
    after = _pinned_vm_hash(vm_image)
    if before != after:
        raise BrokerDenied("VM image changed while broker was measuring isolation")
    return _sign_verified_broker_claims(
        claims, run_id=run_id, container_id=container_id,
        vm_sha256=before, signer_id=signer_id, signer=signer,
        trusted_public_keys=trusted_public_keys,
        broker_public_key=trust.public_key, now=int(time.time()),
    )
