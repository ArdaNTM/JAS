"""Stage C hardware acceptance checklist. Explicitly no passkey, mic or GUI side effects."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CHECKS = {
    "windows_hello": [
        "physical platform authenticator assertion verified with exact origin",
        "replay or altered challenge rejected",
        "no owner signing material in AURA process",
    ],
    "voice": [
        "physical microphone streaming and device disconnect measured",
        "barge-in cancels TTS without extra tool authorizations",
        "record first-audio and end-to-end latency p50/p95",
    ],
    "spatial_hud": [
        "two displays mixed DPI and negative virtual coordinates",
        "click-through disabled only after explicit user choice",
        "hotplug and emergency kill verified",
    ],
    "desktop_control": [
        "disposable Windows VM used; no personal secrets",
        "interactive session explicitly consented",
        "all off-screen and untrusted coordinates rejected",
        "approval expiry and uncertain outcome never replayed",
    ],
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, help="Existing JSON map of test IDs to operator-reviewed evidence")
    args = parser.parse_args(argv)
    supplied = json.loads(args.evidence.read_text("utf-8")) if args.evidence else {}
    if not isinstance(supplied, dict):
        raise ValueError("Evidence must be a JSON object")
    report = {
        "hardware_verified": False,  # No auto-attestation from self-reported evidence.
        "manual_review_required": True,
        "checks": CHECKS,
        "provided_evidence_names": [k for k in supplied if k in CHECKS],
        "note": "Operator must independently sign off on physical device evidence.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
