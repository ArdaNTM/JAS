"""Read-only B2 post-merge regression and *preflight*, never hardware attestation.

Run on the Owner's actual Windows host AFTER explicitly merging the approved
PRs and pulling main. The script cannot enroll Owner identity, sign evidence,
modify firewall/ACL/Hyper-V, start a VM, access Docker socket through transport,
or claim any of the 71 B2-Env capabilities have passed live acceptance.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TEST_PATH = re.compile(r"(?:core/)?tests/[A-Za-z0-9_./-]+\.py")


def load_b2(repo: Path) -> tuple[dict, dict]:
    tracker = json.loads((repo / "docs/22_IMPLEMENTATION/AURA_FEATURE_TRACKER.json").read_text("utf-8"))
    catalog = json.loads((repo / "docs/22_IMPLEMENTATION/AURA_ACCEPTANCE_GROUPS.json").read_text("utf-8"))
    b2 = set(catalog["B2_ids"])
    owner = set(catalog["B2_owner_ids"])
    env = set(catalog["B2_env_ids"])
    if len(b2) != 88 or owner & env or owner | env != b2:
        raise ValueError("incomplete or overlapping B2 Owner/Env partition")
    if any(
        tracker["features"][i - 1]["status"] != "COMPLETED"
        or catalog["records"][i - 1].get("b2_acceptance_track") != "B2-Owner"
        or catalog["records"][i - 1]["ready_for_completion"] is not True
        for i in owner
    ):
        raise ValueError("B2-Owner bounded v1 completion records inconsistent")
    if any(
        tracker["features"][i - 1]["status"] != "TESTING"
        or catalog["records"][i - 1].get("b2_acceptance_track") != "B2-Env"
        or catalog["records"][i - 1]["ready_for_completion"] is not False
        for i in env
    ):
        raise ValueError("B2-Env records are not fail-closed")
    return tracker, catalog


def focused_tests(repo: Path, tracker: dict, catalog: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Discover present focus tests AND retain missing identities as blockers."""
    selected: set[str] = set()
    missing: set[str] = set()
    for i in catalog["B2_env_ids"]:
        row = tracker["features"][i - 1]
        if not row["test_commands"]:
            raise ValueError(f"B2 feature #{i} lacks focused regression tests")
        first = row["test_commands"][0]
        if not first.startswith("cd core && ") or not first.endswith(".py"):
            raise ValueError(f"B2 feature #{i} has unsupported test command")
        paths = _TEST_PATH.findall(first)
        if not paths:
            raise ValueError(f"B2 feature #{i} has no focused pytest paths")
        for item in paths:
            normalized = item.removeprefix("core/")
            actual = (repo / "core" / normalized).resolve()
            tests_dir = (repo / "core/tests").resolve()
            if not actual.is_relative_to(tests_dir):
                raise ValueError(f"B2 feature #{i} points outside test tree: {item}")
            if not actual.is_file():
                missing.add(normalized)
                continue
            selected.add(normalized)
    return tuple(sorted(selected)), tuple(sorted(missing))


