"""Independent, opt-in OSWorld host network auditor and Ed25519 receipt signer.

Run from a separate protected Windows/Linux host identity after the VM boots
and prints the *full* container ID. Never provision a signer key in the repo,
never forward a key to a child VM, and never invoke this from a model tool.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import time

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld.isolation import (
    IsolationDenied, IsolationReceipt, load_pinned_public_keys, verify_receipt,
)
from aura_core.osworld.network_audit import audit_network


def _protected_private_key(path: Path) -> Ed25519PrivateKey:
    root = Path(__file__).resolve().parents[2]
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(root):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operator-owned VM network auditor")
    parser.add_argument("--container", required=True, help="Full 64-hex Docker ID printed at VM boot")
    parser.add_argument("--vm-image", type=Path, required=True, help="Pinned QCOW2 path")
    parser.add_argument("--signer-id", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--trusted-public-keys", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        key = _protected_private_key(args.private_key)
        trusted = load_pinned_public_keys(args.trusted_public_keys)
        boot, ports, checks = audit_network(
            container_id=args.container, vm_image=args.vm_image,
        )
        ts = int(time.time())
        provisional = IsolationReceipt(
            signer_id=args.signer_id, boot=boot, checked_at=ts,
            expires_at=ts + 180, nonce=secrets.token_hex(16),
            checks=checks, host_ports=ports, signature_b64="pending",
        )
        receipt = IsolationReceipt(
            signer_id=provisional.signer_id, boot=provisional.boot,
            checked_at=provisional.checked_at, expires_at=provisional.expires_at,
            nonce=provisional.nonce, checks=provisional.checks,
            host_ports=provisional.host_ports,
            signature_b64=base64.b64encode(key.sign(provisional.signing_payload())).decode("ascii"),
        )
        verify_receipt(receipt, expected=boot, trusted_public_keys=trusted)
        if (not args.out.parent.is_dir() or args.out.exists()
                or args.out.is_symlink() or args.out.resolve().is_relative_to(
                    Path(__file__).resolve().parents[2]
                )):
            raise IsolationDenied("Use a fresh receipt path outside the AURA checkout")
        # An independently created evidence file is never silently overwritten.
        with args.out.open("x", encoding="utf-8") as f:
            json.dump(receipt.to_dict(), f, indent=2)
            f.write("\n")
        print(json.dumps({
            "status": "ISOLATION_SIGNED",
            "container_id": boot.container_id,
            "network_id": boot.network_id,
            "receipt_path": str(args.out),
            "expires_at": receipt.expires_at,
            "checks": sorted(checks),
            "scope": "This does not authorize an MCP action or certify untested paths",
        }, indent=2))
        return 0
    except (IsolationDenied, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "status": "ISOLATION_BLOCKED", "signed": False,
            "error_type": type(exc).__name__, "detail": str(exc)[:500],
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
