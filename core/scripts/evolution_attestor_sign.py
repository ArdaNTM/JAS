"""Operator-controlled OUT-OF-CORE Ed25519 signer for trusted runner observations.

This CLI MUST run in a separate, access-controlled attestor identity, outside
the AURA Core/sandbox environment. Never expose it as an MCP tool. It does not
execute or inspect container runs; it signs independently observed evidence
only, so a trusted runner and protected observation channel are prerequisites.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution.sandbox_attestor import (
    DOMAIN, SCHEMA, SandboxClaims, SignedSandboxAttestation, canonical_claims,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _protected_file(path: Path) -> bytes:
    if path.is_symlink():
        raise PermissionError("Attestor input must not be a symlink")
    resolved = path.resolve(strict=True)
    if resolved.is_relative_to(SOURCE_ROOT):
        raise PermissionError("Attestor private inputs cannot reside in AURA checkout")
    if not resolved.is_file() or resolved.stat().st_size > 16384:
        raise PermissionError("Invalid attestor input")
    # On POSIX reject overly permissive key/observation permissions.
    if os.name == "posix" and (resolved.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)):
        raise PermissionError("Attestor inputs must be owner-only")
    with resolved.open("rb") as stream:
        data = stream.read(16385)
    if len(data) > 16384:
        raise PermissionError("Attestor input exceeds budget")
    return data


def sign_observation(*, observation: Path, private_key: Path, key_id: str) -> SignedSandboxAttestation:
    """Sign ONLY an independently observed, trusted-runner-owned record."""
    data = json.loads(_protected_file(observation))
    if not isinstance(data, dict) or set(data) != set(SandboxClaims.__dataclass_fields__):
        raise ValueError("Unexpected runner evidence schema")
    claims = SandboxClaims(**data)
    key = load_pem_private_key(_protected_file(private_key), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Only Ed25519 signing keys are accepted")
    signature = key.sign(DOMAIN + canonical_claims(claims))
    return SignedSandboxAttestation(
        key_id=key_id, claims=claims,
        signature_b64=base64.b64encode(signature).decode("ascii"), schema=SCHEMA,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted attestor signer (NOT an AURA MCP tool)")
    parser.add_argument("--trusted-observation", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.is_symlink() or args.output.resolve().is_relative_to(SOURCE_ROOT):
        parser.error("Output must be in protected external attestor storage")
    envelope = sign_observation(
        observation=args.trusted_observation, private_key=args.private_key,
        key_id=args.key_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(envelope.to_dict(), stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    print("Signed independent observation; public verifier must still check policy and owner approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
