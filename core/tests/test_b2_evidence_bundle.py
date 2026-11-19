"""Negative-path proof that AURA cannot mint its own independent receipts."""
from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from aura_core.acceptance.b2_evidence_bundle import main
from aura_core.acceptance.hardware_gate import HardwareCheck


def _args(tmp_path: Path):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    pins = tmp_path / "external-pins.json"
    pins.write_text(json.dumps({"independent_lab": "01" * 32}))
    evidence = tmp_path / "SIGNED_EVIDENCE.json"
    copied_pins = tmp_path / "PINNED_PUBLIC_KEYS.json"
    return receipts, pins, evidence, copied_pins


def _invoke(receipts, pins, evidence, copied_pins):
    return main([
        "--receipt-dir", str(receipts),
        "--pin-source", str(pins),
        "--evidence-output", str(evidence),
        "--public-keys-output", str(copied_pins),
    ])


def test_missing_real_hardware_proofs_create_no_acceptance_files(tmp_path):
    receipts, pins, evidence, copied_pins = _args(tmp_path)
    assert _invoke(receipts, pins, evidence, copied_pins) == 2
    assert not evidence.exists() and not copied_pins.exists()


def test_claimed_metrics_without_independent_ed25519_signature_never_pass(tmp_path):
    receipts, pins, evidence, copied_pins = _args(tmp_path)
    run_id = str(uuid4())
    for check in HardwareCheck:
        (receipts / (check.value + ".json")).write_text(json.dumps({
            "run_id": run_id, "check": check.value,
            "signer_id": "independent_lab", "device_digest": "1" * 64,
            "timestamp": int(time.time()), "nonce": "a" * 32,
            "metrics": {"p95_ms": 1.0}, "signature_b64": "not-a-signature",
            "schema": "aura.hardware-evidence.v1",
            "environment": "physical_windows",
        }))
    assert _invoke(receipts, pins, evidence, copied_pins) == 2
    assert not evidence.exists() and not copied_pins.exists()


def test_untrusted_pin_configuration_and_output_collision_fail_closed(tmp_path):
    receipts, pins, evidence, copied_pins = _args(tmp_path)
    pins.write_text("{}")
    assert _invoke(receipts, pins, evidence, copied_pins) == 2
    assert _invoke(receipts, pins, evidence, evidence) == 2
    assert not evidence.exists()
