"""Stateful MCP regression with real signed evidence and Gateway authorization.

The transport is simulated; runtime fingerprints, Owner delegation, registry,
PermissionEngine and MCPGateway checks use the production implementations.
A separate Windows-only test exercises the real Job Object/SQLite process.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace

from aura_core.evolution.activation_runtime import (
    DelegatedMCPActivationManager, DockerMCPProvider, runtime_fingerprint,
)
from aura_core.evolution.windows_job_mcp import local_mcp_state_root
from aura_core.kernel.permissions import AuthorizationDecision
from test_evolution_autonomous_activation import _kernel, _request, _signed_fixture


def test_three_gateway_calls_write_sqlite_without_quarantining_signed_runtime(
    tmp_path, monkeypatch,
):
    workspace, name, repository = _signed_fixture(tmp_path, monkeypatch)
    state = local_mcp_state_root(workspace, name)
    fingerprint = runtime_fingerprint(workspace, name)
    kernel, gateway = _kernel()

    class StatefulWire:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(
                name="lookup_local",
                description="Local SQLite",
                input_schema={"type": "object", "additionalProperties": False},
            )])

        async def call_tool(self, tool, arguments):
            assert tool == "lookup_local"
            # Equivalent to a Windows MCP writing a relative SQLite file from
            # its dedicated state cwd, not its signed package source tree.
            with sqlite3.connect(state / "projectmem.sqlite3") as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY)"
                )
                conn.execute("INSERT INTO sessions DEFAULT VALUES")
                conn.commit()
                calls = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            return SimpleNamespace(structured_content={"calls": calls})

        async def close(self):
            return None

    manager = None

    async def factory(package, grant, entry):
        assert package == name
        return DockerMCPProvider(
            StatefulWire(),
            runtime=workspace.root / "runtime" / name,
            archive_sha256="", workspace=workspace, package=name,
            on_failure=lambda key: asyncio.create_task(manager.quarantine(key)),
            owner_authorized=lambda: manager._still_authorized(name),
            attestation_expires_at=int(time.time()) + 600,
        )

    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    async def scenario():
        assert await manager.scan() == [repository]
        inventory = json.loads(workspace.active.read_text("utf-8"))["active"]
        assert inventory[0]["status"] == "ACTIVE"
        cap = inventory[0]["capabilities"][0]
        scope = "evolution:isolated:" + inventory[0]["source_sha256"] + ":lookup_local"
        for expected in range(1, 4):
            response = await gateway.invoke(_request(cap, "lookup_local", scope))
            assert response.decision is AuthorizationDecision.ALLOW
            assert response.result == {"calls": expected}
            assert runtime_fingerprint(workspace, name) == fingerprint
            current = json.loads(workspace.active.read_text("utf-8"))["active"][0]
            assert current["status"] == "ACTIVE"
        denied = await gateway.invoke(
            _request(cap, "lookup_local", scope, principal="untrusted")
        )
        assert denied.decision is AuthorizationDecision.DENY
        assert (state / "projectmem.sqlite3").exists()
        assert not (workspace.root / "runtime" / name / "projectmem.sqlite3").exists()
        await manager.close()

    asyncio.run(scenario())
