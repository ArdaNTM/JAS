"""Windows autonomous MCP live-recovery security regressions.

No network access, installers, untrusted code execution, or Owner identity
provisioning is required for these static/inert acceptance checks.
"""
from __future__ import annotations

import io
from pathlib import Path
import zipfile

import pytest

from aura_core.evolution.external_staging import _validated_files, StagingRejected
from aura_core.evolution.sandbox_preflight import choose_python_entrypoint
from aura_core.evolution.windows_job_mcp import static_python_entry


def _zip(files: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr("repo-main/" + name, payload)
    return data.getvalue()


def _candidate(extra: dict[str, bytes]) -> bytes:
    return _zip({
        "README.md": b"Fully local MCP server without API keys.",
        "server.py": b"from mcp.server.mcpserver import MCPServer\nmcp = MCPServer('test')\n",
        **extra,
    })


@pytest.mark.parametrize("suffix", [".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"])
def test_inert_helpers_are_skipped_not_rejected(suffix):
    summary: dict = {}
    reviewed, _, binary_skips = _validated_files(
        _candidate({"scripts/setup" + suffix: b"echo harmless helper"}),
        summary=summary,
    )
    assert "scripts/setup" + suffix not in reviewed
    assert "server.py" in reviewed
    assert summary["skipped_non_source"] == 1
    assert binary_skips == 0


@pytest.mark.parametrize("suffix", [
    ".exe", ".dll", ".so", ".dylib", ".sys", ".scr", ".com",
    ".msi", ".vbs", ".jar", ".apk", ".deb", ".rpm",
])
def test_dangerous_binaries_still_rejected_even_when_ignored(suffix):
    with pytest.raises(StagingRejected, match="Executable or suspicious"):
        _validated_files(_candidate({"docs/binary" + suffix: b"x" * 100}))


@pytest.mark.parametrize("entry", [
    "src/memory_mcp/__main__.py",
    "src/memory_mcp/server.py",
    "src/memory_mcp/main.py",
])
def test_src_layout_is_detected_without_executing(entry):
    files = {
        entry: (b"from mcp.server.mcpserver import MCPServer\n"
                b"mcp = MCPServer('local')\n"
                b"@mcp.tool()\n"
                b"def remember() -> str: return 'ok'\n"),
    }
    assert choose_python_entrypoint(files, "pyproject.toml") == entry
    assert static_python_entry(files, "pyproject.toml") == entry


def test_pep621_project_script_resolves_into_src_layout():
    files = {
        "pyproject.toml": (
            b"[project]\nname = 'local-memory'\n"
            b"[project.scripts]\n"
            b"memory-mcp = 'memory_mcp.runner:main'\n"),
        "src/memory_mcp/runner.py": (
            b"from mcp.server.mcpserver import MCPServer\n"
            b"mcp = MCPServer('memory')\n"
            b"@mcp.tool()\n"
            b"def remember() -> str: return 'ok'\n"
            b"def main(): mcp.run(transport='stdio')\n"),
    }
    assert choose_python_entrypoint(files, "pyproject.toml") == "src/memory_mcp/runner.py"
    assert static_python_entry(files, "pyproject.toml") == "src/memory_mcp/runner.py"


def test_package_main_wrapper_must_import_an_ast_verified_sibling():
    files = {
        "src/memory_mcp/__main__.py": (
            b"from .server import main\n"
            b"if __name__ == '__main__': main()\n"
        ),
        "src/memory_mcp/server.py": (
            b"from mcp.server.mcpserver import MCPServer\n"
            b"mcp = MCPServer('local')\n"
            b"@mcp.tool()\n"
            b"def recall() -> str: return 'ok'\n"
            b"def main(): mcp.run(transport='stdio')\n"
        ),
    }
    assert choose_python_entrypoint(files, "src/memory_mcp/__main__.py") == "src/memory_mcp/__main__.py"
    assert static_python_entry(files, "src/memory_mcp/__main__.py") == "src/memory_mcp/__main__.py"
    files["src/memory_mcp/server.py"] = b"def main(): pass\n"
    with pytest.raises(Exception):
        static_python_entry(files, "src/memory_mcp/__main__.py")


def test_wheel_install_requires_validated_owner_permission_and_can_be_disabled(tmp_path):
    from aura_core.evolution.isolated_venv import (
        declared_dependencies, prepare_isolated_venv,
    )
    files = {
        "pyproject.toml": (
            b"[project]\nname='safe-local'\nrequires-python='>=3.12'\n"
            b"dependencies=['mcp>=2.0','httpx>=0.27']\n"
        ),
    }
    dependencies = declared_dependencies(files)
    assert any(s.startswith("mcp") for s in dependencies)
    assert any(s.startswith("httpx") for s in dependencies)
    runtime = tmp_path / "runtime" / "vendor__package"
    runtime.mkdir(parents=True)
    with pytest.raises(Exception, match="disabled"):
        prepare_isolated_venv(runtime, files, tmp_path, install=False)
    assert not (runtime / ".venv").exists()


@pytest.mark.parametrize("malicious", [
    "-r other.txt", "-e .", "https://evil.example/wheel",
    "git+https://github.com/example/package", "local/relative",
])
def test_untrusted_dependency_install_directives_denied(malicious):
    from aura_core.evolution.isolated_venv import declared_dependencies
    with pytest.raises(Exception):
        declared_dependencies({"requirements.txt": malicious.encode()})


def test_isolated_src_python_is_started_as_module_for_relative_imports(tmp_path):
    from aura_core.evolution.windows_job_mcp import _isolated_entry_args
    python = tmp_path / "runtime" / "pkg" / ".venv" / "Scripts" / "python.exe"
    runtime = tmp_path / "runtime" / "pkg"
    assert _isolated_entry_args(
        runtime, "src/memory_mcp/__main__.py", python
    )[-2:] == ["-m", "memory_mcp"]
    assert _isolated_entry_args(
        runtime, "src/memory_mcp/server.py", python
    )[-2:] == ["-m", "memory_mcp.server"]
    assert _isolated_entry_args(
        runtime, "server.py", python
    )[-1] == str(runtime / "server.py")
    with pytest.raises(Exception):
        _isolated_entry_args(runtime, "../unsafe.py", python)


def test_malicious_project_script_is_not_an_arbitrary_shell_command():
    files = {
        "pyproject.toml": b"[project.scripts]\nmemory = 'os.system:run'\n",
        "src/memory_mcp/runner.py": b"print('not MCP')\n",
    }
    with pytest.raises(Exception):
        choose_python_entrypoint(files, "pyproject.toml")


def test_staging_old_script_false_positive_retried_only_once_through_gateway(tmp_path):
    import asyncio
    import sqlite3
    from types import SimpleNamespace
    from aura_core.evolution.self_discovery import SelfDiscoveryEngine
    from aura_core.evolution.external_staging import EvolutionWorkspace
    from aura_core.kernel.permissions import AuthorizationDecision

    class DeniedGateway:
        calls = 0
        async def invoke(self, request):
            self.calls += 1
            return SimpleNamespace(decision=AuthorizationDecision.DENY, result=None)

    workspace = EvolutionWorkspace(tmp_path / "evolution")
    gateway = DeniedGateway()
    engine = SelfDiscoveryEngine(
        gateway=gateway, db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id, repository, url, description, license, capability_hint, "
            " status, created_at, stars, size_kb, package_status, package_error, "
            " stage_attempts, stage_retry_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy-false-positive", "sample/local-memory",
             "https://github.com/sample/local-memory", "local memory mcp",
             "MIT", "MCP server", "pending_owner_review", 1.0, 30, 100,
             "STAGING_REJECTED", "Executable or suspicious archive content rejected",
             1, 1),
        )
    first = asyncio.run(engine._stage_pending())
    assert first["attempted"] == 1
    assert gateway.calls == 1
    second = asyncio.run(engine._stage_pending())
    assert second["attempted"] == 0
    assert gateway.calls == 1


