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
from aura_core.osworld.isolation import (
    BootIdentity, IsolationDenied, IsolationReceipt,
    load_pinned_public_keys, verify_receipt,
)
from aura_core.osworld.network_audit import inspect_topology
from aura_core.osworld.runtime_bridge import OSWorldSubprocessVM, COMMIT, VMBridgeError
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


async def _wait_for_independent_receipt(
    *, receipt_path: Path, expected: BootIdentity,
    trust: dict[str, bytes], timeout_seconds: int,
) -> IsolationReceipt:
    """Wait for externally created receipt; the AURA process cannot sign it."""
    if not 30 <= timeout_seconds <= 600:
        raise PermissionError("Signed receipt wait must remain bounded")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        if receipt_path.is_symlink():
            raise IsolationDenied("Receipt symlink refused")
        if receipt_path.is_file():
            if receipt_path.stat().st_size > 16_384:
                raise IsolationDenied("Unbounded physical network receipt")
            try:
                obj = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipt = IsolationReceipt.from_dict(obj)
                verify_receipt(receipt, expected=expected, trusted_public_keys=trust)
                return receipt
            except (ValueError, TypeError, json.JSONDecodeError, IsolationDenied):
                raise IsolationDenied("Independent receipt was rejected; do not retry in-place")
        await asyncio.sleep(0.5)
    raise IsolationDenied("Independent host receipt was not signed within the time window")


def _guard_signed_network(
    *, receipt: IsolationReceipt, boot: BootIdentity,
    trusted: dict[str, bytes],
) -> None:
    """Fail closed on expiry, mutation and network reattachment per MCP action."""
    verify_receipt(receipt, expected=boot, trusted_public_keys=trusted)
    running, ports, _ = inspect_topology(
        boot.container_id, expected_vm_hash=boot.vm_sha256,
    )
    if running != boot or ports != receipt.host_ports:
        raise IsolationDenied("Network topology or loopback mapping changed after audit")


