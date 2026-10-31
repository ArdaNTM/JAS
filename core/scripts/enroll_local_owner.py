"""Explicit one-shot Windows Hello enrollment, never run by AURA Core."""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from aura_core.evolution.owner_enrollment import ProtectedEnrollment
from aura_core.evolution.owner_enrollment_http import create_enrollment_app
from aura_core.evolution.owner_receipt import DIGEST


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-token-file", type=Path, required=True)
    parser.add_argument("--owner-config-output", type=Path, required=True)
    parser.add_argument("--policy-digest", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    token = args.bootstrap_token_file
    if (not token.is_absolute() or token.is_symlink() or not token.is_file()
        or token.resolve().is_relative_to(root)
        or token.stat().st_size > 256):
        parser.error("Owner bootstrap file must be protected and outside checkout")
    if not DIGEST.fullmatch(args.policy_digest):
        parser.error("A pinned 64-character policy SHA-256 digest is required")
    from os import name
    if name == "posix" and token.stat().st_mode & 0o077:
        parser.error("Owner bootstrap token file must have mode 0600")
    bootstrap = token.read_text(encoding="ascii").strip()
    ceremony = ProtectedEnrollment(
        bootstrap_secret=bootstrap,
        config_output=args.owner_config_output,
        policy_digest=args.policy_digest,
    )
    # Local owner-hostname only. Port 8766 must be free; this service and the
    # owner review server NEVER run concurrently.
    uvicorn.run(create_enrollment_app(ceremony=ceremony),
                host="127.0.0.1", port=8766,
                access_log=False, workers=1, reload=False)


if __name__ == "__main__":
    main()
