"""Fail-closed assembler for independently produced physical Windows receipts.

This module NEVER captures hardware, generates signing keys, signs measurements,
mints Owner permission, or silently accepts simulations. The private Ed25519 key
and real measurement collector belong to a separately provisioned signer.
Only previously pinned public keys and six signed physical receipts are inputs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

from aura_core.acceptance.hardware_gate import (
    HardwareAcceptanceGate,
    HardwareCheck,
    PinnedEd25519HardwareVerifier,
    SignedHardwareEvidence,
)

_MAX_RECEIPT_BYTES = 16_000
_MAX_KEY_BYTES = 8_192


def _read_json(path: Path, *, limit: int) -> object:
    raw = path.read_bytes()
    if not 0 < len(raw) <= limit:
        raise ValueError("Missing or oversized independent evidence input")
    return json.loads(raw.decode("utf-8"))


def _atomic_write(path: Path, contents: bytes) -> None:
    if not path.parent.is_dir():
        raise ValueError("Output directory must already exist")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".aura-b2-evidence-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def assemble(
    *, receipt_dir: Path, pin_source: Path,
    evidence_output: Path, public_keys_output: Path,
) -> dict[str, object]:
    """Publish only after six authentic, fresh, policy-compliant receipts pass."""
    if not receipt_dir.is_dir():
        raise ValueError("Independent receipt directory is missing")
    if evidence_output.resolve() == public_keys_output.resolve():
        raise ValueError("Evidence and trust outputs must be different files")
    source_pins = _read_json(pin_source, limit=_MAX_KEY_BYTES)
    if not isinstance(source_pins, dict):
        raise ValueError("Independent signer pin set must be an object")
    public = {}
    for signer_id, encoded in source_pins.items():
        if type(encoded) is not str:
            raise ValueError("Public key must be hex-encoded")
        public[signer_id] = bytes.fromhex(encoded)
    verifier = PinnedEd25519HardwareVerifier(trusted_public_keys=public)

    expected = set(SignedHardwareEvidence.__dataclass_fields__)
    evidence: list[SignedHardwareEvidence] = []
    public_rows: list[dict] = []
    for check in HardwareCheck:
        path = receipt_dir / (check.value + ".json")
        row = _read_json(path, limit=_MAX_RECEIPT_BYTES)
        if type(row) is not dict or set(row) != expected or row.get("check") != check.value:
            raise ValueError("Missing or malformed independent physical receipt: " + check.value)
        item = SignedHardwareEvidence(**{**row, "check": check})
        evidence.append(item)
        public_rows.append(row)

    run_id = evidence[0].run_id
    report = asyncio.run(HardwareAcceptanceGate(verifier=verifier).assess(
        run_id=run_id, evidence=tuple(evidence),
    ))
    if not (report.accepted and report.independently_signed and report.checked == 6):
        raise ValueError("Physical evidence rejected: " + report.reason)

    output = {"run_id": run_id, "evidence": public_rows}
    raw_evidence = json.dumps(output, ensure_ascii=True, indent=2).encode("utf-8")
    raw_pins = json.dumps(source_pins, ensure_ascii=True, indent=2).encode("utf-8")
    if len(raw_evidence) > 64_000 or len(raw_pins) > _MAX_KEY_BYTES:
        raise ValueError("Output evidence exceeds verifier size budget")
    for destination in (evidence_output, public_keys_output):
        if destination.resolve() == pin_source.resolve():
            raise ValueError("Do not overwrite independent trust source")
        if destination.resolve().is_relative_to(receipt_dir.resolve()):
            raise ValueError("Do not overwrite independent signer receipts")

    _atomic_write(evidence_output, raw_evidence)
    _atomic_write(public_keys_output, raw_pins)
    return {
        "status": "INDEPENDENT_SIGNED_RECEIPTS_ASSEMBLED",
        "run_id": run_id,
        "checked": report.checked,
        "owner_capability_approved": False,
        "note": "Signature validity is not proof of physical collection or Owner tool permission.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify and assemble external physical acceptance receipts")
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--pin-source", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--public-keys-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = assemble(
            receipt_dir=args.receipt_dir, pin_source=args.pin_source,
            evidence_output=args.evidence_output,
            public_keys_output=args.public_keys_output,
        )
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({
            "status": "BLOCKED_UNVERIFIED",
            "error_type": type(exc).__name__,
            "hardware_verified": False,
            "owner_capability_approved": False,
        }))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
