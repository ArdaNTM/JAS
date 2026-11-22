"""Explicit operator-only signing/revoking of bounded local review delegation.

Run this CLI under the separately provisioned Windows Owner identity. The
Ed25519 key is DPAPI CurrentUser-bound and never handled by AURA Core runtime.
It does not mint an Owner WebAuthn receipt or independent sandbox attestation,
and signed review consent never authorizes live MCP execution.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import time

from cryptography.hazmat.primitives import serialization

from aura_core.evolution.decision_engine import (
    _canonical, _DEPLOYED_CATEGORIES,
)
from aura_core.evolution.external_staging import _checked_path


def make_review_delegation(signer, *, categories: tuple[str, ...],
                           duration_seconds: int = 86400,
                           issued_at: int | None = None) -> dict:
    """Domain-separated signature; useful for offline verification tests."""
    if (not isinstance(categories, tuple) or not categories
            or set(categories) - _DEPLOYED_CATEGORIES
            or len(set(categories)) != len(categories)):
        raise ValueError("Unsupported or duplicate delegation categories")
    if type(duration_seconds) is not int or not 60 <= duration_seconds <= 30 * 86400:
        raise ValueError("Delegation duration exceeds 30-day limit")
    now = int(time.time()) if issued_at is None else issued_at
    claims = {
        "schema": "aura.owner-autonomy-delegation.v1",
        "principal_id": "local_owner",
        "issued_at": now,
        "expires_at": now + duration_seconds,
        "categories": sorted(categories),
        "scope": "static-review-only",
        "auto_activation": False,
    }
    signature = signer.sign(_canonical(claims))
    return {
        "claims": claims,
        "signature_b64": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def _root(path: str) -> Path:
    root = Path(path)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise PermissionError("Existing Owner protected root required")
    _checked_path(root)
    checkout = Path(__file__).resolve().parents[4]
    if root.resolve().is_relative_to(checkout):
        raise PermissionError("Owner trust root must be outside checkout")
    if os.name != "nt":
        raise PermissionError("Owner DPAPI signer requires an isolated Windows account")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    require_private_acl(root)
    return root


def _write_owner_document(path: Path, data: bytes) -> None:
    from aura_core.evolution.windows_owner_storage import harden_private_acl
    if path.exists() or path.is_symlink():
        raise FileExistsError("Existing Owner delegation must be revoked explicitly")
    path.write_bytes(data)
    try:
        harden_private_acl(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def sign_delegation(*, owner_root: str, categories: tuple[str, ...],
                    duration_seconds: int = 86400) -> str:
    root = _root(owner_root)
    from aura_core.evolution.windows_owner_storage import (
        load_owner_seed_dpapi, require_private_acl,
    )
    key_path = root / "owner-receipt-key.dpapi"
    passkey = root / "owner-passkey.json"
    require_private_acl(passkey)  # Enrollment must already be completed.
    signer = load_owner_seed_dpapi(key_path)
    doc = make_review_delegation(
        signer, categories=categories, duration_seconds=duration_seconds,
    )
    public = signer.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    raw = signer.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_file = root / "autonomous_delegation.pub.pem"
    declaration = root / "autonomous_delegation.json"
    # No force-overwrite and never mint private material in AURA Core.
    _write_owner_document(key_file, public)
    try:
        _write_owner_document(declaration, json.dumps(
            doc, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
    except BaseException:
        key_file.unlink(missing_ok=True)
        raise
    return hashlib.sha256(raw).hexdigest()


def revoke_delegation(*, owner_root: str) -> bool:
    root = _root(owner_root)
    from aura_core.evolution.windows_owner_storage import require_private_acl
    declaration = root / "autonomous_delegation.json"
    key = root / "autonomous_delegation.pub.pem"
    if not declaration.is_file():
        return False
    require_private_acl(declaration)
    if key.exists():
        require_private_acl(key)
    declaration.unlink()
    if key.exists():
        key.unlink()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m aura_core.evolution.owner_cli")
    sub = parser.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("sign-delegation")
    create.add_argument("--owner-root", default=os.getenv(
        "AURA_EVOLUTION_OWNER_ROOT", r"D:\AURA\Evolution\owner"))
    create.add_argument("--categories", nargs="+", choices=sorted(_DEPLOYED_CATEGORIES),
                        required=True)
    create.add_argument("--days", type=int, default=1)
    create.add_argument("--confirm-static-review-only", action="store_true")
    revoke = sub.add_parser("revoke-delegation")
    revoke.add_argument("--owner-root", default=os.getenv(
        "AURA_EVOLUTION_OWNER_ROOT", r"D:\AURA\Evolution\owner"))
    revoke.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.operation == "sign-delegation":
        if not args.confirm_static_review_only:
            parser.error("Explicit static-review-only acknowledgement required")
        fingerprint = sign_delegation(
            owner_root=args.owner_root, categories=tuple(args.categories),
            duration_seconds=args.days * 86400,
        )
        print("Review-only Owner delegation signed with protected DPAPI identity")
        print("AURA_EVOLUTION_DELEGATION_KEY_SHA256=" + fingerprint)
        print("No live MCP activation or sandbox attestation was granted")
    elif args.operation == "revoke-delegation":
        if not args.confirm:
            parser.error("Explicit Owner revocation confirmation required")
        print("Delegation revoked" if revoke_delegation(owner_root=args.owner_root)
              else "Delegation was already absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
