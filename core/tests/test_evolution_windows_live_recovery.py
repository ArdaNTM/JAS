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


def test_mcp_sdk_follows_installed_version_when_no_other_sdk_declared(monkeypatch):
    from aura_core.evolution import isolated_venv
    monkeypatch.setattr(isolated_venv.metadata, "version", lambda name: (
        "1.26.4" if name == "mcp" else (_ for _ in ()).throw(LookupError(name))
    ))
    requirements = isolated_venv.declared_dependencies({
        "requirements.txt": b"httpx>=0.27\n",
    })
    assert "mcp==1.26.4" in requirements
    assert "mcp==2.0.0" not in requirements


def test_mcp_sdk_fallback_when_core_metadata_missing(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from aura_core.evolution import isolated_venv

    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(isolated_venv.metadata, "version", missing)
    requirements = isolated_venv.declared_dependencies({
        "requirements.txt": b"httpx>=0.27\n",
    })
    assert "mcp>=1.0.0,<2.0.0" in requirements


def test_explicit_mcp_or_fastmcp_constraints_are_not_overridden(monkeypatch):
    from aura_core.evolution import isolated_venv
    # The AURA host pins MCP 2.0.0, but a real FastMCP server must be
    # allowed to resolve its own SDK transitive constraints in its .venv.
    monkeypatch.setattr(isolated_venv.metadata, "version", lambda name: "2.0.0")
    fastmcp_deps = isolated_venv.declared_dependencies({
        "requirements.txt": b"fastmcp>=0.1.0\nJinja2>=3.0\n",
    })
    assert "mcp==2.0.0" not in fastmcp_deps
    assert any(dep.lower().startswith("fastmcp") for dep in fastmcp_deps)

    explicit_mcp = isolated_venv.declared_dependencies({
        "pyproject.toml": b"[project]\nname='memory'\ndependencies=['mcp>=1.0,<3']\n",
    })
    assert any(
        dep.startswith("mcp") and ">=1.0" in dep and "<3" in dep
        for dep in explicit_mcp
    )
    assert "mcp==2.0.0" not in explicit_mcp


def test_large_python_mcp_package_ast_up_to_250_modules_is_bounded():
    # A deliberately large but inert Python FastMCP package. No import/run.
    files = {
        "src/big_mcp/__main__.py": b"from .server import main\n",
        "src/big_mcp/server.py": (
            b"from mcp.server.mcpserver import MCPServer\n"
            b"mcp = MCPServer('test')\n"
            b"@mcp.tool()\ndef ping(): return 'ok'\n"
        ),
    }
    for n in range(248):
        files[f"src/big_mcp/tools/tool_{n:03}.py"] = b"def helper(): return None\n"
    assert len(files) == 250
    assert static_python_entry(files, "src/big_mcp/__main__.py") == (
        "src/big_mcp/__main__.py"
    )
    files["src/big_mcp/tools/tool_248.py"] = b"def too_many(): pass\n"
    with pytest.raises(Exception, match="module count exceeded"):
        static_python_entry(files, "src/big_mcp/__main__.py")


def test_recovery_v3_retries_v2_uv_flags_failure_once_but_never_replays():
    from aura_core.evolution.attestor_worker import (
        RECOVERY_EPOCH, _eligible_local_recovery,
    )

    assert RECOVERY_EPOCH == "windows-isolated-wheels-20261122-v3"
    v2 = {
        "status": "QUARANTINED", "reason_code": "SandboxUntrusted",
        "retry_count": 2, "recovery_epoch": "windows-isolated-wheels-20261122-v2",
    }
    assert _eligible_local_recovery(v2) is True
    assert _eligible_local_recovery({**v2, "recovery_epoch": RECOVERY_EPOCH}) is False
    assert _eligible_local_recovery({**v2, "retry_count": 3}) is False
    assert _eligible_local_recovery({**v2, "status": "REVOKED"}) is False
    assert _eligible_local_recovery({**v2, "reason_code": "PermissionError"}) is False
    assert _eligible_local_recovery({**v2, "retry_count": True}) is False
    # Machines jumping directly from v1 still get a bounded upgrade retry.
    assert _eligible_local_recovery({
        **v2, "recovery_epoch": "windows-isolated-wheels-20261122-v1",
        "retry_count": 1,
    }) is True


def test_local_recovery_does_not_scan_or_install_without_signed_owner():
    import asyncio
    from types import SimpleNamespace
    from aura_core.evolution.attestor_worker import IndependentMCPAttestorWorker

    worker = object.__new__(IndependentMCPAttestorWorker)
    worker._delegation = SimpleNamespace(verified_grant=lambda: None)
    worker._decisions = SimpleNamespace(
        evaluate_pending=lambda **_: (_ for _ in ()).throw(
            AssertionError("unsigned Owner must not evaluate pending candidates")
        ),
    )
    assert asyncio.run(worker.scan()) == []


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
    files = {"pyproject.toml": b"project = 'untrusted scalar'\n"}
    with pytest.raises(Exception):
        declared_dependencies(files)
    with pytest.raises(Exception):
        choose_python_entrypoint(files, "pyproject.toml")


def test_uv_0100_uses_wheel_only_without_conflicting_no_build(monkeypatch, tmp_path):
    """Spy on argv without launching uv, installing wheels or importing candidate code."""
    import os
    from types import SimpleNamespace
    from aura_core.evolution import isolated_venv

    workspace = tmp_path / "external"
    runtime = workspace / "runtime" / "vendor__local"
    runtime.mkdir(parents=True)
    commands = []
    monkeypatch.setattr(isolated_venv.shutil, "which", lambda name: "uv")

    def fake_run(command, **kwargs):
        commands.append(command)
        assert kwargs["cwd"] == runtime
        assert kwargs["check"] is False
        assert kwargs["timeout"] == isolated_venv._MAX_INSTALL_SECONDS
        if command[1] == "venv":
            python = runtime / ".venv" / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )
            python.parent.mkdir(parents=True)
            python.write_bytes(b"test stub, never executed")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(isolated_venv.subprocess, "run", fake_run)
    result = isolated_venv.prepare_isolated_venv(
        runtime, {"requirements.txt": b"fastmcp>=0.1.0\n"},
        workspace, install=True,
    )
    assert result is not None
    assert len(commands) == 2
    assert commands[0][1] == "venv"
    install = commands[1]
    assert install[1:3] == ["pip", "install"]
    assert install.count("--only-binary") == 1
    assert install[install.index("--only-binary") + 1] == ":all:"
    assert "--no-build" not in install
    assert "--no-build-isolation" not in install
    assert "--python" in install
    assert (runtime / ".aura-isolated-env.json").is_file()


