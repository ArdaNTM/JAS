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


def test_malicious_project_script_is_not_an_arbitrary_shell_command():
    files = {
        "pyproject.toml": b"[project.scripts]\nmemory = 'os.system:run'\n",
        "src/memory_mcp/runner.py": b"print('not MCP')\n",
    }
    with pytest.raises(Exception):
        choose_python_entrypoint(files, "pyproject.toml")


def test_launcher_restores_only_missing_user_environment():
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "launch-aura-desktop.ps1").read_text("utf-8")
    for name in (
        "AURA_STORAGE_MODE", "AURA_EVOLUTION_ROOT",
        "AURA_EVOLUTION_AUTO_ACTIVATE", "AURA_EVOLUTION_DELEGATION_KEY_SHA256",
        "AURA_EVOLUTION_ATTESTOR_KEY_SHA256",
    ):
        assert f'GetEnvironmentVariable("{name}", "User")' in text
    assert "Start-Attestor" in text
    assert "autonomous_delegation.json" not in text


def test_setup_clears_clipboard_in_windows_powershell_51():
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "setup-autonomous-aura.ps1").read_text("utf-8")
    assert 'cmd.exe /c "echo off | clip" | Out-Null' in text
    assert "Set-Clipboard -Value ''" not in text
