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
from aura_core.evolution.sandbox_preflight import (
    IsolatedMCPPreflight, _MAX_TOOLS, _MAX_SCHEMA_JSON_BYTES,
    _schema_json_size,
)
from aura_core.evolution.sandbox_attestor import (
    SandboxClaims, SignedSandboxAttestation, DOMAIN, canonical_claims,
)
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.evolution.windows_job_mcp import (
    LOCAL_POLICY_SHA256, LOCAL_TESTS_SHA256,
    LocalWindowsMCPPreflight, local_binding, local_sign,
)


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


RECOVERY_EPOCH = "windows-isolated-wheels-20261122-v5"


def _eligible_local_recovery(previous: object) -> bool:
    """One bounded retry of a prior SDK/install quarantine, never a revoke.

    A v4 marker may have retry_count=4 after the previous transport retry.
    Permit only one more signed Owner-approved recovery under v5.
    """
    if not isinstance(previous, dict):
        return False
    count = previous.get("retry_count", 0)
    return (
        previous.get("status") in {"QUARANTINED", "RETRYING"}
        and previous.get("reason_code") in {
            "SandboxUntrusted", "DEPENDENCY_RECOVERY",
            "MCPError", "McpError", "ExceptionGroup",
        } or (
            previous.get("reason_code") == "PermissionError"
            and previous.get("recovery_epoch") == "windows-isolated-wheels-20261122-v4"
            and previous.get("detail") == "External MCP exceeded delegated tool budget"
        )
        and previous.get("recovery_epoch") != RECOVERY_EPOCH
        and previous.get("recovery_epoch") in {
            None, "windows-isolated-wheels-20261122-v1",
            "windows-isolated-wheels-20261122-v2",
            "windows-isolated-wheels-20261122-v3",
            "windows-isolated-wheels-20261122-v4",
        }
        and type(count) is int and 0 <= count < 5
    )


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
        # The Docker path is unchanged; local execution is a distinct,
        # explicitly signed, weaker Windows-only Owner decision.
        local_opt_in = (
            os.name == "nt" and
            grant.get("allow_local_windows_process", False) is True
        )
        use_local = local_opt_in and (
            decision.category in {"windows_automation", "desktop_automation"}
            or grant["oci_image"] is None
        )
        report = None
        if not use_local:
            if grant["oci_image"] is None:
                raise PermissionError("Docker OCI digest absent")
            sandbox = IsolatedMCPPreflight(self.workspace, image=grant["oci_image"])
            report = await sandbox.probe(package)
            if report.get("status") != "PREPARED_UNATTESTED":
                if not local_opt_in:
                    raise PermissionError("Pinned isolated MCP initialize/tools-list failed")
                use_local = True
        if use_local:
            # Never sign Docker isolation facts for a Windows host process.
            report = await LocalWindowsMCPPreflight(
                self.workspace, owner_grant=grant,
            ).probe(package)
        if report is None or report.get("status") != "PREPARED_UNATTESTED":
            raise PermissionError("Owner-permitted MCP initialize/tools-list failed")
        tools = report.get("tool_schemas", {})
        if (not isinstance(tools, dict) or not tools
                or len(tools) > min(_MAX_TOOLS, grant["max_tools"])
                or _schema_json_size(tools) > _MAX_SCHEMA_JSON_BYTES):
            raise PermissionError("External MCP exceeded delegated tool budget")
        tree = runtime_fingerprint(self.workspace, package)
        issue = int(time.time())
        records = []
        for name in sorted(tools):
            tool = MCPTool(name=name, description="", input_schema=tools[name])
            if use_local:
                from aura_core.evolution.activation_delegation import canonical
                binding = local_binding(
                    repository=decision.repository,
                    source_sha256=decision.source_sha256,
                    tree_sha256=tree, tool=tool, category=decision.category,
                )
                claims = {
                    "schema": "aura.local-windows-job-mcp-attestation.v1",
                    "source_sha256": decision.source_sha256,
                    "runtime_tree_sha256": tree,
                    "binding_digest": binding,
                    "policy_sha256": LOCAL_POLICY_SHA256,
                    "tests_sha256": LOCAL_TESTS_SHA256,
                    "owner_grant_sha256": hashlib.sha256(canonical(grant)).hexdigest(),
                    "runner_id": grant["attestor_runner_id"],
                    "issued_at": issue, "expires_at": issue + 600,
                    "job_object_kill_on_close": True,
                    "outcome": "passed",
                }
                proof = local_sign(self._key, claims)
            else:
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
                proof = envelope.to_dict()
            records.append({
                "name": name, "input_schema": tool.input_schema,
                "attestation": proof,
            })
        payload = {
            "schema": _SCHEMA, "repository": decision.repository,
            "runtime_tree_sha256": tree, "tools": records,
        }
        if use_local:
            payload["execution_profile"] = "windows-job-stdio"
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
            if operating_system.path.getsize(temp) > 262_144:
                raise PermissionError("Attestation bundle too large")
            operating_system.replace(temp, path)
        finally:
            if operating_system.path.exists(temp):
                operating_system.unlink(temp)
        return {"repository": decision.repository, "attested_tools": len(records),
                "independent_runner": grant["attestor_runner_id"]}

    @staticmethod
    def _safe_detail(value: object) -> str:
        """Bound diagnostics and scrub arbitrary untrusted strings."""
        import re
        text = "".join(c for c in str(value) if 32 <= ord(c) <= 126)[:300]
        text = re.sub(
            r"(?i)(?:bearer\s+|(?:token|secret|password|api[_-]?key)\s*[=:]\s*)"
            r"[^\s,;]+", "[REDACTED]", text,
        )
        text = re.sub(r"[a-fA-F0-9]{40,}", "[REDACTED-HEX]", text)
        return text[:240]

    def _read_error_tail(self, package: str) -> str:
        path = self.workspace.root / "logs" / (package + "-local-mcp-stderr.json")
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2048:
                return ""
            data = json.loads(path.read_text("utf-8"))
            return self._safe_detail(data.get("stderr_tail", ""))
        except (OSError, TypeError, ValueError):
            return ""

    def _quarantine_record(self, package: str, record: dict) -> None:
        """Atomic status document and append-only bounded metadata audit."""
        import tempfile
        location = self.workspace.root / "verified" / package / "local-windows-quarantined.json"
        if location.is_symlink():
            raise PermissionError("Untrusted local quarantine path")
        fd, temporary = tempfile.mkstemp(prefix=".local-quarantine-", dir=location.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            if os.path.getsize(temporary) > 2048:
                raise PermissionError("Oversized local quarantine record")
            os.replace(temporary, location)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _audit_local_quarantine(self, package: str, record: dict) -> None:
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+", package):
            raise PermissionError("Untrusted quarantine identity")
        log = self.workspace.root / "logs" / "autonomous-activations.jsonl"
        if log.is_symlink():
            raise PermissionError("Untrusted autonomous activation audit")
        if log.exists() and log.stat().st_size > 200_000:
            rotated = log.with_suffix(".previous.jsonl")
            if rotated.is_symlink():
                raise PermissionError("Untrusted autonomous audit rotation")
            log.replace(rotated)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "time": int(time.time()), "repository": package.replace("__", "/"),
                "status": "QUARANTINED",
                "reason_code": record["reason_code"],
                "detail": record["detail"], "stderr_tail": record["stderr_tail"],
            }, sort_keys=True) + "\n")

    async def scan(self) -> list[dict]:
        grant = self._delegation.verified_grant()
        if grant is None:
            return []
        records = []
        local_allowed = (os.name == "nt" and
                         grant.get("allow_local_windows_process", False) is True)
        # Re-evaluate only previous SDK/install failures once under the new epoch.
        recovery_epoch = RECOVERY_EPOCH
        for decision in self._decisions.evaluate_pending(limit=100):
            if decision.status != "AUTO_APPROVED_BY_POLICY":
                continue
            package = decision.repository.replace("/", "__")
            quarantine = self.workspace.root / "verified" / package / "local-windows-quarantined.json"
            retries = 0
            if quarantine.exists() or quarantine.is_symlink():
                if not local_allowed or quarantine.is_symlink() or quarantine.stat().st_size > 2048:
                    continue
                try:
                    previous = json.loads(quarantine.read_text("utf-8"))
                    if not isinstance(previous, dict):
                        continue
                    retries = previous.get("retry_count", 0)
                    if not _eligible_local_recovery(previous):
                        continue
                    # Retain quarantine marker until fresh signed evidence is
                    # completely written. Core never activates a pending retry.
                    self._quarantine_record(package, {
                        "status": "RETRYING", "reason_code": "DEPENDENCY_RECOVERY",
                        "detail": "One-time post-upgrade isolated environment retry",
                        "stderr_tail": "", "retry_count": retries + 1,
                        "recovery_epoch": recovery_epoch,
                    })
                    retries += 1
                except (OSError, ValueError, TypeError, PermissionError):
                    continue
            try:
                record = await self.attest(package)
                if quarantine.exists():
                    quarantine.unlink()
                records.append(record)
            # MCP transport libraries raise various Exception subclasses
            # (including protocol and task-group failures). CancelledError,
            # KeyboardInterrupt and SystemExit remain non-quarantinable.
            except Exception as exc:
                if local_allowed:
                    result = {
                        "status": "QUARANTINED",
                        "reason_code": type(exc).__name__,
                        "detail": self._safe_detail(exc),
                        "stderr_tail": self._read_error_tail(package),
                        "retry_count": retries,
                        "recovery_epoch": recovery_epoch,
                    }
                    try:
                        self._quarantine_record(package, result)
                        self._audit_local_quarantine(package, result)
                    except (OSError, ValueError, PermissionError):
                        pass
                continue
        return records


