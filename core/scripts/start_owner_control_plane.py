"""Run the independent owner UI under a protected OS account.

Passkey approval requires pre-enrolled WebAuthn ES256 credentials and private
owner files outside checkout. Until enrollment, the local CLI exposes only the
separate untrusted read-only discovery catalog, never approval/activation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import uvicorn

from aura_core.enterprise.approval_store import SQLiteApprovalStore
from aura_core.evolution.owner_challenge import TrustedOwnerPasskeyDecider
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier
from aura_core.evolution.owner_control_plane import create_owner_control_plane
from aura_core.evolution.owner_receipt import OwnerReceiptIssuer
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def protected_path(value: str) -> Path:
    path = Path(value)
    project_root = Path(__file__).resolve().parents[2]
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Owner storage must be a pre-provisioned absolute regular file")
    if path.resolve().is_relative_to(project_root):
        raise PermissionError("Owner storage cannot live in AURA checkout")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise PermissionError("Owner storage must be owner-only (0600)")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        require_private_acl(path)
    return path


def build_app(*, owner_config: str, approval_db: str, challenge_db: str,
              owner_receipt_key: str | None = None, owner_receipt_key_id: str | None = None):
    config_path = protected_path(owner_config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected = {"rp_id", "origin", "credential_id", "public_key_pem", "policy_digest"}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError("Owner config must contain only the expected public-key fields")
    if config["origin"] != "http://localhost:8766" or config["rp_id"] != "localhost":
        raise ValueError("Owner UI origin must remain exactly localhost:8766")
    store = SQLiteApprovalStore(str(protected_path(approval_db)))
    try:
        verifier = OwnerPasskeyVerifier(
            rp_id=config["rp_id"], origin=config["origin"],
            credential_id=config["credential_id"],
            public_key_pem=config["public_key_pem"].encode("ascii"),
        )
        decider = TrustedOwnerPasskeyDecider(
            database_path=protected_path(challenge_db), owner_verifier=verifier,
            approvals=store, policy_digest=config["policy_digest"],
            credential_id=config["credential_id"],
        )
        issuer = None
        if (owner_receipt_key is None) != (owner_receipt_key_id is None):
            raise ValueError("Receipt key and key ID must be configured together")
        if owner_receipt_key is not None:
            protected = protected_path(owner_receipt_key)
            if os.name == "nt":
                if protected.suffix.lower() != ".dpapi":
                    raise PermissionError("Windows owner signing keys must be user-scoped DPAPI blobs")
                from aura_core.evolution.windows_owner_storage import load_owner_seed_dpapi
                signing_key = load_owner_seed_dpapi(protected)
            else:
                private_data = protected.read_bytes()
                if len(private_data) > 8192:
                    raise ValueError("Owner signing key file too large")
                signing_key = load_pem_private_key(private_data, password=None)
                if not isinstance(signing_key, Ed25519PrivateKey):
                    raise ValueError("Owner approval issuer requires Ed25519 key")
            issuer = OwnerReceiptIssuer(
                key_id=owner_receipt_key_id,
                private_key=signing_key,
                policy_digest=config["policy_digest"],
            )
        app = create_owner_control_plane(approvals=store, decider=decider,
                                         receipt_issuer=issuer)
        return app
    except Exception:
        store.close()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    # Existing owner identity must be explicitly provisioned by the dedicated
    # Owner account. No automatic enrollment or insecure key generation.
    parser.add_argument("--owner-root", default=None)
    parser.add_argument(
        "--require-enrollment", action="store_true",
        help="Fail closed instead of offering read-only catalog review",
    )
    parser.add_argument("--owner-config")
    parser.add_argument("--approval-db")
    parser.add_argument("--challenge-db")
    parser.add_argument("--owner-receipt-key")
    parser.add_argument("--owner-receipt-key-id")
    args = parser.parse_args()
    evolution_root = os.environ.get("AURA_EVOLUTION_ROOT") or (
        r"D:\AURA\Evolution" if os.name == "nt" else None
    )
    root = Path(args.owner_root) if args.owner_root else (
        Path(evolution_root) / "owner" if evolution_root else None
    )
    if root is None and not all((args.owner_config, args.approval_db, args.challenge_db)):
        parser.error("Set AURA_EVOLUTION_ROOT or explicit protected Owner paths")
    if root is not None and (not root.is_absolute() or root.is_symlink()):
        parser.error("Owner root must be an absolute non-symlink directory")
    def owner_file(explicit: str | None, filename: str) -> str:
        if explicit is not None:
            return explicit
        assert root is not None
        return str(root / filename)
    config_path = Path(owner_file(args.owner_config, "owner-passkey.json"))
    # Only the implicit, not-yet-enrolled local Owner can choose inert review.
    # Explicit credentials, partial/corrupt passkeys, and strict mode must
    # always go through build_app() with protected_path() NTFS/DPAPI checks.
    explicitly_configured = any((
        args.owner_config, args.approval_db, args.challenge_db,
        args.owner_receipt_key, args.owner_receipt_key_id,
    ))
    if (not args.require_enrollment and not explicitly_configured
            and not config_path.exists() and not config_path.is_symlink()):
        if root is None:
            parser.error("Read-only discovery requires an external Evolution owner root")
        from aura_core.evolution.owner_control_plane_http import build_local_review_app
        app = build_local_review_app(root.parent)
    else:
        app = build_app(
            owner_config=str(config_path),
            approval_db=owner_file(args.approval_db, "approvals.sqlite"),
            challenge_db=owner_file(args.challenge_db, "challenges.sqlite"),
            owner_receipt_key=args.owner_receipt_key,
            owner_receipt_key_id=args.owner_receipt_key_id,
        )
    # No --reload, no multi-worker, no exposed NIC.
    uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False,
                reload=False, workers=1)


if __name__ == "__main__":
    main()
