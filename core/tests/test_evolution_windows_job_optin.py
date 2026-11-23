"""Regression: the Windows Job profile is a distinct, opt-in weaker trust mode."""
from __future__ import annotations

import hashlib
from pathlib import Path
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution.activation_delegation import (
    SANDBOX_POLICY_SHA256, SANDBOX_TESTS_SHA256, canonical, validated_claims,
)
from aura_core.evolution.owner_cli import make_activation_delegation
from aura_core.evolution.sandbox_preflight import SandboxUntrusted
from aura_core.evolution.windows_job_mcp import (
    LOCAL_POLICY_SHA256, LOCAL_SCHEMA, LOCAL_TESTS_SHA256,
    bridge_parameters, local_sign, static_python_entry, verify_local,
)


def _grant(*, allow: bool, image=None):
    signer = Ed25519PrivateKey.generate()
    claims = make_activation_delegation(
        signer, categories=("windows_automation", "filesystem", "browser"),
        image=image, policy_sha256=SANDBOX_POLICY_SHA256,
        tests_sha256=SANDBOX_TESTS_SHA256, attestor_key_sha256="a" * 64,
        attestor_runner_id="test_attestor_runner",
        days=365, max_tools=8, min_score=70,
        allow_local_windows_process=allow,
    )
    return signer, claims


def test_local_windows_is_default_deny_and_cannot_replace_docker_pin():
    _, doc = _grant(allow=False, image="example/python@sha256:" + "a" * 64)
    assert validated_claims(doc["claims"]).get("allow_local_windows_process") is False
    assert doc["claims"]["scope"] == "offline-container-stdio"
    with pytest.raises(PermissionError):
        _grant(allow=False, image=None)


def test_signed_owner_local_optin_can_be_verified_without_forged_oci():
    signer, doc = _grant(allow=True)
    claims = validated_claims(doc["claims"])
    assert claims["allow_local_windows_process"] is True
    assert claims["scope"] == "offline-container-stdio+windows-job-stdio"
    assert claims["oci_image"] is None
    signer.public_key().verify(
        __import__("base64").urlsafe_b64decode(doc["signature_b64"] + "=="),
        canonical(claims),
    )
    altered = dict(claims, allow_local_windows_process=False)
    with pytest.raises(PermissionError):
        validated_claims(altered)


def test_windows_attestation_has_distinct_domain_and_fails_on_tampering():
    from aura_core.evolution.windows_job_mcp import LOCAL_DOMAIN
    attestor = Ed25519PrivateKey.generate()
    _, doc = _grant(allow=True)
    owner = doc["claims"]
    now = int(time.time())
    binding, source, tree = "b" * 64, "c" * 64, "d" * 64
    claims = {
        "schema": LOCAL_SCHEMA, "source_sha256": source,
        "runtime_tree_sha256": tree, "binding_digest": binding,
        "policy_sha256": LOCAL_POLICY_SHA256, "tests_sha256": LOCAL_TESTS_SHA256,
        "owner_grant_sha256": hashlib.sha256(canonical(owner)).hexdigest(),
        "runner_id": owner["attestor_runner_id"], "issued_at": now,
        "expires_at": now + 60, "job_object_kill_on_close": True,
        "outcome": "passed",
    }
    evidence = local_sign(attestor, claims)
    assert verify_local(
        evidence, key=attestor.public_key(), grant=owner,
        source_sha256=source, tree_sha256=tree, binding_digest=binding,
    ) == now + 60
    assert LOCAL_DOMAIN != b"AURA:SANDBOX-ATTESTATION:v1\n"
    for mutation in (
        lambda d: d["claims"].update({"job_object_kill_on_close": False}),
        lambda d: d["claims"].update({"owner_grant_sha256": "0" * 64}),
        lambda d: d["claims"].update({"expires_at": now - 1}),
    ):
        bad = __import__("copy").deepcopy(evidence)
        mutation(bad)
        with pytest.raises(PermissionError):
            verify_local(
                bad, key=attestor.public_key(), grant=owner,
                source_sha256=source, tree_sha256=tree, binding_digest=binding,
            )


