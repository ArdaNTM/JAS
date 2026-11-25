"""Production stability regressions; signatures and Gateway are real, transport is inert."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import replace
import hashlib
import json
import secrets
import shutil
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution.activation_delegation import canonical
from aura_core.evolution.activation_runtime import (
    DelegatedMCPActivationManager, DockerMCPProvider, runtime_fingerprint, tool_binding_digest,
)
from aura_core.evolution.attestor_health import AttestorHealth, attestor_lock, read_attestor_health
from aura_core.evolution.attestor_worker import IndependentMCPAttestorWorker
from aura_core.evolution.sandbox_attestor import DOMAIN, SignedSandboxAttestation, canonical_claims
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight
from aura_core.evolution.windows_job_mcp import (
    LOCAL_SCHEMA, LOCAL_POLICY_SHA256, LOCAL_TESTS_SHA256, local_sign, verify_local,
    local_mcp_state_root, _scrubbed_windows_mcp_environment,
    _require_observed_environment, local_binding,
)
from aura_core.kernel.permissions import AuthorizationDecision
from test_evolution_autonomous_activation import FakeProvider, _kernel, _request, _signed_fixture


def test_attestor_lock_is_exclusive_and_released(tmp_path):
    with attestor_lock(tmp_path):
        with pytest.raises(PermissionError, match="already running"):
            with attestor_lock(tmp_path):
                pytest.fail("second attestor entered")
    # OS releases ownership, even though the lock file itself remains.
    with attestor_lock(tmp_path):
        assert (tmp_path / ".independent-attestor.lock").is_file()


def test_attestor_health_is_bounded_and_informational(tmp_path):
    assert read_attestor_health(tmp_path)["state"] == "UNKNOWN"
    with AttestorHealth(tmp_path) as health:
        now = int(time.time())
        health.update(phase="IDLE", last_success=now, last_renewal=now)
        status = read_attestor_health(tmp_path)
        assert status["state"] == "IDLE"
        assert status["last_success"] == status["last_renewal"] == now
        health.update(phase="ERROR", last_error="PermissionError")
        assert read_attestor_health(tmp_path)["last_error"] == "PermissionError"
    assert read_attestor_health(tmp_path)["state"] == "STOPPED"
    path = tmp_path / "attestor-health.json"
    doc = json.loads(path.read_text())
    doc.update(phase="SCANNING", heartbeat=int(time.time()) - 100)
    path.write_text(json.dumps(doc))
    assert read_attestor_health(tmp_path)["state"] == "STALE"
    path.write_text("x" * 4097)
    assert read_attestor_health(tmp_path)["state"] == "UNKNOWN"


def test_attestor_capacity_and_bounded_fair_queue(tmp_path):
    worker = object.__new__(IndependentMCPAttestorWorker)
    worker.workspace = SimpleNamespace(root=tmp_path, max_items=125)
    worker._delegation = SimpleNamespace(verified_grant=lambda: {})
    seen = []
    decisions = [
        SimpleNamespace(repository=f"aa{i:03}/pending", status="REJECTED_EVIDENCE")
        for i in range(101)
    ] + [
        SimpleNamespace(repository=f"zz{i}/memory", status="AUTO_APPROVED_BY_POLICY")
        for i in range(6)
    ]
    def pending(*, limit):
        assert limit == 125
        return list(decisions[:limit])
    worker._decisions = SimpleNamespace(evaluate_pending=pending)
    async def attest(package):
        seen.append(package)
        return {"repository": package.replace("__", "/"), "attested_tools": 1}
    worker.attest = attest
    assert len(asyncio.run(worker.scan())) == 3
    assert len(asyncio.run(worker.scan())) == 3
    assert seen == [f"zz{i}__memory" for i in range(6)]


def _second_signed_package(workspace, name, repo, grant):
    second_repo = "zz/local-memory"
    second = second_repo.replace("/", "__")
    base = workspace.root / "verified"
    shutil.copytree(base / name, base / second)
    manifest = base / second / "aura-capability-manifest.json"
    data = json.loads(manifest.read_text())
    data["repository"] = second_repo
    manifest.write_text(json.dumps(data))
    IsolatedMCPPreflight(workspace, image=grant["oci_image"]).prepare(second)
    bundle_file = base / second / "independent-attestations.json"
    bundle = json.loads(bundle_file.read_text())
    tree = runtime_fingerprint(workspace, second)
    tool = FakeProvider().tools[0]
    binding = tool_binding_digest(
        repository=second_repo, source_sha256=data["source_sha256"], tree_sha256=tree,
        image=grant["oci_image"], tool=tool, category="local_memory",
    )
    envelope = SignedSandboxAttestation.from_dict(bundle["tools"][0]["attestation"])
    claims = replace(envelope.claims, binding_digest=binding, run_id=secrets.token_hex(16))
    signature = workspace._testing_attestor_signer.sign(DOMAIN + canonical_claims(claims))
    bundle.update(repository=second_repo, runtime_tree_sha256=tree)
    bundle["tools"][0]["attestation"] = SignedSandboxAttestation(
        key_id=envelope.key_id, claims=claims,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    ).to_dict()
    bundle_file.write_text(json.dumps(bundle))
    return second, second_repo


def test_same_category_independently_signed_providers_are_namespaced(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, gateway = _kernel()
    providers = {}
    async def factory(package, *_):
        providers[package] = FakeProvider()
        return providers[package]
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=kernel, provider_factory=factory)
    second, second_repo = _second_signed_package(workspace, name, repo, manager.delegation.verified_grant())
    async def run():
        assert await manager.scan() == [repo, second_repo]
        assert len(manager._active) == 2
        rows = {r["repository"]: r for r in manager._load_inventory()["active"]}
        first_cap, second_cap = (rows[r]["capabilities"][0] for r in (repo, second_repo))
        assert first_cap != second_cap
        assert rows[repo]["category"] == rows[second_repo]["category"] == "local_memory"
        assert await manager.scan() == []
        for repository, capability in ((repo, first_cap), (second_repo, second_cap)):
            scope = "evolution:isolated:" + rows[repository]["source_sha256"] + ":lookup_local"
            result = await gateway.invoke(_request(capability, "lookup_local", scope))
            assert result.decision is AuthorizationDecision.ALLOW
            denied = await gateway.invoke(_request(capability, "lookup_local", scope, principal="stranger"))
            assert denied.decision is AuthorizationDecision.DENY
        await manager.revoke(repo)
        assert name not in manager._active and second in manager._active
        scope = "evolution:isolated:" + rows[second_repo]["source_sha256"] + ":lookup_local"
        assert (await gateway.invoke(_request(second_cap, "lookup_local", scope))).decision is AuthorizationDecision.ALLOW
        assert providers[name].closed and not providers[second].closed
        await manager.close()
    asyncio.run(run())


def _install_inert_venv(runtime):
    executable = runtime / ".venv" / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"inert interpreter identity")
    (runtime / ".aura-isolated-env.json").write_text(json.dumps({
        "schema": "aura.windows-isolated-venv.v1",
        "dependency_sha256": "a" * 64,
    }))
    return executable


def test_live_signed_tree_rejects_changed_wheels_but_allows_external_state(tmp_path, monkeypatch):
    workspace, name, _ = _signed_fixture(tmp_path, monkeypatch)
    runtime = workspace.root / "runtime" / name
    wheel = _install_inert_venv(runtime)
    tree = runtime_fingerprint(workspace, name)
    state = local_mcp_state_root(workspace, name)
    scratch = workspace.root / "runtime-work" / name
    scratch.mkdir(parents=True)
    env = _scrubbed_windows_mcp_environment(scratch, state=state)
    assert env["PYTHONPYCACHEPREFIX"] == str(scratch.resolve() / "pycache")
    notes = state / ".projectmem"
    notes.mkdir()
    data = notes / "notes.sqlite"
    transport = SimpleNamespace(call_tool=AsyncMock(side_effect=lambda *_: data.write_bytes(b"persistent state")))
    failure = Mock()
    provider = DockerMCPProvider(
        transport, runtime=runtime, archive_sha256="", workspace=workspace,
        package=name, on_failure=failure, owner_authorized=lambda: True,
        attestation_expires_at=int(time.time()) + 600, signed_tree=tree,
    )
    asyncio.run(provider.call_tool("lookup_local"))
    assert local_mcp_state_root(workspace, name) == state
    assert data.read_bytes() == b"persistent state"
    assert runtime_fingerprint(workspace, name) == tree
    wheel.write_bytes(b"tampered executable")
    with pytest.raises(PermissionError, match="Runtime tree differs"):
        asyncio.run(provider.call_tool("lookup_local"))
    transport.call_tool.assert_awaited_once()
    failure.assert_called_once_with(name)


def test_unsigned_bytecode_is_not_accepted(tmp_path, monkeypatch):
    workspace, name, _ = _signed_fixture(tmp_path, monkeypatch)
    cache = workspace.root / "runtime" / name / "__pycache__"
    cache.mkdir()
    (cache / "server.cpython-313.pyc").write_bytes(b"not signed")
    with pytest.raises(PermissionError, match="unsigned bytecode"):
        runtime_fingerprint(workspace, name)


def test_authentic_expired_local_evidence_is_renewable_not_invalid_binding(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=kernel)
    grant = {**manager.delegation.verified_grant(), "allow_local_windows_process": True}
    signer = workspace._testing_attestor_signer
    runtime = workspace.root / "runtime" / name
    wheel = _install_inert_venv(runtime)
    tree = runtime_fingerprint(workspace, name)
    package = workspace.root / "verified" / name
    source = hashlib.sha256((package / "source.zip").read_bytes()).hexdigest()
    tool = FakeProvider().tools[0]
    binding = local_binding(repository=repo, source_sha256=source, tree_sha256=tree,
                            tool=tool, category="local_memory")
    now = int(time.time())
    claims = {
        "schema": LOCAL_SCHEMA, "source_sha256": source,
        "runtime_tree_sha256": tree, "binding_digest": binding,
        "policy_sha256": LOCAL_POLICY_SHA256, "tests_sha256": LOCAL_TESTS_SHA256,
        "owner_grant_sha256": hashlib.sha256(canonical(grant)).hexdigest(),
        "runner_id": grant["attestor_runner_id"],
        "issued_at": now - 601, "expires_at": now - 1,
        "job_object_kill_on_close": True, "outcome": "passed",
    }
    envelope = local_sign(signer, claims)
    args = dict(key=signer.public_key(), grant=grant, source_sha256=source,
                tree_sha256=tree, binding_digest=binding)
    with pytest.raises(PermissionError, match="Independent Windows attestation expired"):
        verify_local(envelope, **args)
    bad = {**envelope, "signature_b64": base64.b64encode(b"x" * 64).decode("ascii")}
    with pytest.raises(PermissionError, match="Unsigned or forged"):
        verify_local(bad, **args)
    wrong = local_sign(signer, {**claims, "owner_grant_sha256": "0" * 64})
    with pytest.raises(PermissionError, match="Owner and job observation binding"):
        verify_local(wrong, **args)
    (package / "independent-attestations.json").write_text(json.dumps({
        "schema": "aura.external-attested-tools.v1", "repository": repo,
        "execution_profile": "windows-job-stdio", "runtime_tree_sha256": tree,
        "tools": [{"name": tool.name, "input_schema": tool.input_schema, "attestation": envelope}],
    }))
    checks = dict(grant=grant, repository=repo, source=source, category="local_memory")
    _require_observed_environment(workspace, name, tree=tree, **checks)
    wheel.write_bytes(b"unauthorized dependency change")
    with pytest.raises(PermissionError, match="differs from signed provenance"):
        _require_observed_environment(workspace, name, tree=runtime_fingerprint(workspace, name), **checks)


def _registration_script():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "scripts" / "Register-AuraIndependentAttestor.ps1"


def _registration_precheck():
    """Extract the actual production preflight, not a duplicate command."""
    source = _registration_script().read_text(encoding="utf-8")
    start = source.index("$check = @'\n")
    end = source.index("\n$sha = ", start)
    return source[start:end]


def test_registration_precheck_uses_stdin_not_native_code_argument():
    import ast
    source = _registration_precheck()
    payload = source.split("@'\n", 1)[1].split("\n'@", 1)[0]
    ast.parse(payload)
    assert '$check | & $TrustedPython -I -B - $EvolutionRoot $PrivateKey' in source
    assert '-c $check' not in source
    assert 'if ($LASTEXITCODE -ne 0)' in source
    assert '_load_signer(Path(sys.argv[2]))' in payload
    assert 'grant["attestor_key_sha256"]' in payload


@pytest.mark.skipif(__import__("os").name != "nt", reason="Native Windows PowerShell 5.1 and NTFS ACL")
def test_registration_native_powershell_precheck_and_private_key_acl(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    import subprocess
    import sys
    from cryptography.hazmat.primitives import serialization
    from aura_core.evolution.windows_owner_storage import harden_private_acl, require_private_acl
    from test_windows_owner_acl import _add_untrusted_ace

    workspace, _, _ = _signed_fixture(tmp_path, monkeypatch)
    # The private attestor key is outside both the checkout and Owner storage.
    keys = workspace.root / "Independent Attestor Keys"
    keys.mkdir()
    harden_private_acl(keys)
    key_path = keys / "sandbox-attestor.pem"
    key_path.write_bytes(workspace._testing_attestor_signer.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    harden_private_acl(key_path)
    require_private_acl(keys)
    require_private_acl(key_path)

    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # Run exactly the production preflight with a real native interpreter.
    # No task is registered or user environment mutated on the shared runner.
    wrapper = tmp_path / "registration-preflight.ps1"
    wrapper.write_text(
        "param([string]$TrustedPython,[string]$TrustedWorkingDirectory,"
        "[string]$EvolutionRoot,[string]$PrivateKey)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Expected Windows PowerShell 5.1' }\n"
        + _registration_precheck() + "\nWrite-Output 'ATTESTOR_PREFLIGHT_PASS'\n",
        encoding="ascii",
    )

    def run():
        return subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(wrapper), sys.executable, str(tmp_path),
             str(workspace.root), str(key_path)],
            capture_output=True, text=True, timeout=180, check=False,
        )

    valid = run()
    assert valid.returncode == 0, valid.stderr[-1500:]
    assert "ATTESTOR_PREFLIGHT_PASS" in valid.stdout

    # A different real Ed25519 key must fail even with correct private ACLs.
    key_path.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    mismatch = run()
    assert mismatch.returncode != 0
    assert "Independent signer validation failed" in mismatch.stderr
    assert "Independent attestor identity or Owner grant invalid" in mismatch.stderr
    assert "ATTESTOR_PREFLIGHT_PASS" not in mismatch.stdout

    # Correct key with an unexpected ACE must also fail, not reach registration.
    key_path.write_bytes(workspace._testing_attestor_signer.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        _add_untrusted_ace(key_path)
        rejected = run()
        assert rejected.returncode != 0
        assert "NTFS ACL" in rejected.stderr
        assert "ATTESTOR_PREFLIGHT_PASS" not in rejected.stdout
    finally:
        harden_private_acl(key_path)


@pytest.mark.skipif(__import__("os").name != "nt", reason="Real Windows identity check")
def test_registration_rejects_core_identity_before_task_creation():
    import csv
    import os
    from pathlib import Path
    import subprocess
    import sys

    current = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        capture_output=True, text=True, timeout=15, check=True,
    )
    sid = next(csv.reader(current.stdout.splitlines()))[-1].strip()
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(_registration_script()), "-CoreIdentity", sid,
         "-TrustedPython", sys.executable,
         "-TrustedWorkingDirectory", str(_registration_script().parent)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "Attestor must be a separate non-SYSTEM Windows account" in result.stderr
    assert "Registered independent task:" not in result.stdout
