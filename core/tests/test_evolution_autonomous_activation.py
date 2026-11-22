"""End-to-end delegated offline MCP: real Registry + Gateway, with fake Docker transport only.

The independent Ed25519 signers are generated in the test harness. Production
never possesses their private keys in AURA Core and runs real pinned Docker.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import time
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution.activation_runtime import (
    DelegatedMCPActivationManager, tool_binding_digest, runtime_fingerprint,
)
from aura_core.evolution.external_staging import EvolutionWorkspace
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight
from aura_core.evolution.owner_cli import make_activation_delegation
from aura_core.evolution.activation_delegation import (
    SANDBOX_POLICY_SHA256, SANDBOX_TESTS_SHA256,
)
from aura_core.evolution.sandbox_attestor import (
    SandboxClaims, SignedSandboxAttestation, DOMAIN, canonical_claims,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.services import ServiceRegistry
from aura_core.kernel.permissions import PermissionEngine, AuthorizationDecision, RiskLevel
from aura_core.kernel.events import EventBus
from aura_core.mcp.provider import ProviderRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool


class FakeProvider:
    def __init__(self):
        self.tools = (MCPTool(
            name="lookup_local", description="Read local SQLite",
            input_schema={"type": "object", "additionalProperties": False},
        ),)
        self.calls = 0
        self.closed = False

    async def list_tools(self):
        return self.tools

    async def call_tool(self, name, arguments=None):
        self.calls += 1
        return {"local": True}

    async def close(self):
        self.closed = True


def _kernel():
    events = EventBus()
    services = ServiceRegistry(event_bus=events)
    capabilities = CapabilityRegistry(services, event_bus=events)
    providers = ProviderRegistry(services, event_bus=events)
    permissions = PermissionEngine(capabilities, event_bus=events)
    kernel = SimpleNamespace(
        service_registry=services, capability_registry=capabilities,
        provider_registry=providers, permission_engine=permissions, event_bus=events,
    )
    gateway = MCPGateway(capabilities, providers, permissions, event_bus=events)
    return kernel, gateway


def _signed_fixture(tmp_path, monkeypatch):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    name = "test__local-memory"
    repository = "test/local-memory"
    package = workspace.root / "verified" / name
    package.mkdir()
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("snapshot/README.md", "Fully local, offline, no API keys")
        z.writestr("snapshot/server.py", "from fastmcp import FastMCP\napp=FastMCP('memory')")
        z.writestr("snapshot/pyproject.toml", "[project]\nname='memory'")
        z.writestr("snapshot/docs/ignored.md", "documentation")
    archive = zipped.getvalue()
    sha = hashlib.sha256(archive).hexdigest()
    (package / "source.zip").write_bytes(archive)
    (package / "aura-capability-manifest.json").write_text(json.dumps({
        "repository": repository, "source_sha256": sha,
        "status": "READY_FOR_OWNER_REVIEW",
        "license_spdx_metadata": "MIT", "entrypoint_hint": "pyproject.toml",
        "detected_capabilities": ["FastMCP", "sqlite3", "local memory"],
        "sandbox_attested": False, "activation_performed": False,
        "execution_allowed": False,
    }), encoding="utf-8")
    image = "example/mcp@sha256:" + "a" * 64
    IsolatedMCPPreflight(workspace, image=image).prepare(name)

    owner_signer = Ed25519PrivateKey.generate()
    attestor_signer = Ed25519PrivateKey.generate()
    workspace._testing_attestor_signer = attestor_signer
    owner_raw = owner_signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    attestor_raw = attestor_signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    owner = workspace.root / "owner"
    owner.mkdir()
    (owner / "autonomous_delegation.pub.pem").write_bytes(
        owner_signer.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    doc = make_activation_delegation(
        owner_signer, categories=("local_memory",), image=image,
        policy_sha256=SANDBOX_POLICY_SHA256, tests_sha256=SANDBOX_TESTS_SHA256,
        attestor_key_sha256=hashlib.sha256(attestor_raw).hexdigest(),
        attestor_runner_id="operator_runner", days=1,
        max_tools=2, min_score=70,
    )
    (owner / "autonomous_delegation.json").write_text(json.dumps(doc))
    if os.name == "posix":
        owner.chmod(0o700)
        for file in owner.iterdir():
            file.chmod(0o600)
    else:
        from test_evolution_decision_engine import _private_windows_test_owner_state
        _private_windows_test_owner_state(workspace)
    trust = workspace.root / "trust"
    trust.mkdir()
    (trust / "sandbox-attestor.pub.pem").write_bytes(
        attestor_signer.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    monkeypatch.setenv("AURA_STORAGE_MODE", "local")
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "1")
    monkeypatch.setenv(
        "AURA_EVOLUTION_DELEGATION_KEY_SHA256",
        hashlib.sha256(owner_raw).hexdigest(),
    )
    tool = FakeProvider().tools[0]
    from aura_core.evolution.decision_engine import EvolutionDecisionEngine
    decision = EvolutionDecisionEngine(workspace).evaluate(name)
    assert decision.status == "AUTO_APPROVED_BY_POLICY"
    tree = runtime_fingerprint(workspace, name)
    binding = tool_binding_digest(
        repository=repository, source_sha256=sha, tree_sha256=tree,
        image=image, tool=tool, category=decision.category,
    )
    now = int(time.time())
    claims = SandboxClaims(
        source_sha256=sha, tests_sha256=SANDBOX_TESTS_SHA256,
        image_digest="sha256:" + "a" * 64,
        policy_sha256=SANDBOX_POLICY_SHA256, binding_digest=binding,
        run_id=secrets.token_hex(16), runner_id="operator_runner",
        issued_at=now, expires_at=now + 600,
        exit_code=0, outcome="passed", network_disabled=True,
        rootfs_readonly=True,
    )
    signed = SignedSandboxAttestation(
        key_id="operator_attestor", claims=claims,
        signature_b64=base64.b64encode(
            attestor_signer.sign(DOMAIN + canonical_claims(claims)),
        ).decode("ascii"),
    )
    (package / "independent-attestations.json").write_text(json.dumps({
        "schema": "aura.external-attested-tools.v1",
        "repository": repository,
        "runtime_tree_sha256": tree,
        "tools": [{
            "name": tool.name, "input_schema": tool.input_schema,
            "attestation": signed.to_dict(),
        }],
    }))
    return workspace, name, repository


def _request(capability, tool, scope, *, principal="local_owner"):
    return MCPGatewayRequest(
        request_id=str(uuid4()), principal_id=principal,
        capability_id=capability, operation_id=capability,
        resource_scope=scope, risk_level=RiskLevel.LOW,
        tool_name=tool, arguments={},
    )


def test_default_without_delegation_never_registers(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "0")
    kernel, gateway = _kernel()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=lambda *_: None,
    )
    assert asyncio.run(manager.scan()) == []
    assert not kernel.capability_registry.records()
    assert json.loads(workspace.active.read_text())["active"] == []


def test_live_signed_activation_gateway_and_restart_persistence(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, gateway = _kernel()
    provider = FakeProvider()

    async def factory(_name, _grant, _entry):
        return provider

    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    async def live():
        assert await manager.scan() == [repo]
        inventory = json.loads(workspace.active.read_text())
        assert inventory["active"][0]["status"] == "ACTIVE"
        capability = inventory["active"][0]["capabilities"][0]
        scope = ("evolution:isolated:" +
                 inventory["active"][0]["source_sha256"] + ":lookup_local")
        response = await gateway.invoke(_request(capability, "lookup_local", scope))
        assert response.decision is AuthorizationDecision.ALLOW
        assert response.result == {"local": True}
        denied = await gateway.invoke(_request(
            capability, "lookup_local", scope, principal="unauthorized",
        ))
        assert denied.decision is AuthorizationDecision.DENY
        assert provider.calls == 1
        assert len(manager.tools.records()) == 1
        await manager.close()
        assert json.loads(workspace.active.read_text())["active"][0]["status"] == "ACTIVE"
    asyncio.run(live())

    second_kernel, second_gateway = _kernel()
    second_provider = FakeProvider()
    async def second_factory(*_):
        return second_provider
    manager2 = DelegatedMCPActivationManager(
        workspace=workspace, kernel=second_kernel, provider_factory=second_factory,
    )

    async def restart():
        assert await manager2.scan() == [repo]
        assert second_kernel.capability_registry.records()
        await manager2.quarantine(name)
        assert not second_kernel.capability_registry.records()
        assert not second_kernel.provider_registry.records()
        assert not manager2.tools.records()
        assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"
    asyncio.run(restart())


def test_tampered_attestation_cannot_register(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    file = workspace.root / "verified" / name / "independent-attestations.json"
    bundle = json.loads(file.read_text())
    bundle["tools"][0]["input_schema"]["properties"] = {"evil": {"type": "string"}}
    file.write_text(json.dumps(bundle))
    kernel, _ = _kernel()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel,
        provider_factory=lambda *_: None,
    )
    assert asyncio.run(manager.scan()) == []
    assert not kernel.capability_registry.records()
    assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"


def test_owner_revocation_immediately_blocks_live_tool(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    provider = FakeProvider()
    async def factory(*_):
        return provider
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    async def revoke():
        assert await manager.scan() == [repo]
        (workspace.root / "owner" / "autonomous_delegation.json").unlink()
        await manager.scan()
        assert not kernel.capability_registry.records()
        assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"
        assert provider.closed is True
    asyncio.run(revoke())


def test_owner_review_one_click_denial_only_quarantines_on_next_scan(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aura_core.evolution.owner_control_plane_http import build_local_review_app
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    provider = FakeProvider()
    async def factory(*_):
        return provider
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    assert asyncio.run(manager.scan()) == [repo]
    with TestClient(build_local_review_app(workspace.root),
                    base_url="http://localhost:8766") as client:
        status = client.get("/api/owner/activations")
        assert status.status_code == 200
        assert status.json()["items"][0]["status"] == "ACTIVE"
        rejected = client.post(
            "/api/owner/activations/quarantine", json={"repository": repo},
            headers={"Origin": "http://attacker.example"},
        )
        assert rejected.status_code == 403
        assert client.get("/api/owner/activations").json()["items"][0]["status"] == "ACTIVE"
        approved = client.post(
            "/api/owner/activations/quarantine", json={"repository": repo},
            headers={"Origin": "http://localhost:8766"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "REVOKED"
        assert approved.json()["authorization_granted"] is False
        assert client.post(
            "/api/owner/activations/quarantine",
            json={"repository": repo}, headers={"Origin": "http://localhost:8766"},
        ).status_code == 409
    assert asyncio.run(manager.scan()) == []
    assert not kernel.capability_registry.records()
    assert provider.closed
    assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"
    assert asyncio.run(manager.scan()) == []


def test_quarantined_external_mcp_does_not_auto_reactivate(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    async def factory(*_):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    assert asyncio.run(manager.scan()) == [repo]
    asyncio.run(manager.quarantine(name))
    assert asyncio.run(manager.scan()) == []
    assert not kernel.provider_registry.records()
    assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"


def test_expired_independent_attestation_quarantines_or_waits(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    async def factory(*_):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    async def run():
        assert await manager.scan() == [repo]
        item = manager._active[name]
        item.attestation_expires_at = 0
        # Expiry must remove the live provider before new proof checks.
        assert await manager.scan() == []
        assert not kernel.capability_registry.records()
        status = json.loads(workspace.active.read_text())["active"][0]["status"]
        assert status == "WAITING_ATTESTATION"
    asyncio.run(run())


def test_signed_windows_nineteen_mcp_tools_preflight_attest_and_activate(
    tmp_path, monkeypatch,
):
    """Bounded 19-tool/27,351-byte full signed proof -> Gateway -> inventory.

    Only the connection transport and wheel installer are inert: production
    authorization, exact-source hashing, Ed25519 signatures and registration
    are real. Untrusted source code is never imported or executed.
    """
    import shutil
    from aura_core.evolution import (
        activation_runtime, attestor_worker, windows_job_mcp, isolated_venv,
    )
    from aura_core.evolution.activation_delegation import (
        SANDBOX_POLICY_SHA256, SANDBOX_TESTS_SHA256,
    )
    from aura_core.evolution.owner_cli import make_activation_delegation
    from aura_core.evolution.sandbox_preflight import (
        _schema_json_size, SandboxUntrusted,
    )

    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    pkg = workspace.root / "verified" / name
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("snapshot/README.md", "Fully local, offline MCP server; no API keys required; signed proof")
        z.writestr(
            "snapshot/server.py",
            "from fastmcp import FastMCP\n"
            "app = FastMCP('memory')\n"
            "@app.tool()\ndef ping() -> str: return 'pong'\n"
            "if __name__ == '__main__': app.run()\n",
        )
        z.writestr("snapshot/pyproject.toml", "[project]\nname='memory'\n")
    source = archive.getvalue()
    (pkg / "source.zip").write_bytes(source)
    manifest = pkg / "aura-capability-manifest.json"
    metadata = json.loads(manifest.read_text("utf-8"))
    metadata["source_sha256"] = hashlib.sha256(source).hexdigest()
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    (pkg / "independent-attestations.json").unlink()
    shutil.rmtree(workspace.root / "runtime" / name)
    IsolatedMCPPreflight(
        workspace, image="example/mcp@sha256:" + "a" * 64,
    ).prepare(name)

    owner_signer = Ed25519PrivateKey.generate()
    attestor_signer = workspace._testing_attestor_signer
    owner_raw = owner_signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    attestor_raw = attestor_signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    grant = make_activation_delegation(
        owner_signer, categories=("local_memory",), image=None,
        policy_sha256=SANDBOX_POLICY_SHA256,
        tests_sha256=SANDBOX_TESTS_SHA256,
        attestor_key_sha256=hashlib.sha256(attestor_raw).hexdigest(),
        attestor_runner_id="operator_runner",
        days=1, max_tools=64, min_score=70,
        allow_local_windows_process=True,
    )
    owner_dir = workspace.root / "owner"
    (owner_dir / "autonomous_delegation.pub.pem").write_bytes(
        owner_signer.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (owner_dir / "autonomous_delegation.json").write_text(
        json.dumps(grant), encoding="utf-8",
    )
    if os.name == "nt":
        from test_evolution_decision_engine import _private_windows_test_owner_state
        _private_windows_test_owner_state(workspace)
    else:
        for p in owner_dir.iterdir():
            p.chmod(0o600)
    monkeypatch.setenv(
        "AURA_EVOLUTION_DELEGATION_KEY_SHA256",
        hashlib.sha256(owner_raw).hexdigest(),
    )

    # No modification to the real process-wide os.name (pathlib/ACL safety).
    class EmulatedWindows:
        name = "nt"

        def __getattr__(self, attr):
            return getattr(os, attr)

    for module in (windows_job_mcp, attestor_worker, activation_runtime):
        monkeypatch.setattr(module, "os", EmulatedWindows())

    schemas = {
        f"memory_{i:02d}": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }
        for i in range(19)
    }
    base_size = _schema_json_size(schemas)
    schemas["memory_00"]["properties"]["query"]["description"] = ""
    overhead = _schema_json_size(schemas) - base_size
    padding = 27_351 - base_size - overhead
    assert padding > 0
    schemas["memory_00"]["properties"]["query"]["description"] = "x" * padding
    # Schema map accounting includes all tool names and JSON overhead.
    assert _schema_json_size(schemas) == 27_351
    tools19 = tuple(
        MCPTool(name=n, description="", input_schema=s) for n, s in schemas.items()
    )
    current = {"tools": list(tools19)}

    class InertConnection:
        async def connect_stdio(self, params):
            assert params.command
        async def list_tools(self):
            return SimpleNamespace(tools=list(current["tools"]))
        async def close(self):
            pass

    monkeypatch.setattr(windows_job_mcp, "MCPConnection", InertConnection)
    monkeypatch.setattr(
        isolated_venv, "prepare_isolated_venv",
        lambda *args, **kwargs: None,
    )

    class FakeNineteenProvider:
        calls = 0
        async def list_tools(self):
            return tools19
        async def call_tool(self, name, arguments=None):
            self.calls += 1
            return {"tool": name}
        async def close(self):
            pass

    async def factory(*_):
        return FakeNineteenProvider()

    kernel, gateway = _kernel()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    async def run():
        preflight = windows_job_mcp.LocalWindowsMCPPreflight(
            workspace, owner_grant=grant["claims"],
        )
        report = await preflight.probe(name)
        assert report["status"] == "PREPARED_UNATTESTED"
        assert len(report["tool_schemas"]) == 19
        assert _schema_json_size(report["tool_schemas"]) == 27_351

        attestor = attestor_worker.IndependentMCPAttestorWorker(
            workspace=workspace, key=attestor_signer,
        )
        evidence = await attestor.scan()
        assert len(evidence) == 1 and evidence[0]["attested_tools"] == 19
        bundle = json.loads(
            (pkg / "independent-attestations.json").read_text("utf-8")
        )
        assert len(bundle["tools"]) == 19
        assert bundle["execution_profile"] == "windows-job-stdio"

        assert await manager.scan() == [repo]
        inventory = json.loads(workspace.active.read_text("utf-8"))
        active = [x for x in inventory["active"] if x["status"] == "ACTIVE"]
        assert len(active) == 1
        assert active[0]["repository"] == repo
        assert len(active[0]["capabilities"]) == 19
        assert len(kernel.capability_registry.records()) == 19
        first = active[0]["capabilities"][0]
        tool = first.rsplit(".", 1)[-1]
        scope = "evolution:isolated:" + active[0]["source_sha256"] + ":" + tool
        allowed = await gateway.invoke(_request(first, tool, scope))
        denied = await gateway.invoke(_request(
            first, tool, scope, principal="unsigned-actor",
        ))
        assert allowed.decision is AuthorizationDecision.ALLOW
        assert denied.decision is AuthorizationDecision.DENY
        from aura_core.application.api import _external_mcp_execution_scope
        assert _external_mcp_execution_scope(
            kernel.permission_engine, "local_owner", first,
        ) == scope
        assert _external_mcp_execution_scope(
            kernel.permission_engine, "unauthorized", first,
        ) is None

        # Negative cap and schema tests reuse the real probe, not a
        # reimplemented mock of its limits.
        extra = tuple(
            MCPTool(name=f"extra_{i:02d}", description="",
                    input_schema={"type": "object"})
            for i in range(45)
        )
        current["tools"] = list(tools19 + extra)
        assert len((await preflight.probe(name))["tool_schemas"]) == 64
        current["tools"].append(MCPTool(
            name="overflow_65", description="", input_schema={"type": "object"},
        ))
        with pytest.raises(SandboxUntrusted, match="oversized"):
            await preflight.probe(name)
        current["tools"] = list(tools19)
        huge = {k: dict(v) for k, v in schemas.items()}
        huge["memory_00"] = {
            "type": "object",
            "properties": {"query": {
                "type": "string", "description": "x" * 65_536,
            }},
        }
        current["tools"] = [
            MCPTool(name=k, description="", input_schema=v)
            for k, v in huge.items()
        ]
        with pytest.raises(SandboxUntrusted, match="Oversized"):
            await preflight.probe(name)

        await manager.close()

    asyncio.run(run())


def test_independent_attestor_observes_mcp_and_signs_exact_gateway_binding(
    tmp_path, monkeypatch,
):
    from aura_core.evolution.attestor_worker import IndependentMCPAttestorWorker
    from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    proof_path = workspace.root / "verified" / name / "independent-attestations.json"
    proof_path.unlink()
    tool = FakeProvider().tools[0]

    async def fake_probe(self, package_name):
        assert package_name == name
        return {
            "repository": repo,
            "status": "PREPARED_UNATTESTED",
            "tool_schemas": {tool.name: tool.input_schema},
            "tool_count": 1, "sandbox_attested": False,
            "activation_performed": False,
        }

    monkeypatch.setattr(IsolatedMCPPreflight, "probe", fake_probe)
    attestor = IndependentMCPAttestorWorker(
        workspace=workspace, key=workspace._testing_attestor_signer,
    )
    evidence = asyncio.run(attestor.attest(name))
    assert evidence["attested_tools"] == 1
    assert proof_path.is_file()
    kernel, gateway = _kernel()
    async def factory(*_):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    async def live():
        assert await manager.scan() == [repo]
        inventory = json.loads(workspace.active.read_text())
        capability = inventory["active"][0]["capabilities"][0]
        scope = "evolution:isolated:" + inventory["active"][0]["source_sha256"] + ":" + tool.name
        response = await gateway.invoke(_request(capability, tool.name, scope))
        assert response.decision is AuthorizationDecision.ALLOW
        assert response.result == {"local": True}
        await manager.close()
    asyncio.run(live())


@pytest.mark.skipif(os.name == "nt", reason="independent Windows ACL attestor manual provisioning")
def test_independent_attestor_provisioning_never_overwrites_private_identity(tmp_path):
    from aura_core.evolution.attestor_worker import provision_attestor
    workspace = EvolutionWorkspace(tmp_path / "outside")
    root = tmp_path / "owner-only-attestor"
    root.mkdir()
    root.chmod(0o700)
    digest = provision_attestor(workspace=workspace, key_root=root)
    assert len(digest) == 64
    private = root / "sandbox-attestor.pem"
    assert private.stat().st_mode & 0o077 == 0
    assert (workspace.root / "trust" / "sandbox-attestor.pub.pem").is_file()
    with pytest.raises(FileExistsError):
        provision_attestor(workspace=workspace, key_root=root)


def test_quota_quarantined_inventory_reactivates_only_after_signed_fresh_evidence(
    tmp_path, monkeypatch,
):
    from aura_core.evolution import activation_runtime

    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    provider = FakeProvider()

    async def factory(*_):
        return provider

    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    signed = manager.delegation.verified_grant()
    assert signed is not None
    grant = {**signed, "allow_local_windows_process": True}
    # Emulate the separately signed Windows-local pathway without changing
    # process-global os.name or running a host executable in the tests.
    class WindowsOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(os, key)

    monkeypatch.setattr(activation_runtime, "os", WindowsOs())
    manager.delegation = SimpleNamespace(verified_grant=lambda: grant)
    manager._persist(
        repo, "QUARANTINED", reason_code="PermissionError",
        recovery_version=1,
    )
    marker = workspace.root / "verified" / name / "local-windows-quarantined.json"
    marker.write_text('{"status":"QUARANTINED"}', encoding="utf-8")
    assert asyncio.run(manager.scan()) == []
    assert not kernel.capability_registry.records()

    marker.unlink()
    assert asyncio.run(manager.scan()) == [repo]
    assert json.loads(workspace.active.read_text())["active"][0]["status"] == "ACTIVE"
    assert kernel.capability_registry.records()
    asyncio.run(manager.close())


def test_quarantined_inventory_with_tampered_signature_stays_blocked(
    tmp_path, monkeypatch,
):
    from aura_core.evolution import activation_runtime

    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel,
        provider_factory=lambda *_: None,
    )
    grant = manager.delegation.verified_grant()
    assert grant is not None
    manager.delegation = SimpleNamespace(
        verified_grant=lambda: {**grant, "allow_local_windows_process": True},
    )
    class WindowsOs:
        name = "nt"

        def __getattr__(self, key):
            return getattr(os, key)

    monkeypatch.setattr(activation_runtime, "os", WindowsOs())
    manager._persist(repo, "QUARANTINED", reason_code="PermissionError")
    bundle = workspace.root / "verified" / name / "independent-attestations.json"
    data = json.loads(bundle.read_text("utf-8"))
    data["tools"][0]["attestation"]["signature_b64"] = base64.b64encode(
        b"0" * 64,
    ).decode("ascii")
    bundle.write_text(json.dumps(data), encoding="utf-8")
    assert asyncio.run(manager.scan()) == []
    assert not kernel.capability_registry.records()
    assert json.loads(workspace.active.read_text())["active"][0]["status"] == "QUARANTINED"