def test_static_python_review_rejects_non_mcp_and_never_executes(tmp_path):
    flag = tmp_path / "executed"
    source = (
        "from pathlib import Path\n"
        f"Path({str(flag)!r}).write_text('bad')\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "mcp = FastMCP('example')\n"
        "@mcp.tool()\n"
        "def hello() -> str: return 'hi'\n"
    ).encode()
    assert static_python_entry({"server.py": source}, "server.py") == "server.py"
    v2_source = source.replace(
        b"from mcp.server.fastmcp import FastMCP",
        b"from mcp.server.mcpserver import MCPServer",
    ).replace(b"FastMCP('example')", b"MCPServer('example')")
    assert static_python_entry({"server.py": v2_source}, "server.py") == "server.py"
    assert not flag.exists()
    with pytest.raises(SandboxUntrusted):
        static_python_entry({"server.py": b"def hello(): return 1"}, "server.py")


def test_bridge_refuses_non_windows_hosts(tmp_path):
    import os
    if os.name == "nt":
        pytest.skip("Windows subprocess integration requires Job Object live runner")
    with pytest.raises(PermissionError):
        bridge_parameters(tmp_path, "server.py")


def test_scrubbed_windows_environment_can_import_trusted_mcp_sdk(tmp_path):
    import os
    import subprocess
    import sys
    if os.name != "nt":
        pytest.skip("Only Windows has a Job Object executable environment")
    from aura_core.evolution.windows_job_mcp import _scrubbed_windows_mcp_environment
    safe = _scrubbed_windows_mcp_environment(tmp_path)
    assert not any(key.upper().startswith("AURA_") for key in safe)
    assert "OPENAI_API_KEY" not in safe
    assert Path(safe["USERPROFILE"]).resolve() == tmp_path.resolve()
    check = subprocess.run(
        [sys.executable, "-B", "-s", "-c",
         "from mcp.server.mcpserver import MCPServer; print('mcp-sdk-ready')"],
        cwd=tmp_path, env=safe, capture_output=True, text=True, timeout=25,
    )
    assert check.returncode == 0, check.stderr[-1200:]
    assert "mcp-sdk-ready" in check.stdout


def test_windows_job_object_real_mcp_initialize_and_tools_list(tmp_path):
    import asyncio
    import os
    if os.name != "nt":
        pytest.skip("Only a real Windows runner can inspect Job Object behavior")
    from aura_core.mcp.connection import MCPConnection
    from aura_core.evolution.external_staging import EvolutionWorkspace

    # The Windows Job bridge intentionally rejects arbitrary directories:
    # production only launches <AURA_EVOLUTION_ROOT>/runtime/<owner>__<repo>.
    # Exercise the real Job Object handshake in that exact external layout,
    # not from pytest's bare tmp_path (which would be denied before CreateProcess).
    workspace = EvolutionWorkspace(tmp_path / "external-evolution")
    runtime = workspace.root / "runtime" / "test__job-handshake"
    runtime.mkdir(parents=True)
    server = runtime / "server.py"
    server.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "mcp = MCPServer('job-sandbox-test')\n"
        "@mcp.tool()\n"
        "def hello() -> str: return 'hello'\n"
        "if __name__ == '__main__': mcp.run(transport='stdio')\n",
        encoding="utf-8",
    )

    async def check():
        connection = MCPConnection()
        try:
            await asyncio.wait_for(
                connection.connect_stdio(bridge_parameters(runtime, "server.py")), timeout=20
            )
            response = await asyncio.wait_for(connection.list_tools(), timeout=5)
            tools = response.tools if hasattr(response, "tools") else response
            assert any(tool.name == "hello" for tool in tools)
        finally:
            await connection.close()

    asyncio.run(check())
    assert server.is_file()  # Job never overwrites the reviewed source tree.
    scratch_parent = workspace.root / "runtime-work" / "test__job-handshake"
    assert scratch_parent.is_dir()
    assert not list(scratch_parent.iterdir())  # Disposable child state cleaned up.


def test_setup_keeps_real_passkey_and_does_not_bypass_owner_security():
    root = Path(__file__).resolve().parents[2]
    setup = (root / "scripts" / "setup-autonomous-aura.ps1").read_text("utf-8")
    assert "provision_windows_owner.ps1" in setup
    assert "enroll_local_owner.py" in setup
    assert "--allow-local-windows-process" in setup
    assert "activation_delegation --verify" in setup
    assert "owner-passkey.json" in setup