def test_malformed_project_metadata_rejected_without_dynamic_loading(tmp_path):
    from aura_core.evolution.isolated_venv import declared_dependencies
    files = {"pyproject.toml": b"project = 'untrusted scalar'\\n"}
    with pytest.raises(Exception):
        declared_dependencies(files)
    with pytest.raises(Exception):
        choose_python_entrypoint(files, "pyproject.toml")


def test_install_failure_diagnostics_are_redacted_and_bounded(tmp_path):
    import json
    from aura_core.evolution.isolated_venv import _record_safe_install_failure
    workspace = tmp_path / "evolution"
    (workspace / "logs").mkdir(parents=True)
    runtime = workspace / "runtime" / "vendor__memory"
    runtime.mkdir(parents=True)
    _record_safe_install_failure(
        workspace, runtime,
        "TOKEN=secret_should_not_be_logged\\nNo matching distribution found for secret.pkg",
    )
    record = json.loads(
        (workspace / "logs" / "vendor__memory-local-mcp-stderr.json").read_text("utf-8")
    )
    assert record["stderr_tail"] == "No compatible wheel on package index"
    assert "secret_should_not_be_logged" not in json.dumps(record)


def test_launcher_restores_only_missing_user_environment():
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "launch-aura-desktop.ps1").read_text("utf-8")
    for name in (
        "AURA_STORAGE_MODE", "AURA_EVOLUTION_ROOT",
        "AURA_EVOLUTION_AUTO_ACTIVATE", "AURA_EVOLUTION_DELEGATION_KEY_SHA256",
        "AURA_EVOLUTION_ATTESTOR_KEY_SHA256",
    ):
        assert f'"{name}"' in text
    assert 'GetEnvironmentVariable($name, "User")' in text
    assert 'GetEnvironmentVariable($name, "Process")' in text
    assert "Start-Attestor" in text
    assert "autonomous_delegation.json" not in text


def test_setup_clears_clipboard_in_windows_powershell_51():
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "setup-autonomous-aura.ps1").read_text("utf-8")
    assert 'cmd.exe /c "echo off | clip" | Out-Null' in text
    assert "Set-Clipboard -Value ''" not in text
