"""Production dependency scope must not silently expand under the npm audit exception."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "aura-ui" / "package-lock.json"
WORKFLOW = ROOT / ".github" / "workflows" / "aura-windows-launcher.yml"


def test_picomatch_is_build_only_in_locked_desktop_tree() -> None:
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    packages = data["packages"]
    scoped = [
        (path, pkg)
        for path, pkg in packages.items()
        if path.endswith("/picomatch") or path == "node_modules/picomatch"
    ]
    assert scoped, "expected lockfile evidence for picomatch"
    assert all(pkg.get("dev") is True for _, pkg in scoped), (
        "picomatch entered a production dependency path; block the release"
    )
    assert "picomatch" not in packages[""].get("dependencies", {})


def test_windows_ci_audits_runtime_and_reports_dev_risks() -> None:
    contents = WORKFLOW.read_text(encoding="utf-8")
    assert "npm ls picomatch --all" in contents
    assert "npm audit --omit=dev --audit-level=high" in contents
    assert "npm audit --audit-level=high" in contents
    assert "continue-on-error: true" in contents
