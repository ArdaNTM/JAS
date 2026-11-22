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


def make_activation_delegation(
    signer, *, categories: tuple[str, ...], image: str,
    policy_sha256: str, tests_sha256: str,
    attestor_key_sha256: str, attestor_runner_id: str,
    days: int = 1, max_tools: int = 8, min_score: int = 75,
    issued_at: int | None = None,
) -> dict:
    from aura_core.evolution.activation_delegation import (
        SCHEMA, canonical, validated_claims,
    )
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError("Only 1-7 day delegated activation allowed")
    now = int(time.time()) if issued_at is None else issued_at
    claims = validated_claims({
        "schema": SCHEMA, "principal_id": "local_owner",
        "issued_at": now, "expires_at": now + days * 86400,
        "categories": sorted(categories), "scope": "offline-container-stdio",
        "auto_activation": True, "oci_image": image,
        "policy_sha256": policy_sha256, "tests_sha256": tests_sha256,
        "attestor_key_sha256": attestor_key_sha256,
        "attestor_runner_id": attestor_runner_id,
        "max_tools": max_tools, "min_score": min_score,
    }, now=now)
    signature = signer.sign(canonical(claims))
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


def _persist_owner_signature(root: Path, signer, document: dict) -> str:
    """Non-overwriting signed declaration; never mints arbitrary new Owner keys."""
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
    if key_file.exists() or declaration.exists():
        raise FileExistsError("Revoke existing delegation before signing a new scope")
    _write_owner_document(key_file, public)
    try:
        _write_owner_document(declaration, json.dumps(
            document, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
    except BaseException:
        key_file.unlink(missing_ok=True)
        raise
    return hashlib.sha256(raw).hexdigest()


def _owner_signer(root: Path):
    from aura_core.evolution.windows_owner_storage import (
        load_owner_seed_dpapi, require_private_acl,
    )
    require_private_acl(root / "owner-passkey.json")
    return load_owner_seed_dpapi(root / "owner-receipt-key.dpapi")


def sign_activation_delegation(
    *, owner_root: str, categories: tuple[str, ...], image: str,
    policy_sha256: str, tests_sha256: str, attestor_key_sha256: str,
    attestor_runner_id: str, days: int = 1,
    max_tools: int = 8, min_score: int = 75,
) -> str:
    root = _root(owner_root)
    signer = _owner_signer(root)
    claims = make_activation_delegation(
        signer, categories=categories, image=image,
        policy_sha256=policy_sha256, tests_sha256=tests_sha256,
        attestor_key_sha256=attestor_key_sha256,
        attestor_runner_id=attestor_runner_id, days=days,
        max_tools=max_tools, min_score=min_score,
    )
    return _persist_owner_signature(root, signer, claims)


def sign_delegation(*, owner_root: str, categories: tuple[str, ...],
                    duration_seconds: int = 86400) -> str:
    root = _root(owner_root)
    signer = _owner_signer(root)
    document = make_review_delegation(
        signer, categories=categories, duration_seconds=duration_seconds,
    )
    return _persist_owner_signature(root, signer, document)

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
    activation = sub.add_parser("sign-activation-delegation")
    activation.add_argument("--owner-root", default=os.getenv(
        "AURA_EVOLUTION_OWNER_ROOT", r"D:\AURA\Evolution\owner"))
    activation.add_argument("--categories", nargs="+", choices=sorted(_DEPLOYED_CATEGORIES),
                            required=True)
    activation.add_argument("--image", required=True)
    activation.add_argument("--policy-sha256", required=True)
    activation.add_argument("--tests-sha256", required=True)
    activation.add_argument("--attestor-key-sha256", required=True)
    activation.add_argument("--attestor-runner-id", required=True)
    activation.add_argument("--max-tools", type=int, default=8)
    activation.add_argument("--min-score", type=int, default=75)
    activation.add_argument("--days", type=int, default=1)
    activation.add_argument("--confirm-owner-authority", action="store_true")
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
    elif args.operation == "sign-activation-delegation":
        if not args.confirm_owner_authority:
            parser.error("Explicit owner authority acknowledgement required")
        fingerprint = sign_activation_delegation(
            owner_root=args.owner_root, categories=tuple(args.categories),
            image=args.image, policy_sha256=args.policy_sha256,
            tests_sha256=args.tests_sha256,
            attestor_key_sha256=args.attestor_key_sha256,
            attestor_runner_id=args.attestor_runner_id,
            max_tools=args.max_tools, min_score=args.min_score,
            days=args.days,
        )
        print("Isolated offline MCP Owner delegation signed with protected DPAPI identity")
        print("AURA_EVOLUTION_DELEGATION_KEY_SHA256=" + fingerprint)
        print("Activation still requires independent trusted sandbox attestation")
    elif args.operation == "revoke-delegation":
        if not args.confirm:
            parser.error("Explicit Owner revocation confirmation required")
        print("Delegation revoked" if revoke_delegation(owner_root=args.owner_root)
              else "Delegation was already absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