def test_uv_conflicting_flags_diagnostic_is_safe_and_bounded(tmp_path):
    import json
    from aura_core.evolution.isolated_venv import _record_safe_install_failure

    workspace = tmp_path / "external"
    (workspace / "logs").mkdir(parents=True)
    runtime = workspace / "runtime" / "vendor__memory"
    runtime.mkdir(parents=True)
    _record_safe_install_failure(
        workspace, runtime,
        "TOKEN=top-secret\nerror: the argument '--no-build' cannot be used with "
        "'--only-binary <ONLY_BINARY>'",
    )
    receipt = json.loads(
        (workspace / "logs" / "vendor__memory-local-mcp-stderr.json").read_text("utf-8")
    )
    assert receipt["reason_code"] == "ISOLATED_DEPENDENCY_INSTALL_FAILED"
    assert receipt["stderr_tail"] == "Installed uv rejected conflicting CLI flags"
    assert "top-secret" not in json.dumps(receipt)


def test_install_failure_diagnostics_are_redacted_and_bounded(tmp_path):
    import json
    from aura_core.evolution.isolated_venv import _record_safe_install_failure
    workspace = tmp_path / "evolution"
    (workspace / "logs").mkdir(parents=True)
    runtime = workspace / "runtime" / "vendor__memory"
    runtime.mkdir(parents=True)
    _record_safe_install_failure(
        workspace, runtime,
        "TOKEN=secret_should_not_be_logged\nNo matching distribution found for secret.pkg",
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
