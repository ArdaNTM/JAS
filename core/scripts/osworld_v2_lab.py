"""Offline OSWorld-V2.1 acceptance contract. Never launches a desktop or network call.

Official evaluation requires separately provisioned, version-pinned and isolated
OSWorld host/VM tasks. This script checks release provenance and writes a safe
local dry-run manifest to stdout; it is NOT an official benchmark score.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RELEASE = "osworld-v2.1"
MANIFEST = {
    "schema": "aura.stage-c.osworld-lab.v1",
    "release": RELEASE,
    "code_tag": RELEASE,
    "task_assets_tag": RELEASE,
    "task_classes_tag": RELEASE,
    "website_tag": RELEASE,
    "environment": "isolated_disposable_vm",
    "execution": "disabled_until_explicit_evaluation_setup",
    "required_evidence": [
        "gateway_approval_per_action",
        "cross_origin_denied",
        "budget_8_steps_120_seconds",
        "kill_switch_survives_restart",
        "no_replay_after_uncertain_action",
        "secret_redaction",
        "agent_trajectory_and_verifier_log",
    ],
}


def validate_manifest(manifest: dict) -> None:
    for field in ("release", "code_tag", "task_assets_tag", "task_classes_tag", "website_tag"):
        if manifest.get(field) != RELEASE:
            raise ValueError("OSWorld-V2 benchmark components must share the pinned release")
    if manifest.get("environment") != "isolated_disposable_vm":
        raise ValueError("OSWorld desktop evaluation must run in a disposable VM")


def main(argv=None) -> int:
    # Opt-in real provider. Dry-run stays the safe default and never claims a
    # VM score. A real run requires external Docker, signed Owner approvals,
    # gated OSWorld assets, the pinned osworld-v2.1 tag, and a disposable VM.
    import sys
    selected = list(sys.argv[1:] if argv is None else argv)
    if selected and selected[0] == "--live":
        from run_osworld_v2_live import main as live_main
        return live_main(selected[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    manifest = (json.loads(args.manifest.read_text("utf-8")) if args.manifest else MANIFEST)
    validate_manifest(manifest)
    print(json.dumps({"status": "DRY_RUN_ONLY", "benchmark_score": None, "manifest": manifest},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
