"""Strict public-key verification of a short-lived OSWorld network isolation proof.

AURA may *verify* but never sign receipts here. A separate host OS identity
and private signing key must run the container/network auditor. A signature
attests the exact inspected Docker container, immutable runtime image, guest
disk, network ID, exposed ports, and all specified negative probes; it cannot
magically prove an untested network path or protect against a compromised host.

Receipt must be renewed when container/network/VM changes; passkey approvals
and MCP Gateway dispatch remain independent, mandatory boundaries.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

NETWORK_NAME = "aura-osworld-v21-lab"
IMAGE = "happysixd/osworld-docker@sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
EXPECTED_PORTS = (5000, 8006, 8080, 9222)
DOMAIN = b"AURA:OSWORLD:NETWORK-ISOLATION:v1\n"
REQUIRED_CHECKS = frozenset({
    "network_internal",
    "single_network",
    "loopback_ports",
    "unprivileged",
    "no_docker_socket",
    "image_pinned",
    "egress_v4_blocked",
    "metadata_blocked",
    "external_dns_blocked",
    "ipv6_blocked",
    "host_gateway_blocked",
})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_SIGNER = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


class IsolationDenied(PermissionError):
    """The asserted Docker sandbox isolation is not sufficiently evidenced."""


@dataclass(frozen=True, slots=True)
class BootIdentity:
    container_id: str
    network_id: str
    vm_sha256: str
    image: str

    def __post_init__(self) -> None:
        if any(not isinstance(x, str) or not _HEX64.fullmatch(x) for x in (
            self.container_id, self.network_id, self.vm_sha256,
        )):
            raise IsolationDenied("Malformed VM, network or container identity")
        if self.image != IMAGE:
            raise IsolationDenied("Unpinned OSWorld runtime image")


@dataclass(frozen=True, slots=True)
class IsolationReceipt:
    signer_id: str
    boot: BootIdentity
    checked_at: int
    expires_at: int
    nonce: str
    checks: Mapping[str, bool]
    host_ports: Mapping[str, str]
    signature_b64: str

    def _claims(self) -> dict[str, object]:
        return {
            "schema": "aura.osworld.network-isolation.v1",
            "signer_id": self.signer_id,
            "container_id": self.boot.container_id,
            "network_id": self.boot.network_id,
            "vm_sha256": self.boot.vm_sha256,
            "image": self.boot.image,
            "network_name": NETWORK_NAME,
            "checked_at": self.checked_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "checks": dict(self.checks),
            "host_ports": dict(self.host_ports),
        }

    def signing_payload(self) -> bytes:
        return DOMAIN + json.dumps(
            self._claims(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")

    def to_dict(self) -> dict[str, object]:
        return {**self._claims(), "signature_b64": self.signature_b64}

    @classmethod
    def from_dict(cls, obj: object) -> IsolationReceipt:
        fields = {
            "schema", "signer_id", "container_id", "network_id", "vm_sha256",
            "image", "network_name", "checked_at", "expires_at", "nonce",
            "checks", "host_ports", "signature_b64",
        }
        if not isinstance(obj, dict) or set(obj) != fields:
            raise IsolationDenied("Invalid signed isolation envelope")
        if obj["schema"] != "aura.osworld.network-isolation.v1" or obj["network_name"] != NETWORK_NAME:
            raise IsolationDenied("Unexpected isolation schema or network")
        boot = BootIdentity(obj["container_id"], obj["network_id"], obj["vm_sha256"], obj["image"])
        return cls(
            signer_id=obj["signer_id"], boot=boot, checked_at=obj["checked_at"],
            expires_at=obj["expires_at"], nonce=obj["nonce"], checks=obj["checks"],
            host_ports=obj["host_ports"], signature_b64=obj["signature_b64"],
        )


def verify_receipt(
    receipt: IsolationReceipt, *,
    expected: BootIdentity,
    trusted_public_keys: Mapping[str, bytes],
    now: int | None = None,
) -> None:
    """Fail closed; no self-signed or boolean-only trust shortcut."""
    if not isinstance(receipt, IsolationReceipt) or receipt.boot != expected:
        raise IsolationDenied("Receipt is bound to a different container, VM or network")
    if not isinstance(receipt.signer_id, str) or not _SIGNER.fullmatch(receipt.signer_id):
        raise IsolationDenied("Invalid external signer identity")
    if not isinstance(receipt.checked_at, int) or type(receipt.checked_at) is not int:
        raise IsolationDenied("Invalid audit timestamp")
    if type(receipt.expires_at) is not int or type(receipt.nonce) is not str:
        raise IsolationDenied("Invalid expiry or nonce")
    current = int(time.time()) if now is None else now
    if not isinstance(current, int) or not (current - 300 <= receipt.checked_at <= current + 30):
        raise IsolationDenied("Receipt must reflect a recent host inspection")
    if not (0 < receipt.expires_at - receipt.checked_at <= 300) or current >= receipt.expires_at:
        raise IsolationDenied("Expired or unbounded isolation receipt")
    if not _HEX32.fullmatch(receipt.nonce):
        raise IsolationDenied("Invalid receipt nonce")
    if (not isinstance(receipt.checks, dict)
            or set(receipt.checks) != REQUIRED_CHECKS
            or any(v is not True for v in receipt.checks.values())):
        raise IsolationDenied("Missing or failed network isolation checks")
    if (not isinstance(receipt.host_ports, dict)
            or set(receipt.host_ports) != {str(p) for p in EXPECTED_PORTS}
            or any(
                not isinstance(v, str) or not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}", v)
                or int(v.split(":")[1]) > 65535
                for v in receipt.host_ports.values()
            )):
        raise IsolationDenied("Container control ports not all bound to loopback")
    raw = trusted_public_keys.get(receipt.signer_id)
    if not isinstance(raw, bytes) or len(raw) != 32:
        raise IsolationDenied("Independent host auditor key not pinned")
    try:
        signature = base64.b64decode(receipt.signature_b64, validate=True)
        if len(signature) != 64:
            raise IsolationDenied("Malformed attestor signature")
        Ed25519PublicKey.from_public_bytes(raw).verify(
            signature, receipt.signing_payload(),
        )
    except (InvalidSignature, ValueError, TypeError, binascii.Error) as exc:
        raise IsolationDenied("Invalid network attestor signature") from exc


def load_pinned_public_keys(path: Path) -> dict[str, bytes]:
    """Operator-provisioned pinned signer trust store. Public keys only."""
    if not path.is_file() or path.stat().st_size > 4096:
        raise IsolationDenied("Invalid public-key trust file")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not 1 <= len(obj) <= 4:
        raise IsolationDenied("One to four independent host auditor keys required")
    try:
        parsed = {k: bytes.fromhex(v) for k, v in obj.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise IsolationDenied("Invalid public-key encoding") from exc
    if any(not _SIGNER.fullmatch(k) or len(v) != 32 for k, v in parsed.items()):
        raise IsolationDenied("Invalid pinned signer ID or Ed25519 public key")
    return parsed
