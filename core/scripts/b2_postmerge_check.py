"""Read-only B2 post-merge regression and *preflight*, never hardware attestation.

Run on the Owner's actual Windows host AFTER explicitly merging the approved
PRs and pulling main. The script cannot enroll Owner identity, sign evidence,
modify firewall/ACL/Hyper-V, start a VM, access Docker socket through transport,
or claim any of the 71 B2-Env capabilities passed live physical acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from datetime import datetime, timezone
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V1_SOFTWARE = frozenset({3, 4, 15, 29, 30, 48, 56, 63, 103, 105, 107, 115})
V1_SIMULATION = frozenset({81, 85, 86, 87, 88, 89, 90})
V1_FINAL_WINDOWS = frozenset({1, 6, 7, 9, 11, 13, 14, 16, 17, 18, 19, 20, 22, 23, 24, 26, 28, 31, 32, 49, 54, 55, 57, 69, 77, 78, 79, 80, 82, 83, 84, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 104, 106, 113, 116})
V1_FINAL_HYPERV = frozenset({25, 27, 33, 45, 51, 60, 101})
V1_ACCEPTED = V1_SOFTWARE | V1_SIMULATION | V1_FINAL_WINDOWS | V1_FINAL_HYPERV
_TEST_PATH = re.compile(r"(?:core/)?tests/[A-Za-z0-9_./-]+\.py")


def _inside_tree(candidate: Path, tree_root: Path) -> bool:
    """Check resolved path membership across Windows casing and drive changes.

    A path on a different volume (e.g. TEMP on C: and JAS on D:) is
    outside, not an error; a sibling with a common textual prefix is
    NOT inside. No paths inside the checkout are exempted.
    """
    child = candidate.resolve()
    root = tree_root.resolve()
    try:
        common = os.path.commonpath((str(child), str(root)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(str(root))


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
    acceptance = catalog.get("B2_env_acceptance")
    if (type(acceptance) is not dict
            or acceptance.get("software_ids") != sorted(V1_SOFTWARE)
            or acceptance.get("simulation_ids") != sorted(V1_SIMULATION)
            or acceptance.get("remaining_ids") != sorted(env - V1_ACCEPTED)
            or acceptance.get("windows_local_v1_ids") != sorted(V1_FINAL_WINDOWS)
            or acceptance.get("hyperv_docker_v1_ids") != sorted(V1_FINAL_HYPERV)
            or V1_ACCEPTED != env
            or "NO_PHYSICAL_CERTIFICATION" not in acceptance.get("simulation_policy", "")):
        raise ValueError("B2-Env v1 acceptance cohort must remain pinned")
    if any(
        tracker["features"][i - 1]["status"]
        != ("COMPLETED" if i in V1_ACCEPTED else "TESTING")
        or catalog["records"][i - 1].get("b2_acceptance_track") != "B2-Env"
        or catalog["records"][i - 1]["ready_for_completion"] is not (i in V1_ACCEPTED)
        for i in env
    ):
        raise ValueError("B2-Env accepted-v1 / pending status inconsistency")
    validation_groups = catalog.get("B2_env_validation_groups")
    if (type(validation_groups) is not dict or
            set(validation_groups) != {"windows_local", "hyperv_docker", "external_hardware_simulation"}
            or any(type(items) is not list or items != sorted(set(items)) for items in validation_groups.values())
            or sorted(sum((items for items in validation_groups.values()), []))
                != catalog["B2_env_ids"]):
        raise ValueError("B2-Env validation groups must partition 71 governed IDs")
    return tracker, catalog


def pending_env_ids(tracker: dict, catalog: dict) -> list[int]:
    """Return only unaccepted B2-Env features, never simulation as physical."""
    return [i for i in catalog["B2_env_ids"]
            if tracker["features"][i - 1]["status"] == "TESTING"]


def focused_tests(repo: Path, tracker: dict, catalog: dict, *, target_ids: list[int] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Discover present focus tests AND retain missing identities as blockers."""
    selected: set[str] = set()
    missing: set[str] = set()
    # Preserve access to all 64 pinned regression suites even after bounded-v1
    # completion; a green test can never claim hardware/production acceptance.
    selected_ids = catalog["B2_env_ids"] if target_ids is None else target_ids
    if target_ids is not None and not set(target_ids).issubset(catalog["B2_env_ids"]):
        raise ValueError("B2-Env target IDs out of bounds")
    for i in selected_ids:
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
            if not _inside_tree(actual, tests_dir):
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