async def run(args: argparse.Namespace) -> dict:
    if not args.allow_real_vm:
        raise PermissionError("Explicit --allow-real-vm operator consent required")
    upstream = args.upstream.resolve(strict=True)
    if args.upstream_commit != COMMIT:
        raise PermissionError("Only exact pinned osworld-v2.1 source commit is allowed")
    # The bridge separately checks Git revision, tag, and Python 3.12 interpreter.
    worker = Path(__file__).resolve().with_name("osworld_secure_worker.py")
    assets = None
    trust = None
    receipt_path = None
    task_id = None
    task_digest = None
    if not args.smoke:
        if (args.assets is None or args.owner_db is None
                or args.trusted_public_keys is None or args.receipt is None
                or args.task_id is None or args.approved_task_sha256 is None
                or not args.website_suffix):
            raise PermissionError("Live mode requires official assets, approved task, Owner DB and attestor trust")
        assets = args.assets.resolve(strict=True)
        if not assets.is_dir() or not any(assets.iterdir()):
            raise PermissionError("Gated official OSWorld assets not yet available")
        task_id = args.task_id
        task_digest = args.approved_task_sha256
        if not re.fullmatch(r"[0-9]{3}", task_id) or not re.fullmatch(r"[0-9a-f]{64}", task_digest):
            raise PermissionError("Official task ID and independently approved SHA-256 required")
        task_path = upstream / "evaluation_examples" / "task_class" / f"task_{task_id}.py"
        if not task_path.is_file() or not task_path.resolve().is_relative_to(upstream):
            raise PermissionError("Approved official V2.1 task class not present")
        import hashlib
        if hashlib.sha256(task_path.read_bytes()).hexdigest() != task_digest:
            raise PermissionError("Official task source differs from operator-approved hash")
        receipt_path = args.receipt.resolve(strict=False)
        if receipt_path.is_file() or receipt_path.is_symlink():
            raise IsolationDenied("Use a fresh, never-before-used receipt path for this VM")
        if not receipt_path.parent.is_dir():
            raise IsolationDenied("Independent attestor receipt directory missing")
        trust = load_pinned_public_keys(args.trusted_public_keys)
        owner_db = args.owner_db.resolve(strict=True)
        if owner_db.is_relative_to(Path(__file__).resolve().parents[2]) or not owner_db.is_file():
            raise PermissionError("Protected Owner approval store must exist outside the checkout")
        if os.name == "nt":
            from aura_core.evolution.windows_owner_storage import require_private_acl
            require_private_acl(owner_db.parent)
            require_private_acl(owner_db)
        elif owner_db.stat().st_mode & 0o077:
            raise PermissionError("Owner approval store cannot be group/world accessible")
        if any(c in args.website_suffix for c in " /:@\\") or len(args.website_suffix) > 128:
            raise PermissionError("Invalid pinned mock-site domain suffix")
    if not args.smoke:
        key = os.environ.get("AURA_APPROVAL_FINGERPRINT_KEY_HEX", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64,128}", key):
            raise PermissionError("Strong Owner approval fingerprint key missing")
    bridge = await asyncio.to_thread(
        OSWorldSubprocessVM, upstream=upstream, worker=worker,
        boot_timeout=args.boot_timeout, assets=assets,
        force_no_kvm=args.smoke,
        website_suffix=args.website_suffix if not args.smoke else None,
    )
    try:
        boot = bridge.boot
        assert boot is not None
        print(json.dumps({
            "phase": "SECURE_VM_BOOT",
            "container_id": boot.container_id,
            "network_id": boot.network_id,
            "vm_sha256": boot.vm_sha256,
            "kvm_mode": bridge.kvm_mode,
            "docker_network": "aura-osworld-v21-lab",
            "receipt_required": not args.smoke,
            "note": "An isolated network is necessary but not sufficient for verified egress policy.",
        }, indent=2), file=sys.stderr, flush=True)
        if args.smoke:
            return {
                "status": "VM_BOOT_ONLY",
                "kvm_mode": bridge.kvm_mode,
                "boot_verified": True,
                "network_isolation_verified": False,
                "benchmark_score": None,
                "hardware_verified": False,
                "note": "Smoke profile never executes a task or enables MCP actions.",
            }
        assert receipt_path is not None and trust is not None
        print(json.dumps({
            "phase": "WAIT_FOR_INDEPENDENT_NETWORK_ATTESTOR",
            "receipt_path": str(receipt_path),
            "container_id": boot.container_id,
            "vm_image": str(bridge.image),
            "note": "Run attest_osworld_network.py as a separate trusted operator process.",
        }, indent=2), file=sys.stderr, flush=True)
        evidence = await _wait_for_independent_receipt(
            receipt_path=receipt_path, expected=boot, trust=trust,
            timeout_seconds=args.attestation_wait,
        )
        def isolation_guard() -> None:
            _guard_signed_network(receipt=evidence, boot=boot, trusted=trust)
        await asyncio.to_thread(isolation_guard)
        with SQLiteApprovalStore(str(owner_db)) as approvals:
            gateway = compose_vm_gateway(
                environment=bridge, store=approvals,
                fingerprint_key=bytes.fromhex(
                    os.environ.get("AURA_APPROVAL_FINGERPRINT_KEY_HEX", "")
                ),
                isolation_guard=isolation_guard,
            )
            print(json.dumps({
                "phase": "SIGNED_ISOLATION_VERIFIED",
                "owner_challenge_policy_digest": policy_digest(),
                "task_id": task_id,
                "note": "Each action requires a separate Owner WebAuthn approval through MCP Gateway.",
            }, indent=2), file=sys.stderr, flush=True)
            result = await evaluate_live_vm(
                environment=bridge, gateway=gateway,
                planner=LocalModelVMPlanner(
                    base_url=args.ollama_url, model=args.model,
                ),
                approvals=OwnerApprovalPolling(approvals),
                task_config={
                    "id": task_id,
                    "task_sha256": task_digest,
                    "instruction": "",
                },
                max_actions=args.max_actions, wall_time_seconds=args.wall_time,
            )
            return {
                "status": "REAL_OSWORLD_VM_EVALUATION",
                "task_id": result.task_id,
                "actions_attempted": result.actions_attempted,
                "all_actions_gateway_approved": result.all_actions_gateway_approved,
                "score": result.score,
                "official_task_evaluated": result.score is not None,
                "isolation_verified_at_start": True,
                "physical_hardware_verified": False,
                "leaderboard_verified": False,
            }
    finally:
        await asyncio.to_thread(bridge.close)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AURA guarded OSWorld V2.1 Python 3.12 VM")
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--task-id", help="Official v2.1 class id, e.g. 001")
    parser.add_argument("--approved-task-sha256", help="Independently reviewed task file hash")
    parser.add_argument("--website-suffix")
    parser.add_argument("--owner-db", type=Path)
    parser.add_argument("--trusted-public-keys", type=Path)
    parser.add_argument("--receipt", type=Path, help="Fresh external signed network receipt")
    parser.add_argument("--attestation-wait", type=int, default=240)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--max-actions", type=int, default=8)
    parser.add_argument("--wall-time", type=int, default=120)
    parser.add_argument("--boot-timeout", type=int, default=900)
    parser.add_argument("--smoke", action="store_true",
                        help="KVM=N, boot only; no model, task, owner or receipt")
    parser.add_argument("--allow-real-vm", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (ValueError, TypeError, PermissionError, OSError,
            subprocess.SubprocessError, TimeoutError, RuntimeError) as exc:
        print(json.dumps({
            "status": "LIVE_VM_BLOCKED",
            "benchmark_score": None, "hardware_verified": False,
            "error_type": type(exc).__name__, "reason": str(exc)[:500],
        }, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
