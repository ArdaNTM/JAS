"""TDD: Python-only MCP discovery and bounded multi-module static acceptance.

Untrusted Python is never imported or executed by these tests.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

from aura_core.evolution.external_staging import _validated_files, StagingRejected
from aura_core.evolution.sandbox_preflight import SandboxUntrusted, choose_python_entrypoint
from aura_core.evolution.windows_job_mcp import (
    static_python_entry, _project_script_launch, _isolated_entry_args,
)
from aura_core.evolution.isolated_venv import declared_dependencies
from aura_core.evolution.self_discovery import QUERIES, SelfDiscoveryEngine
from aura_core.evolution.external_staging import EvolutionWorkspace


def _archive(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr("repo-commit/" + name, data)
    return stream.getvalue()


SERVER = (
    b"from mcp.server.fastmcp import FastMCP\n"
    b"mcp = FastMCP('local')\n"
    b"def main(): mcp.run(transport='stdio')\n"
)
TOOLS = (
    b"from memory_server.server import mcp\n"
    b"@mcp.tool()\n"
    b"def recall(key: str) -> str: return key\n"
)
SCRIPT = b"[project]\nname='memory-mcp'\n[project.scripts]\nmemory-server='memory_server.cli:main'\n"


def test_discovery_queries_python_fastmcp_first_and_still_budgeted():
    assert len(QUERIES) == len(set(QUERIES))
    assert any('"FastMCP" "mcp.tool"' in query for query in QUERIES)
    assert any('"from mcp.server.fastmcp import FastMCP"' in query for query in QUERIES)
    assert any('"from fastmcp import FastMCP"' in query for query in QUERIES)
    assert all("language:Python" in query and "size:<25000" in query for query in QUERIES)
    assert "FastMCP" in QUERIES[0]


def test_pep621_script_wins_over_confusing_server_hint():
    files = {
        "pyproject.toml": SCRIPT,
        "server.py": b"from fastmcp import FastMCP\nmcp = FastMCP('unrelated')\n",
        "src/memory_server/cli.py": b"from .server import main\n",
        "src/memory_server/server.py": SERVER,
        "src/memory_server/tools/recall.py": TOOLS,
    }
    assert choose_python_entrypoint(files, "server.py") == "src/memory_server/cli.py"
    assert static_python_entry(files, "server.py") == "src/memory_server/cli.py"


def test_nested_pyproject_project_script_resolves_and_launches(tmp_path):
    files = {
        "packages/roam/pyproject.toml": SCRIPT,
        "packages/roam/src/memory_server/cli.py": b"from .server import main\n",
        "packages/roam/src/memory_server/server.py": SERVER,
        "packages/roam/src/memory_server/tools/recall.py": TOOLS,
        "server.py": b"print('not an MCP')\n",
    }
    expected = "packages/roam/src/memory_server/cli.py"
    assert choose_python_entrypoint(files, "server.py") == expected
    assert static_python_entry(files, "server.py") == expected
    runtime = tmp_path / "runtime" / "example__roam"
    runtime.mkdir(parents=True)
    (runtime / "packages" / "roam").mkdir(parents=True)
    (runtime / "packages" / "roam" / "pyproject.toml").write_bytes(SCRIPT)
    assert _project_script_launch(runtime, expected) == ("memory_server.cli", "main")
    python = runtime / ".venv" / "Scripts" / "python.exe"
    assert _isolated_entry_args(runtime, expected, python)[-2:] == [
        "-m", "memory_server.cli",
    ]


def test_split_absolute_import_tool_and_mcp_definition_accepted():
    files = {
        "pyproject.toml": SCRIPT,
        "src/memory_server/cli.py": b"from memory_server.server import main\n",
        "src/memory_server/server.py": SERVER,
        "src/memory_server/tools/recall.py": TOOLS,
    }
    assert static_python_entry(files, "pyproject.toml") == "src/memory_server/cli.py"


def test_non_mcp_and_cross_package_stitched_evidence_denied():
    files = {
        "pyproject.toml": SCRIPT,
        "src/memory_server/cli.py": b"print('does nothing')\n",
        "src/memory_server/server.py": b"def unrelated(): return 1\n",
        "src/other/server.py": SERVER,
        "src/other/tools.py": TOOLS,
    }
    with pytest.raises(SandboxUntrusted, match="AST lacks"):
        static_python_entry(files, "pyproject.toml")


def test_bounded_package_ast_rejects_oversized_module():
    files = {
        "pyproject.toml": SCRIPT,
        "src/memory_server/cli.py": b"from .server import main\n",
        "src/memory_server/server.py": SERVER,
        "src/memory_server/tools.py": TOOLS + b"\n" + b"#" * 550_000,
    }
    with pytest.raises(SandboxUntrusted, match="AST|module|budget"):
        static_python_entry(files, "pyproject.toml")


def test_requires_python_incompatible_gives_actionable_reason():
    required = f">={sys.version_info.major}.{sys.version_info.minor + 1}"
    files = {"pyproject.toml": (
        "[project]\nname='local'\nrequires-python='" + required + "'\n"
    ).encode()}
    with pytest.raises(SandboxUntrusted, match=(
        r"PythonVersionIncompatible: requires " +
        __import__("re").escape(required) + r", host is " +
        str(sys.version_info.major) + r"\." + str(sys.version_info.minor)
    )):
        declared_dependencies(files)


@pytest.mark.parametrize("files", [
    {"README.md": b"Fully local offline no API keys", "go.mod": b"module local/mcp\n", "main.go": b"package main"},
    {"README.md": b"Fully local offline no API keys", "package.json": b'{"name":"node-mcp"}', "index.ts": b"import { Server } from '@modelcontextprotocol/sdk';"},
    {"README.md": b"Fully local offline no API keys", "Cargo.toml": b"[package]\nname='mcp'\n", "src/main.rs": b"fn main() {}"},
    {"README.md": b"Fully local offline no API keys", "server.py": b"from django.core.wsgi import get_wsgi_application\napplication=get_wsgi_application()\n"},
])
def test_non_python_stdio_mcp_rejected_before_verified(files):
    with pytest.raises(StagingRejected, match="Python stdio MCP"):
        _validated_files(_archive(files))


def test_python_multimodule_candidate_still_reaches_static_review():
    reviewed, entry, skipped = _validated_files(_archive({
        "README.md": b"Fully local offline MCP without any API key",
        "pyproject.toml": SCRIPT,
        "src/memory_server/cli.py": b"from .server import main\n",
        "src/memory_server/server.py": SERVER,
        "src/memory_server/tools/recall.py": TOOLS,
    }))
    assert entry.endswith(".py") or entry == "pyproject.toml"
    assert "src/memory_server/server.py" in reviewed
    assert skipped == 0


def test_existing_python_fastmcp_candidates_sort_before_old_non_python_queue(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "outside")
    engine = SelfDiscoveryEngine(
        gateway=object(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        for i, (name, hint) in enumerate((
            ("Gentleman-Programming/engram", "Go local memory"),
            ("Jpisnice/shadcn-ui-mcp-server", "Node TypeScript MCP"),
            ("example/fastmcp-python", "Python FastMCP local memory"),
        )):
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id, repository, url, description, license, capability_hint,"
                " created_at) VALUES (?,?,?,?,?,?,?)",
                (str(i), name, "https://github.com/" + name, hint, "MIT", "MCP", i),
            )
    # The selection remains Gateway-only; inspect the pure ordering key.
    from aura_core.evolution.self_discovery import _python_mcp_priority
    assert _python_mcp_priority("example/fastmcp-python", "Python FastMCP local") < (
        _python_mcp_priority("Gentleman-Programming/engram", "Go local memory")
    )

def test_non_python_legacy_staging_is_marked_unsupported_without_retry(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from aura_core.kernel.permissions import AuthorizationDecision

    workspace = EvolutionWorkspace(tmp_path / "outside")
    class Gateway:
        attempts = 0

        async def invoke(self, request):
            self.attempts += 1
            raise ValueError("No supported Python stdio MCP entrypoint")

    gateway = Gateway()
    engine = SelfDiscoveryEngine(
        gateway=gateway, db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id, repository, url, description, license, capability_hint,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            ("legacy-go", "Gentleman-Programming/engram",
             "https://github.com/Gentleman-Programming/engram",
             "Local Golang memory MCP", "MIT", "MCP", 1.0),
        )
    first = asyncio.run(engine._stage_pending())
    assert first["attempted"] == 1
    with sqlite3.connect(engine._db_path) as db:
        status, error = db.execute(
            "SELECT package_status, package_error FROM evolution_proposals"
        ).fetchone()
    assert status == "UNSUPPORTED_RUNTIME"
    assert error == "No supported Python stdio MCP entrypoint"
    assert asyncio.run(engine._stage_pending())["attempted"] == 0
    assert gateway.attempts == 1
    assert workspace.verified_packages() == []


def test_project_specific_requires_python_checked_before_install(tmp_path):
    from aura_core.evolution.isolated_venv import prepare_isolated_venv
    incompatible = f">={sys.version_info.major}.{sys.version_info.minor + 1}"
    files = {
        "packages/roam/pyproject.toml": (
            f"[project]\\nname='roam'\\nrequires-python='{incompatible}'\\n"
        ).encode("utf-8"),
        "packages/roam/src/roam/cli.py": b"from roam.server import main\\n",
    }
    runtime = tmp_path / "runtime" / "example__roam"
    runtime.mkdir(parents=True)
    with pytest.raises(SandboxUntrusted, match="PythonVersionIncompatible"):
        prepare_isolated_venv(
            runtime, files, tmp_path,
            entry="packages/roam/src/roam/cli.py", install=False,
        )
    assert not (runtime / ".venv").exists()
