"""Independent operator attestor: observe isolated MCP health, then Ed25519-sign.

MUST be started manually or as a separate restricted OS service, *never*
by AURA Core. The key file is private to this identity. The process has
Docker access, but does not grant AURA runtime execution or sign Owner consent.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
from aura_core.evolution.activation_runtime import (
    _SCHEMA, runtime_fingerprint, tool_binding_digest,
)
from aura_core.evolution.decision_engine import EvolutionDecisionEngine
from aura_core.evolution.external_staging import EvolutionWorkspace
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight
from aura_core.evolution.sandbox_attestor import (
    SandboxClaims, SignedSandboxAttestation, DOMAIN, canonical_claims,
)
from aura_core.mcp.mcp_provider import MCPTool


def _load_signer(path: Path) -> Ed25519PrivateKey:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.stat().st_size > 16_384):
        raise PermissionError("Independent attestor key must be pre-provisioned")
    checkout = Path(__file__).resolve().parents[4]
    if path.resolve().is_relative_to(checkout):
        raise PermissionError("Independent attestor key cannot live inside JAS checkout")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        require_private_acl(path)
    elif (path.stat().st_mode & 0o077):
        raise PermissionError("Attestor private key must have 0600 permissions")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Attestor signer must be Ed25519")
    return key


class IndependentMCPAttestorWorker:
    def __init__(self, *, workspace: EvolutionWorkspace, key: Ed25519PrivateKey):
        self.workspace = workspace
        self._key = key
        self._decisions = EvolutionDecisionEngine(workspace)
        self._delegation = ActivationDelegationVerifier(workspace)

    async def attest(self, package: str) -> dict:
        grant = self._delegation.verified_grant()
        if grant is None:
            raise PermissionError("Valid, pinned and explicit Owner activation delegation required")
        decision = self._decisions.evaluate(package)
        if decision.status != "AUTO_APPROVED_BY_POLICY":
            raise PermissionError("Package is not delegated by Owner policy")
        raw_pub = self._key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        import hashlib
        if hashlib.sha256(raw_pub).hexdigest() != grant["attestor_key_sha256"]:
            raise PermissionError("Signing key does not match independently pinned attestor")
        sandbox = IsolatedMCPPreflight(self.workspace, image=grant["oci_image"])
        report = await sandbox.probe(package)
        if report.get("status") != "PREPARED_UNATTESTED":
            raise PermissionError("Pinned isolated MCP initialize/tools-list failed")
        tools = report.get("tool_schemas", {})
        if (not isinstance(tools, dict) or not tools
                or len(tools) > grant["max_tools"]):
            raise PermissionError("External MCP exceeded delegated tool budget")
        tree = runtime_fingerprint(self.workspace, package)
        issue = int(time.time())
        records = []
        for name in sorted(tools):
            tool = MCPTool(name=name, description="", input_schema=tools[name])
            binding = tool_binding_digest(
                repository=decision.repository, source_sha256=decision.source_sha256,
                tree_sha256=tree, image=grant["oci_image"],
                tool=tool, category=decision.category,
            )
            claims = SandboxClaims(
                source_sha256=decision.source_sha256,
                tests_sha256=grant["tests_sha256"],
                image_digest=grant["oci_image"].split("@", 1)[1],
                policy_sha256=grant["policy_sha256"],
                binding_digest=binding, run_id=secrets.token_hex(16),
                runner_id=grant["attestor_runner_id"],
                issued_at=issue, expires_at=issue + 600,
                exit_code=0, outcome="passed",
                network_disabled=True, rootfs_readonly=True,
            )
            signature = self._key.sign(DOMAIN + canonical_claims(claims))
            envelope = SignedSandboxAttestation(
                key_id="operator_attestor", claims=claims,
                signature_b64=base64.b64encode(signature).decode("ascii"),
            )
            records.append({
                "name": name, "input_schema": tool.input_schema,
                "attestation": envelope.to_dict(),
            })
        payload = {
            "schema": _SCHEMA, "repository": decision.repository,
            "runtime_tree_sha256": tree, "tools": records,
        }
        path = self.workspace.root / "verified" / package / "independent-attestations.json"
        if path.is_symlink():
            raise PermissionError("Attestation output cannot follow symlinks")
        # Replace only this operator-generated bounded evidence; no source
        # archive or approval file is ever modified.
        import tempfile
        import os as operating_system
        handle, temp = tempfile.mkstemp(prefix=".attested-", dir=path.parent)
        try:
            with operating_system.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                operating_system.fsync(stream.fileno())
            if operating_system.path.getsize(temp) > 100_000:
                raise PermissionError("Attestation bundle too large")
            operating_system.replace(temp, path)
        finally:
            if operating_system.path.exists(temp):
                operating_system.unlink(temp)
        return {"repository": decision.repository, "attested_tools": len(records),
                "independent_runner": grant["attestor_runner_id"]}

    async def scan(self) -> list[dict]:
        grant = self._delegation.verified_grant()
        if grant is None:
            return []
        records = []
        for decision in self._decisions.evaluate_pending(limit=100):
            if decision.status != "AUTO_APPROVED_BY_POLICY":
                continue
            try:
                records.append(await self.attest(decision.repository.replace("/", "__")))
            except (ValueError, PermissionError, RuntimeError, OSError, TimeoutError):
                continue
        return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Separate-identity offline MCP attestation")
    parser.add_argument("--evolution-root", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 30 <= args.poll_seconds <= 3600:
        parser.error("Poll must be bounded between 30 and 3600 seconds")
    workspace = EvolutionWorkspace(args.evolution_root)
    worker = IndependentMCPAttestorWorker(
        workspace=workspace, key=_load_signer(args.private_key),
    )
    while True:
        result = asyncio.run(worker.scan())
        print(json.dumps({"attested_packages": len(result)}, sort_keys=True), flush=True)
        if not args.watch:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
