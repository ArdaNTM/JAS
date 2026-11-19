"""Verify six REAL independently signed Windows hardware measurements.

This tool has no signing ability, mock mode, device automation bypass or Owner
approval issuance. Only trusted *public keys* are supplied by the operator;
the private hardware laboratory signer must run under a separate Windows OS
identity and must physically collect WebAuthn, microphone+Nirvana barge-in,
dual display/hotplug and emergency-stop observations. A verified JSON result
is not an authorization token for AURA Kernel or MCP Gateway.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from aura_core.acceptance.hardware_gate import (
    HardwareAcceptanceGate, HardwareCheck, HardwareThresholds,
    PinnedEd25519HardwareVerifier, SignedHardwareEvidence,
)


async def verify(
    *, evidence_path: Path, keys_path: Path,
) -> dict[str, object]:
    if not evidence_path.is_file() or not keys_path.is_file():
        raise ValueError("External evidence and trusted-public-key files must exist")
    if evidence_path.stat().st_size > 64_000 or keys_path.stat().st_size > 8_192:
        raise ValueError("Evidence or trust configuration is unbounded")
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    trusted = json.loads(keys_path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"run_id", "evidence"}
            or not isinstance(data["evidence"], list) or len(data["evidence"]) != 6
            or not isinstance(trusted, dict)):
        raise ValueError("Missing physical evidence or signer configuration")
    public = {name: bytes.fromhex(value) for name, value in trusted.items()}
    verifier = PinnedEd25519HardwareVerifier(trusted_public_keys=public)
    items: list[SignedHardwareEvidence] = []
    for row in data["evidence"]:
        if not isinstance(row, dict) or set(row) != set(SignedHardwareEvidence.__dataclass_fields__):
            raise ValueError("Invalid signed physical hardware envelope")
        items.append(SignedHardwareEvidence(
            **{**row, "check": HardwareCheck(row["check"])}
        ))
    report = await HardwareAcceptanceGate(verifier=verifier).assess(
        run_id=data["run_id"], evidence=tuple(items),
    )
    return {
        "status": "HARDWARE_PHYSICAL_EVIDENCE_VALIDATED" if report.accepted else "HARDWARE_ACCEPTANCE_BLOCKED",
        "hardware_verified": report.accepted and report.independently_signed,
        "checks_verified": report.checked,
        "total_checks": 6,
        "reason": report.reason,
        "owner_capability_approved": False,
        "benchmark_score": None,
        "note": "Independent physical evidence only; no Kernel activation or release promotion.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--trusted-public-keys", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(verify(
            evidence_path=args.evidence, keys_path=args.trusted_public_keys,
        ))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report = {
            "status": "HARDWARE_ACCEPTANCE_BLOCKED",
            "hardware_verified": False, "error_type": type(exc).__name__,
        }
    print(json.dumps(report, indent=2))
    return 0 if report["hardware_verified"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
