"""Production dependency scope must not silently expand under the npm audit exception."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "aura-ui" / "package-lock.json"
WORKFLOW = ROOT / ".github" / "workflows" / "aura-windows-launcher.yml"


def test_picomatch_is_build_only_in_locked_desktop_tree() -> None:
    for lock in (LOCK, ROOT / "core" / "frontend" / "package-lock.json"):
        data = json.loads(lock.read_text(encoding="utf-8"))
        packages = data["packages"]
        scoped = [
            (path, pkg)
            for path, pkg in packages.items()
            if path.endswith("/picomatch") or path == "node_modules/picomatch"
        ]
        assert scoped, f"expected lockfile evidence for picomatch in {lock}"
        assert all(pkg.get("dev") is True for _, pkg in scoped), (
            f"picomatch entered a production dependency path in {lock}"
        )
        assert "picomatch" not in packages[""].get("dependencies", {})


def test_windows_ci_audits_runtime_and_reports_dev_risks() -> None:
    contents = WORKFLOW.read_text(encoding="utf-8")
    assert "npm ls picomatch --all" in contents
    assert "npm audit --omit=dev --audit-level=high" in contents
    assert "npm audit --audit-level=high" in contents
    assert "continue-on-error: true" in contents
    assert contents.count("npm ls picomatch --all") == 2
    assert contents.count("npm audit --omit=dev --audit-level=high") == 2
    assert contents.count("npm audit --audit-level=high") == 2


def test_security_workflows_preserve_production_audit_and_report_dev_advisories() -> None:
    paths = [
        ROOT / ".github/workflows/aura-secure-evolution.yml",
        ROOT / ".github/workflows/aura-physical-trust-acceptance.yml",
    ]
    expected = [1, 2]
    for path, n in zip(paths, expected, strict=True):
        text = path.read_text(encoding="utf-8")
        assert text.count("npm ls picomatch --all") == n
        assert text.count("npm audit --omit=dev --audit-level=high") == n
        assert text.count("npm audit --audit-level=high") == n
        assert text.count("continue-on-error: true") >= n
