"""Run one REAL OSWorld-V2.1 task in its official disposable Docker VM.

Unlike scripts/osworld_v2_lab.py's dry-run contract, this entry point actually
constructs DesktopEnv(provider_name='docker'), resets a signed-release task,
dispatches generated actions ONLY through a real AURA MCPGateway and waits for
external Windows Hello approval from Owner Control Plane. No model has direct
VM access. Operator must provision upstream checkout/assets/websites/image and
verify an independent VM/network firewall *before* invoking this command.

This script cannot provision a Windows Hello credential, sign an Owner receipt,
grant approval, or infer firewall isolation. A score is emitted only if the
official upstream evaluator returns an accepted numeric score; crashes or
timeouts never produce a fictitious zero/success.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from aura_core.enterprise.approval_store import SQLiteApprovalStore
from aura_core.osworld.live_vm import evaluate_live_vm
from aura_core.osworld.runtime import (
    LocalModelVMPlanner, OwnerApprovalPolling, compose_vm_gateway, policy_digest,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE = "osworld-v2.1"


def _run_checked(command: list[str], *, cwd: Path, timeout: int = 20) -> str:
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True,
        check=True, timeout=timeout, shell=False,
    )
    return result.stdout.strip()


def inspect_real_environment(
    *, upstream: Path, expected_commit: str, assets: Path,
    task_file: Path, owner_db: Path, website_suffix: str,
) -> dict:
    """Check exact release components before any VM is started.

    The official gated assets and self-hosted sites are operator-provided.
    This check does not download files or run arbitrary Git-sourced hooks.
    """
    upstream = upstream.resolve(strict=True)
    assets = assets.resolve(strict=True)
    task_file = task_file.resolve(strict=True)
    owner_db = owner_db.resolve(strict=True)
    if not SHA.fullmatch(expected_commit):
        raise ValueError("The OSWorld code commit must be pinned to 40 hex digits")
    if not (upstream / "desktop_env").is_dir() or not (upstream / "run.py").is_file():
        raise ValueError("Official OSWorld-V2 checkout missing")
    if not task_file.is_relative_to(upstream) or task_file.suffix != ".json":
        raise ValueError("Official OSWorld task config must be inside pinned checkout")
    if not assets.is_dir() or not any(assets.iterdir()):
        raise ValueError("Gated OSWorld-V2.1 asset directory not provisioned")
    if not owner_db.is_file() or owner_db.is_relative_to(upstream):
        raise PermissionError("Separate protected owner approval DB required")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(owner_db.parent)
        require_private_acl(owner_db)
    elif owner_db.stat().st_mode & 0o077:
        raise PermissionError("Owner approval DB cannot be group/world accessible")
    if not website_suffix or any(c in website_suffix for c in " /:@\\"):
        raise ValueError("Operator must configure the pinned self-hosted website suffix")
    head = _run_checked(["git", "rev-parse", "HEAD"], cwd=upstream)
    if head != expected_commit:
        raise ValueError("Upstream source does not match pinned Git commit")
    tag = _run_checked(["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=upstream)
    if tag != RELEASE:
        raise ValueError("OSWorld source is not exactly the osworld-v2.1 tag")
    if os.environ.get("AURA_OSWORLD_VM_FIREWALL_VERIFIED") != "1":
        raise PermissionError("Operator must independently verify VM network isolation")
    _run_checked(["docker", "info", "--format", "{{.ServerVersion}}"], cwd=upstream)
    if task_file.stat().st_size > 100_000:
        raise ValueError("Unbounded official task file")
    task = json.loads(task_file.read_text(encoding="utf-8"))
    if not isinstance(task, dict) or not all(
        isinstance(task.get(k), str) and task[k] for k in ("id", "instruction")
    ) or "evaluator" not in task:
        raise ValueError("Invalid official task schema")
    return task


async def run(args: argparse.Namespace) -> dict:
    if not args.allow_real_vm:
        raise PermissionError("Explicit --allow-real-vm operator decision required")
    upstream = Path(args.upstream).resolve(strict=True)
    task = await asyncio.to_thread(
        inspect_real_environment, upstream=upstream,
        expected_commit=args.upstream_commit,
        assets=Path(args.assets),
        task_file=Path(args.task_file),
        owner_db=Path(args.owner_db),
        website_suffix=args.website_suffix,
    )
    key = bytes.fromhex(os.environ.get("AURA_APPROVAL_FINGERPRINT_KEY_HEX", ""))
    if len(key) < 32:
        raise PermissionError("Strong Gateway approval key must be in protected environment")
    # Native OSWorld imported ONLY after pinned tag and commit checks.
    sys.path.insert(0, str(upstream))
    from desktop_env.desktop_env import DesktopEnv
    os.environ["OSWORLD_FILE_BASE_URL"] = str(Path(args.assets).resolve(strict=True))
    os.environ["OSWORLD_BENCHMARK_RELEASE"] = RELEASE
    os.environ["WEBSITE_HOST_SUFFIX"] = args.website_suffix
    env = None
    with SQLiteApprovalStore(str(Path(args.owner_db).resolve(strict=True))) as approvals:
        try:
            env = await asyncio.to_thread(
                DesktopEnv, provider_name="docker", os_type="Ubuntu",
                headless=True, action_space="pyautogui",
                screen_size=(1920, 1080), require_a11y_tree=True,
            )
            gateway = compose_vm_gateway(
                environment=env, store=approvals, fingerprint_key=key,
            )
            print(json.dumps({
                "mode": "REAL_VM_RUNNING",
                "release": RELEASE,
                "owner_challenge_policy_digest": policy_digest(),
                "task_id": task["id"],
                "note": "Every action waits for external passkey approval in Owner Control Plane.",
            }), file=sys.stderr, flush=True)
            result = await evaluate_live_vm(
                environment=env, gateway=gateway,
                planner=LocalModelVMPlanner(
                    base_url=args.ollama_url, model=args.model,
                ),
                approvals=OwnerApprovalPolling(approvals),
                task_config=task, max_actions=args.max_actions,
                wall_time_seconds=args.wall_time,
            )
            return {
                "status": "REAL_OSWORLD_VM_EVALUATION",
                "task_id": result.task_id,
                "actions_attempted": result.actions_attempted,
                "all_actions_gateway_approved": result.all_actions_gateway_approved,
                "benchmark_release": RELEASE,
                "score": result.score,
                "official_task_evaluated": result.score is not None,
                "physical_hardware_verified": False,
                "leaderboard_verified": False,
            }
        finally:
            if env is not None:
                await asyncio.to_thread(env.close)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--website-suffix", required=True)
    parser.add_argument("--owner-db", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--max-actions", type=int, default=8)
    parser.add_argument("--wall-time", type=int, default=120)
    parser.add_argument("--allow-real-vm", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (ValueError, TypeError, PermissionError, OSError, subprocess.SubprocessError, TimeoutError, RuntimeError) as exc:
        print(json.dumps({
            "status": "LIVE_EVALUATION_BLOCKED",
            "benchmark_score": None, "hardware_verified": False,
            "error_type": type(exc).__name__,
        }, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
