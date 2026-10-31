"""Run the independent owner UI under a protected OS account.

Opt-in, fail-closed. Requires pre-enrolled WebAuthn ES256 credential and
owner-provisioned database files outside the AURA checkout. Not launched by
Start-AURA or enabled by AURA_BACKGROUND_THINKING_ENABLED.
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
            private_data = protected_path(owner_receipt_key).read_bytes()
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
    parser.add_argument("--owner-config", required=True)
    parser.add_argument("--approval-db", required=True)
    parser.add_argument("--challenge-db", required=True)
    parser.add_argument("--owner-receipt-key")
    parser.add_argument("--owner-receipt-key-id")
    args = parser.parse_args()
    app = build_app(
        owner_config=args.owner_config, approval_db=args.approval_db,
        challenge_db=args.challenge_db,
        owner_receipt_key=args.owner_receipt_key,
        owner_receipt_key_id=args.owner_receipt_key_id,
    )
    # No --reload, no multi-worker, no exposed NIC.
    uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False,
                reload=False, workers=1)


if __name__ == "__main__":
    main()
