"""Independent F2.4 OSWorld host attestor — broker-only isolation receipts.

Run as AuraAuditor under a separate Windows account. Never invoke Docker
directly, load broker signing secrets, or fall back to host-side network_audit.
The service must first return a fresh, valid signed measurement from its
separately protected key. The host then independently binds it to the pinned
QCOW2 and signs with the existing AuraAuditor Ed25519 private key.

This code does not install/enable the F2.1 deny-only broker service, and
does not confer MCP Gateway authorization or Windows Hello approval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld.audit_broker_attestor import (
    attest_via_broker, load_broker_trust, _protected_operator_file,
)
from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.isolation import (
    IsolationDenied, load_pinned_public_keys,
)


def _protected_private_key(path: Path) -> Ed25519PrivateKey:
    root = Path(__file__).resolve().parents[2]
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.resolve().is_relative_to(root)):
        raise IsolationDenied("Independent auditor private key must live outside AURA checkout")
    if path.stat().st_size > 8192:
        raise IsolationDenied("Oversized signer private key")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        require_private_acl(path)
    elif path.stat().st_mode & 0o077:
        raise IsolationDenied("Auditor key cannot be group/world accessible")
    key = load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise IsolationDenied("Auditor must use independently protected Ed25519 key")
    return key


def _safe_new_receipt_path(path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    if (not path.is_absolute() or not path.parent.is_dir()
            or path.is_symlink() or path.parent.is_symlink() or path.exists()
            or path.resolve().is_relative_to(root)):
        raise IsolationDenied("Use a fresh receipt path outside the AURA checkout")
    if os.name == "nt":
        if path.drive.upper() != "D:":
            raise IsolationDenied("New isolation receipts must reside on D:")
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
    elif path.parent.stat().st_mode & 0o077:
        raise IsolationDenied("Receipt directory cannot be group/world accessible")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independent AuraAuditor: broker-signed OSWorld isolation only",
    )
    parser.add_argument("--run-id", required=True, help="32-hex OSWorld run ID")
    parser.add_argument("--container", required=True, help="Full 64-hex Docker VM container ID")
    parser.add_argument("--vm-image", type=Path, required=True, help="Pinned QCOW2 on D:")
    parser.add_argument("--broker-trust", type=Path, required=True,
                        help="Protected independent broker SID/public key trust file")
    parser.add_argument("--signer-id", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--trusted-public-keys", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        trust = load_broker_trust(args.broker_trust)
        key = _protected_private_key(args.private_key)
        _protected_operator_file(args.trusted_public_keys)
        trusted = load_pinned_public_keys(args.trusted_public_keys)

        # A valid host receipt can only be created by a trusted broker IPC
        # response. There is NO direct Docker audit fallback.
        receipt = attest_via_broker(
            run_id=args.run_id, container_id=args.container,
            vm_image=args.vm_image, trust=trust, signer_id=args.signer_id,
            signer=key, trusted_public_keys=trusted,
        )
        _safe_new_receipt_path(args.out)
        # Exclusive creation: pre-existing evidence is never overwritten.
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(receipt.to_dict(), stream, indent=2)
            stream.write("\n")
        print(json.dumps({
            "status": "ISOLATION_SIGNED",
            "container_id": receipt.boot.container_id,
            "network_id": receipt.boot.network_id,
            "receipt_path": str(args.out),
            "expires_at": receipt.expires_at,
            "checks": sorted(receipt.checks),
            "scope": "Does not authorize MCP actions or Windows Hello bypass",
        }, indent=2))
        return 0
    except (BrokerDenied, IsolationDenied, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "status": "ISOLATION_BLOCKED",
            "signed": False,
            "error_type": type(exc).__name__,
            "detail": str(exc)[:500],
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