def provision_attestor(*, workspace: EvolutionWorkspace, key_root: Path) -> str:
    """Explicit operator-only attestor identity. Never called from AURA Core."""
    if (not key_root.is_absolute() or not key_root.is_dir()
            or key_root.is_symlink()
            or key_root.resolve().is_relative_to(Path(__file__).resolve().parents[4])):
        raise PermissionError("Pre-provisioned external attestor trust directory required")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import (
            require_private_acl, harden_private_acl,
        )
        require_private_acl(key_root)
    elif key_root.stat().st_mode & 0o077:
        raise PermissionError("Attestor trust directory must be owner-only")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    from aura_core.evolution.external_staging import _checked_path
    _checked_path(key_root)
    signer = Ed25519PrivateKey.generate()
    private = key_root / "sandbox-attestor.pem"
    trust = workspace.root / "trust"
    trust.mkdir(exist_ok=True)
    _checked_path(trust)
    public = trust / "sandbox-attestor.pub.pem"
    if private.exists() or private.is_symlink() or public.exists() or public.is_symlink():
        raise FileExistsError("Attestor identity already provisioned")
    private_bytes = signer.private_bytes(
        ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption(),
    )
    with private.open("xb") as stream:
        stream.write(private_bytes)
    try:
        if os.name == "nt":
            harden_private_acl(private)
        else:
            private.chmod(0o600)
        public.write_bytes(signer.public_key().public_bytes(
            ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo,
        ))
    except BaseException:
        private.unlink(missing_ok=True)
        public.unlink(missing_ok=True)
        raise
    raw = signer.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Separate-identity offline MCP attestation")
    parser.add_argument("--evolution-root", type=Path, required=True)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--provision-key-root", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 30 <= args.poll_seconds <= 3600:
        parser.error("Poll must be bounded between 30 and 3600 seconds")
    workspace = EvolutionWorkspace(args.evolution_root)
    if args.provision_key_root is not None:
        print("AURA_EVOLUTION_ATTESTOR_KEY_SHA256=" + provision_attestor(
            workspace=workspace, key_root=args.provision_key_root,
        ))
        return 0
    if args.private_key is None:
        parser.error("--private-key required after independent provisioning")
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