def run_check(title: str, cmd: list[str], *, cwd: Path) -> bool:
    print(f"CHECK {title}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, check=False, timeout=600)
    print(f"{title}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
    return result.returncode == 0


def preflight(*, ubuntu_host: str | None, ubuntu_port: int, vm_name: str) -> bool:
    if platform.system() != "Windows":
        print("B2-Env: INCONCLUSIVE (live Windows host required)")
        return False
    ok = True
    if not shutil.which("docker"):
        print("B2-Env Docker: INCONCLUSIVE (Docker CLI unavailable)")
        ok = False
    elif not run_check(
        "Docker Engine availability",
        ["docker", "info", "--format", "{{.OSType}}"],
        cwd=ROOT,
    ):
        ok = False
    if not shutil.which("powershell.exe"):
        print("B2-Env Hyper-V: INCONCLUSIVE (PowerShell unavailable)")
        ok = False
    else:
        # Read-only: inspect existing VM; never start or reconfigure it.
        safe_vm = vm_name.replace("'", "''")
        if not run_check(
            "Existing running Hyper-V Ubuntu VM",
            ["powershell.exe", "-NoProfile", "-Command",
             f"$vm = Get-VM -Name '{safe_vm}' -ErrorAction Stop; if ($vm.State -ne 'Running') {{ exit 2 }}"],
            cwd=ROOT,
        ):
            ok = False
    if ubuntu_host is None:
        print("B2-Env Ubuntu: INCONCLUSIVE (--ubuntu-host not provided)")
        ok = False
    else:
        try:
            with socket.create_connection((ubuntu_host, ubuntu_port), timeout=5):
                print("B2-Env Ubuntu TCP: reachable; identity/broker authorization NOT verified")
        except OSError as exc:
            print(f"B2-Env Ubuntu TCP: INCONCLUSIVE ({type(exc).__name__})")
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B2 post-merge focused tests and read-only host preflight")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--ubuntu-host", help="Ubuntu VM SSH TCP address, not a credential")
    parser.add_argument("--ubuntu-port", type=int, default=22)
    parser.add_argument("--vm-name", default="AURA-Broker-Lab")
    parser.add_argument("--hardware-evidence", type=Path)
    parser.add_argument("--trusted-public-keys", type=Path)
    parser.add_argument("--list-only", action="store_true",
                        help="Offline test discovery only; no live probes or tests")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    if not 1 <= args.ubuntu_port <= 65535:
        parser.error("invalid Ubuntu port")
    try:
        tracker, catalog = load_b2(repo)
        paths, missing_tests = focused_tests(repo, tracker, catalog)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"B2 CHECKLIST ERROR: {exc}")
        return 2
    print(f"B2-Owner={len(catalog['B2_owner_ids'])} B2-Env={len(catalog['B2_env_ids'])}; "
          f"71 TESTING (B2-Env only); {len(paths)} present and {len(missing_tests)} MISSING unique focused test files")
    if missing_tests:
        print("B2 regression acceptance BLOCKED: " + ", ".join(missing_tests))
    if args.list_only:
        print("AVAILABLE PYTEST: " + " ".join(paths))
        print("B2 hardware/Owner evidence NOT evaluated")
        return 0
    if not run_check("On merged main", ["git", "branch", "--show-current"], cwd=repo):
        return 2
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            check=False, capture_output=True, text=True)
    if branch.returncode or branch.stdout.strip() != "main":
        print("BLOCKED: run only after approved PR merge and checkout of main")
        return 2
    checks = [
        ("Feature completion/authoritative source pins",
         [sys.executable, str(repo / "scripts/audit_aura_117_completion.py")]),
        ("Tracker contract",
         [sys.executable, str(repo / "scripts/validate_aura_feature_tracker.py")]),
        ("440 source release lock",
         [sys.executable, str(repo / "core/scripts/verify_final_lock.py")]),
        ("B2 scoped positive/negative regression tests",
         [sys.executable, "-m", "pytest", "-q", "--tb=short", *paths]),
    ]
    all_pass = all(run_check(name, cmd, cwd=repo / "core") for name, cmd in checks)
    if missing_tests:
        all_pass = False
    environment_ok = preflight(
        ubuntu_host=args.ubuntu_host, ubuntu_port=args.ubuntu_port,
        vm_name=args.vm_name)
    if args.hardware_evidence is not None or args.trusted_public_keys is not None:
        if args.hardware_evidence is None or args.trusted_public_keys is None:
            print("Physical hardware evidence: INCONCLUSIVE (evidence and keys both required)")
            environment_ok = False
        else:
            environment_ok = run_check(
                "External Ed25519 physical hardware receipt verification",
                [sys.executable, str(repo / "core/scripts/verify_physical_hardware.py"),
                 "--evidence", str(args.hardware_evidence.resolve()),
                 "--trusted-public-keys", str(args.trusted_public_keys.resolve())],
                cwd=repo / "core",
            ) and environment_ok
    else:
        print("Physical hardware receipts: NOT VERIFIED (no signed evidence provided)")
        environment_ok = False
    print("B2-Owner bounded offline v1: 17 COMPLETED; live production acceptance not inferred")
    print("All 71 B2-Env remain TESTING; a green preflight is NEVER live acceptance.")
    return 0 if all_pass and environment_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