def run_pytest_evidence(
    *, repo: Path, paths: tuple[str, ...], group: str, feature_ids: list[int],
    output: Path, baseline_ok: bool, head: str,
) -> bool:
    """Execute real scoped pytest; emit UNSIGNED software-only evidence.

    This report is never an Owner credential, physical witness, production
    acceptance or permission to dispatch tools through MCP Gateway.
    """
    repo = repo.resolve()
    destination = output.resolve()
    if _inside_tree(destination, repo) or not destination.parent.is_dir():
        raise ValueError("Evidence output must be outside the checkout")
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise ValueError("Evidence requires an exact checked-out Git HEAD")
    started = datetime.now(timezone.utc).isoformat()
    code, summary = 2, "No pending tests for selected group"
    if paths:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", *paths],
                cwd=repo / "core", capture_output=True, text=True,
                timeout=600, check=False,
            )
            code = result.returncode
            # Do not store or echo unredacted pytest output.
            output_lines = (result.stdout or "").splitlines()
            summaries = [line.strip()[:240] for line in output_lines
                         if re.search(r"\b\d+ (?:passed|failed|skipped|error)\b", line)]
            summary = summaries[-1] if summaries else "pytest returned no summary"
        except subprocess.TimeoutExpired:
            code, summary = 124, "pytest exceeded 600 seconds"
    hashes: list[dict[str, str]] = []
    for name in paths:
        path = (repo / "core" / name).resolve()
        if not _inside_tree(path, repo / "core/tests") or not path.is_file():
            raise ValueError("Selected pytest source is no longer under core/tests")
        hashes.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    success = bool(paths and baseline_ok and code == 0)
    record = {
        "schema": "aura.b2-env-pytest-evidence.v1",
        "git_head": head,
        "group": group,
        "feature_ids": feature_ids,
        "focused_test_files": hashes,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": code,
        "pytest_summary": summary,
        "source_and_governance_checks_pass": bool(baseline_ok),
        "result": "PASS_SOFTWARE_REGRESSION_ONLY" if success else "BLOCKED",
        "is_signed": False,
        "hardware_verified": False,
        "owner_authorization_granted": False,
        "production_acceptance": False,
    }
    encoded = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".aura-b2-pytest-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"B2 pytest evidence: {record['result']} ({summary})")
    print(f"Unsigned test report: {destination}")
    return success


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
    parser.add_argument("--group", choices=(
        "all", "windows_local", "hyperv_docker", "external_hardware_simulation"
    ), default="all", help="Scope focused test selection; no release approval inferred")
    parser.add_argument("--run-pytest", action="store_true",
                        help="Create an unsigned JSON report from actual focused pytest execution")
    parser.add_argument("--evidence-out", type=Path,
                        help="External JSON test evidence path (not hardware attestation)")
    parser.add_argument("--tests-only", action="store_true",
                        help="Run scoped regressions/source validation; no hardware or Owner proof")
    parser.add_argument("--list-only", action="store_true",
                        help="Offline test discovery only; no live probes or tests")
    args = parser.parse_args(argv)
    if args.run_pytest != (args.evidence_out is not None):
        parser.error("--run-pytest requires --evidence-out and vice versa")
    if args.run_pytest and not args.tests_only:
        parser.error("--run-pytest requires --tests-only")
    if args.list_only and args.tests_only:
        parser.error("--list-only and --tests-only are mutually exclusive")
    if args.group != "all" and not (args.list_only or args.tests_only):
        parser.error("Scoped --group must be combined with --list-only or --tests-only")
    repo = args.repo_root.resolve()
    if not 1 <= args.ubuntu_port <= 65535:
        parser.error("invalid Ubuntu port")
    try:
        tracker, catalog = load_b2(repo)
        target_ids = None if args.group == "all" else catalog["B2_env_validation_groups"][args.group]
        paths, missing_tests = focused_tests(repo, tracker, catalog, target_ids=target_ids)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"B2 CHECKLIST ERROR: {exc}")
        return 2
    pending_ids = pending_env_ids(tracker, catalog)
    selected_ids = catalog["B2_env_ids"] if args.group == "all" else (
        catalog["B2_env_validation_groups"][args.group]
    )
    print(f"B2-Owner={len(catalog['B2_owner_ids'])} B2-Env={len(catalog['B2_env_ids'])}; "
          f"{len(pending_ids)} TESTING (B2-Env only); {len(paths)} present and {len(missing_tests)} MISSING unique focused test files")
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
        ("441 source release lock",
         [sys.executable, str(repo / "core/scripts/verify_final_lock.py")]),
    ]
    baseline_ok = all(run_check(name, cmd, cwd=repo / "core") for name, cmd in checks)
    if missing_tests:
        baseline_ok = False
    if args.run_pytest:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                              capture_output=True, text=True, timeout=15, check=False)
        try:
            all_pass = run_pytest_evidence(
                repo=repo, paths=paths, group=args.group,
                feature_ids=selected_ids, output=args.evidence_out,
                baseline_ok=baseline_ok,
                head=head.stdout.strip() if head.returncode == 0 else "",
            )
        except (OSError, ValueError, TypeError) as exc:
            print(f"B2 unsigned evidence BLOCKED: {type(exc).__name__}: {exc}")
            return 2
    else:
        all_pass = baseline_ok and bool(paths) and run_check(
            "B2 scoped positive/negative regression tests",
            [sys.executable, "-m", "pytest", "-q", "--tb=short", *paths],
            cwd=repo / "core",
        )
    if args.tests_only:
        print("Software regression only: physical/Owner acceptance NOT VERIFIED")
        return 0 if all_pass else 2
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
    print(f"Remaining {len(pending_ids)} B2-Env are TESTING; bounded v1 is not live production or physical acceptance.")
    return 0 if all_pass and environment_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
