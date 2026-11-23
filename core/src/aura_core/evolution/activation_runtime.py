"""Delegated external MCP activation through independent attestations and MCPGateway.

NO untrusted package can issue an Owner signature, attestation, or permission.
Default off. Runtime code executes only in an immutable digest-pinned,
network-denied Docker sandbox with source mounted read-only. An independent
operator attestor signs each exact source/tool/schema/runtime-tree binding.
The old TrustedPromotionBridge remains sealed for preinstalled bindings.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Awaitable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from mcp.client.stdio import StdioServerParameters

from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
from aura_core.evolution.decision_engine import EvolutionDecisionEngine
from aura_core.evolution.external_staging import (
    EvolutionWorkspace, _checked_path, _validated_files,
)
from aura_core.evolution.sandbox_preflight import (
    IsolatedMCPPreflight, choose_python_entrypoint,
    _MAX_TOOLS, _MAX_SCHEMA_JSON_BYTES, _schema_json_size,
)
from aura_core.evolution.windows_job_mcp import (
    bridge_parameters, local_binding, verify_local,
)
from aura_core.evolution.sandbox_attestor import (
    IndependentAttestationVerifier, SignedSandboxAttestation,
)
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, ProviderType,
)
from aura_core.kernel.events import KernelEvent
from aura_core.kernel.permissions import (
    PermissionPolicy, AuthorizationLevel, AuthorizationDecision,
)
from aura_core.kernel.services import (
    ServiceDefinition, ServiceCategory, ServiceState,
)
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider, MCPTool
from aura_core.mcp.provider import ProviderDefinition
from aura_core.mcp.tool_registry import MCPToolRegistry

_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOOL = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SCHEMA = "aura.external-attested-tools.v1"
_TOOL_LIMIT_BYTES = 262_144
_CATEGORY = {
    "desktop_automation": CapabilityCategory.AUTOMATION,
    "code_analysis": CapabilityCategory.CODING,
    "local_memory": CapabilityCategory.MEMORY,
    "web_research": CapabilityCategory.RESEARCH,
    "developer_tools": CapabilityCategory.CODING,
    "windows_automation": CapabilityCategory.AUTOMATION,
    "filesystem": CapabilityCategory.STORAGE,
    "research": CapabilityCategory.RESEARCH,
    "browser": CapabilityCategory.BROWSER,
}


def canonical_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                      separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()


def runtime_fingerprint(workspace: EvolutionWorkspace, name: str) -> str:
    """Reject altered, added, symlinked or missing source before every use."""
    verified = workspace.root / "verified" / name
    runtime = workspace.root / "runtime" / name
    if not runtime.exists():
        raise PermissionError("Sandbox runtime not prepared")
    if (not runtime.is_dir() or runtime.is_symlink()
            or not verified.is_dir() or verified.is_symlink()):
        raise PermissionError("Unsafe independently prepared runtime")
    _checked_path(runtime)
    with (verified / "source.zip").open("rb") as stream:
        files, _entry, _skipped = _validated_files(stream)
    # Docker-only packages retain the original exact-source contract.
    # An explicitly installed local .venv is hashed *into* its independently
    # signed runtime identity; an added/modified wheel invalidates evidence.
    venv = runtime / ".venv"
    local_env = venv.exists()
    marker_name = ".aura-isolated-env.json"
    if local_env:
        if not venv.is_dir() or venv.is_symlink() or not (runtime / marker_name).is_file():
            raise PermissionError("Untrusted isolated dependency environment")
        if not (venv / "Scripts" / "python.exe").is_file() and os.name == "nt":
            raise PermissionError("Isolated runtime interpreter missing")
    elif (runtime / marker_name).exists():
        raise PermissionError("Isolated dependency marker without environment")
    allowed = set(files) | {".aura-untrusted-review.json"}
    if local_env:
        allowed.add(marker_name)
    seen: set[str] = set()
    environment_files: list[tuple[str, str]] = []
    environment_bytes = 0
    for path in runtime.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise PermissionError("Unsafe runtime symlink/junction")
        if path.is_file():
            rel = path.relative_to(runtime).as_posix()
            if local_env and rel.startswith(".venv/"):
                environment_bytes += path.stat().st_size
                if environment_bytes > 512 * 1024 * 1024 or len(environment_files) >= 25_000:
                    raise PermissionError("Isolated dependency footprint exceeds trusted budget")
                digest = hashlib.sha256()
                with path.open("rb") as file:
                    while block := file.read(1024 * 1024):
                        digest.update(block)
                environment_files.append((rel, digest.hexdigest()))
                continue
            if rel not in allowed:
                raise PermissionError("Unexpected runtime executable or data")
            seen.add(rel)
        if len(seen) > len(allowed) + 1:
            raise PermissionError("Untrusted additional runtime files")
    if set(files) - seen:
        raise PermissionError("Prepared runtime missing source files")
    manifest = runtime / ".aura-untrusted-review.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 4096:
        raise PermissionError("Prepared runtime marker absent")
    data = json.loads(manifest.read_text("utf-8"))
    hasher = hashlib.sha256()
    with (verified / "source.zip").open("rb") as archive_stream:
        while chunk := archive_stream.read(1024 * 1024):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if data.get("source_sha256") != digest or data.get("activation_performed") is not False:
        raise PermissionError("Runtime source marker changed")
    lines = []
    for rel in sorted(files):
        actual = (runtime / rel).read_bytes()
        if actual != files[rel]:
            raise PermissionError("Prepared runtime source changed")
        lines.append(rel + "\t" + hashlib.sha256(actual).hexdigest() + "\n")
    if local_env:
        environment_marker = runtime / marker_name
        if environment_marker.is_symlink() or environment_marker.stat().st_size > 2048:
            raise PermissionError("Invalid isolated environment metadata")
        metadata = json.loads(environment_marker.read_text("utf-8"))
        if (metadata.get("schema") != "aura.windows-isolated-venv.v1"
                or not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("dependency_sha256")))):
            raise PermissionError("Untrusted isolated dependency lock")
        lines.append(marker_name + "\t" +
                     hashlib.sha256(environment_marker.read_bytes()).hexdigest() + "\n")
        for rel, digest in sorted(environment_files):
            lines.append(rel + "\t" + digest + "\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def expired_attestation_evidence(
    workspace: EvolutionWorkspace, name: str, *, grant: dict,
    now: int | None = None,
) -> bool:
    """Recognize *signed* expired Windows evidence solely for fresh re-attestation.

    This never authorizes an expired tool. A valid, current Owner grant and
    pinned Ed25519 attestor must corroborate the old exact-source observation.
    """
    import base64
    from cryptography.exceptions import InvalidSignature
    from aura_core.evolution.activation_delegation import canonical
    from aura_core.evolution.windows_job_mcp import (
        LOCAL_DOMAIN, LOCAL_SCHEMA, LOCAL_POLICY_SHA256, LOCAL_TESTS_SHA256,
    )

    path = workspace.root / "verified" / name / "independent-attestations.json"
    keyfile = workspace.root / "trust" / "sandbox-attestor.pub.pem"
    source = workspace.root / "verified" / name / "source.zip"
    try:
        if (not isinstance(grant, dict)
                or grant.get("allow_local_windows_process") is not True
                or path.is_symlink() or not path.is_file()
                or path.stat().st_size > _TOOL_LIMIT_BYTES
                or keyfile.is_symlink() or not keyfile.is_file()
                or keyfile.stat().st_size > 512
                or source.is_symlink() or not source.is_file()):
            return False
        key = serialization.load_pem_public_key(keyfile.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            return False
        raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if hashlib.sha256(raw).hexdigest() != grant.get("attestor_key_sha256"):
            return False
        owner_hash = hashlib.sha256(canonical(grant)).hexdigest()
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        bundle = json.loads(path.read_text("utf-8"))
        if (not isinstance(bundle, dict) or bundle.get("schema") != _SCHEMA
                or bundle.get("repository") != name.replace("__", "/")
                or bundle.get("execution_profile") != "windows-job-stdio"
                or not _SHA.fullmatch(str(bundle.get("runtime_tree_sha256", "")))
                or not isinstance(bundle.get("tools"), list)
                or not 1 <= len(bundle["tools"]) <= 64):
            return False
        current = int(time.time()) if now is None else now
        for row in bundle["tools"]:
            if not isinstance(row, dict) or not isinstance(row.get("attestation"), dict):
                return False
            evidence = row["attestation"]
            claims = evidence.get("claims")
            if (evidence.get("schema") != LOCAL_SCHEMA
                    or evidence.get("key_id") != "operator_attestor"
                    or not isinstance(claims, dict)
                    or claims.get("schema") != LOCAL_SCHEMA
                    or claims.get("owner_grant_sha256") != owner_hash
                    or claims.get("source_sha256") != source_hash
                    or claims.get("runtime_tree_sha256") != bundle["runtime_tree_sha256"]
                    or claims.get("policy_sha256") != LOCAL_POLICY_SHA256
                    or claims.get("tests_sha256") != LOCAL_TESTS_SHA256
                    or type(claims.get("issued_at")) is not int
                    or type(claims.get("expires_at")) is not int
                    or not 0 < claims["expires_at"] - claims["issued_at"] <= 600
                    or claims["expires_at"] > current):
                return False
            signature = base64.b64decode(evidence["signature_b64"], validate=True)
            if len(signature) != 64:
                return False
            payload = json.dumps(
                claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("ascii")
            key.verify(signature, LOCAL_DOMAIN + payload)
        return True
    except (OSError, ValueError, TypeError, PermissionError, KeyError,
            InvalidSignature, UnicodeError):
        return False


def tool_binding_digest(*, repository: str, source_sha256: str, tree_sha256: str,
                        image: str, tool: MCPTool, category: str) -> str:
    if (not _TOOL.fullmatch(tool.name) or not isinstance(tool.input_schema, dict)
            or not _SHA.fullmatch(tree_sha256)):
        raise PermissionError("Unsupported MCP tool or runtime identity")
    return canonical_hash({
        "domain": "AURA:EXTERNAL-MCP-BINDING:v1",
        "repository": repository, "source_sha256": source_sha256,
        "runtime_tree_sha256": tree_sha256,
        "image": image, "category": category, "tool": tool.name,
        "input_schema_sha256": canonical_hash(tool.input_schema),
        "risk": "low",
        "scope": "evolution:isolated:" + source_sha256 + ":" + tool.name,
    })


class DockerMCPProvider(MCPProvider):
    """Governed external MCP connection, checked on every tool invocation."""

    def __init__(self, connection: MCPConnection, *, runtime: Path,
                 archive_sha256: str, workspace: EvolutionWorkspace,
                 package: str, on_failure: Callable[[str], None],
                 owner_authorized: Callable[[], bool],
                 attestation_expires_at: int):
        super().__init__(connection)
        self.runtime = runtime
        self.archive_sha256 = archive_sha256
        self.workspace = workspace
        self.package = package
        self._on_failure = on_failure
        self._owner_authorized = owner_authorized
        self._expires = attestation_expires_at
        self._healthy = True

    async def list_tools(self):
        if (not self._healthy or not self._owner_authorized()
                or time.time() >= self._expires):
            self._healthy = False
            self._on_failure(self.package)
            raise PermissionError("Quarantined, expired or revoked external provider")
        try:
            return await super().list_tools()
        except Exception:
            self._healthy = False
            self._on_failure(self.package)
            raise

    async def call_tool(self, name, arguments=None):
        if (not self._healthy or not self._owner_authorized()
                or time.time() >= self._expires):
            self._healthy = False
            self._on_failure(self.package)
            raise PermissionError("Quarantined, expired or revoked external provider")
        try:
            # Prevent host-side file mutation after signed sandbox evidence.
            runtime_fingerprint(self.workspace, self.package)
            return await super().call_tool(name, arguments)
        except Exception:
            self._healthy = False
            self._on_failure(self.package)
            raise


@dataclass
class _Live:
    provider: Any
    provider_id: str
    service_id: str
    capabilities: tuple[str, ...]
    policies: tuple[str, ...]
    category: str
    attestation_expires_at: int


class DelegatedMCPActivationManager:
    """Fail-closed Docker activation plus explicitly signed Windows Job opt-in."""

    def __init__(self, *, workspace: EvolutionWorkspace, kernel,
                 provider_factory=None):
        self.workspace = workspace
        self.kernel = kernel
        self.delegation = ActivationDelegationVerifier(workspace)
        self.decisions = EvolutionDecisionEngine(workspace)
        self.tools = MCPToolRegistry(event_bus=kernel.event_bus)
        self._active: dict[str, _Live] = {}
        self._lock = asyncio.Lock()
        self._factory = provider_factory
        self._inventory = workspace.active
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def _load_inventory(self) -> dict:
        if (self._inventory.is_symlink() or not self._inventory.is_file()
                or self._inventory.stat().st_size > 200_000):
            raise PermissionError("Active inventory must be a bounded external file")
        data = json.loads(self._inventory.read_text("utf-8"))
        if (not isinstance(data, dict)
                or data.get("schema") != "aura.external-capabilities.v1"
                or not isinstance(data.get("active"), list)
                or len(data["active"]) > self.workspace.max_items):
            raise PermissionError("Invalid active capability inventory")
        return data

    @staticmethod
    def _reason_detail(value: object) -> str:
        """Small privacy-safe diagnostic; never store raw untrusted stderr.

        Windows errors may embed absolute Owner paths; credentials and control
        sequences are redacted before the bounded audit / inventory write.
        """
        text = "".join(char if char.isprintable() else " " for char in str(value))
        text = re.sub(r"(?i)\b(?:[a-z]:\\\\|[a-z]:\\|\\\\\\\\)[^\s;,]+", "[path]", text)
        text = re.sub(r"(?i)\b(token|secret|password|api[_-]?key)\s*[:=]\s*[^\s;,]+",
                      r"\1=[redacted]", text)
        return " ".join(text.split())[:160]

    def _persist(self, repository: str, status: str, **fields):
        original = self._load_inventory()
        if "reason_detail" in fields:
            fields["reason_detail"] = self._reason_detail(fields["reason_detail"])
        record = {"repository": repository, "status": status,
                  "time": int(time.time()), **fields}
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository):
            raise PermissionError("Invalid persistent repository identity")
        current = [r for r in original["active"]
                   if isinstance(r, dict) and r.get("repository") != repository]
        if len(current) >= self.workspace.max_items:
            raise PermissionError("Active inventory full")
        original["active"] = current + [record]
        # Use fsync + atomic replace; never write inside the JAS checkout.
        handle, temporary = tempfile.mkstemp(prefix=".inventory-", dir=self.workspace.root)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(original, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._inventory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._audit(repository, status, record)

    def _audit(self, repository: str, status: str, record: dict):
        destination = self.workspace.root / "logs" / "autonomous-activations.jsonl"
        if destination.is_symlink():
            raise PermissionError("Unsafe activation audit log")
        if destination.exists() and destination.stat().st_size > 200_000:
            rotation = destination.with_suffix(".previous.jsonl")
            if rotation.is_symlink():
                raise PermissionError("Unsafe activation audit rotation")
            destination.replace(rotation)
        with destination.open("a", encoding="utf-8") as stream:
            evidence = {"time": record["time"], "repository": repository,
                        "status": status}
            if status in {"QUARANTINED", "WAITING_ATTESTATION"}:
                for key in ("reason_code", "reason_detail"):
                    if key in record:
                        evidence[key] = record[key]
            stream.write(json.dumps(evidence, sort_keys=True) + "\n")

    def _attestor(self, grant: dict) -> IndependentAttestationVerifier:
        pub = self.workspace.root / "trust" / "sandbox-attestor.pub.pem"
        if (pub.is_symlink() or not pub.is_file() or pub.stat().st_size > 512):
            raise PermissionError("Independently pinned attestor key missing")
        key = serialization.load_pem_public_key(pub.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise PermissionError("Untrusted attestor key")
        raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if hashlib.sha256(raw).hexdigest() != grant["attestor_key_sha256"]:
            raise PermissionError("Attestor key fingerprint mismatch")
        return IndependentAttestationVerifier(
            trusted_public_keys={"operator_attestor": raw},
            expected_image_digest=grant["oci_image"].split("@", 1)[1],
            expected_policy_sha256=grant["policy_sha256"],
            expected_tests_sha256=grant["tests_sha256"],
            trusted_runner_id=grant["attestor_runner_id"],
        )

    def _still_authorized(self, name: str) -> bool:
        if self.delegation.verified_grant() is None:
            return False
        repository = name.replace("__", "/")
        try:
            records = self._load_inventory()["active"]
            return not any(
                isinstance(row, dict) and row.get("repository") == repository
                and row.get("status") in {"REVOKED", "QUARANTINED"}
                for row in records
            )
        except (OSError, ValueError, PermissionError, TypeError):
            return False

    async def _connect(self, name: str, grant: dict, entry: str, expires_at: int,
                       execution_profile: str = "docker-stdio"):
        runtime = self.workspace.root / "runtime" / name
        if self._factory is not None:
            return await self._factory(name, grant, entry)
        import shutil
        if execution_profile == "windows-job-stdio":
            if (os.name != "nt" or
                grant.get("allow_local_windows_process", False) is not True):
                raise PermissionError("Owner did not permit local Windows MCP process")
            parameters = bridge_parameters(runtime, entry)
        elif execution_profile == "docker-stdio":
            docker = shutil.which("docker")
            if not docker or grant["oci_image"] is None:
                raise PermissionError("Isolated Docker MCP runtime unavailable")
            sandbox = IsolatedMCPPreflight(self.workspace, image=grant["oci_image"])
            parameters = StdioServerParameters(
                command=docker, args=sandbox._docker_arguments(runtime, entry),
                env={},
            )
        else:
            raise PermissionError("Unknown external MCP execution profile")
        connection = MCPConnection()
        try:
            await asyncio.wait_for(connection.connect_stdio(parameters), timeout=20)
            return DockerMCPProvider(
                connection, runtime=runtime, archive_sha256="",
                workspace=self.workspace, package=name,
                on_failure=lambda key: asyncio.create_task(self.quarantine(key)),
                owner_authorized=lambda: self._still_authorized(name),
                attestation_expires_at=expires_at,
            )
        except BaseException:
            await connection.close()
            raise

    async def _verify_and_connect(self, name: str, grant: dict):
        # Independent attestor quarantine must take precedence over a missing
        # prepared runtime. Evidence presence/shape is checked before invoking
        # the static candidate / runtime-tree checks, which may themselves fail
        # for a package whose attestation never completed. Cryptographic claims
        # are STILL verified below against independently checked source + tree.
        package = self.workspace.root / "verified" / name
        marker = package / "local-windows-quarantined.json"
        if marker.exists() or marker.is_symlink():
            raise PermissionError("Local Windows MCP candidate quarantined by independent attestor")
        bundle_file = package / "independent-attestations.json"
        if (bundle_file.is_symlink() or not bundle_file.is_file()
                or bundle_file.stat().st_size > _TOOL_LIMIT_BYTES):
            raise PermissionError("Independently signed sandbox results missing")
        bundle = json.loads(bundle_file.read_text("utf-8"))
        if not isinstance(bundle, dict):
            raise PermissionError("Untrusted sandbox bundle")
        decision = self.decisions.evaluate(name)
        if (decision.status != "AUTO_APPROVED_BY_POLICY"
                or decision.category not in grant["categories"]):
            raise PermissionError("Independent Owner approval scope invalid")
        repository, sha = decision.repository, decision.source_sha256
        details, _, _ = self.decisions._check_candidate(name)
        with (self.workspace.root / "verified" / name / "source.zip").open("rb") as stream:
            retained, _, _ = _validated_files(stream)
        entry = choose_python_entrypoint(retained, details.get("entrypoint_hint", ""))
        tree = runtime_fingerprint(self.workspace, name)
        profile = bundle.get("execution_profile", "docker-stdio")
        expected_fields = {"schema", "repository", "runtime_tree_sha256", "tools"}
        if profile == "windows-job-stdio":
            expected_fields.add("execution_profile")
            if (os.name != "nt" or
                grant.get("allow_local_windows_process", False) is not True):
                raise PermissionError("Unsigned local Windows execution permission")
        elif profile != "docker-stdio":
            raise PermissionError("Unknown external attestation profile")
        if (set(bundle) != expected_fields or bundle["schema"] != _SCHEMA
                or bundle["repository"] != repository
                or bundle["runtime_tree_sha256"] != tree
                or not isinstance(bundle["tools"], list)
                or not 1 <= len(bundle["tools"]) <= min(_MAX_TOOLS, grant["max_tools"])):
            raise PermissionError("Untrusted sandbox bundle")
        attestor = self._attestor(grant) if profile == "docker-stdio" else None
        local_key = None
        if profile == "windows-job-stdio":
            pub = self.workspace.root / "trust" / "sandbox-attestor.pub.pem"
            if pub.is_symlink() or not pub.is_file() or pub.stat().st_size > 512:
                raise PermissionError("Pinned attestor key missing")
            local_key = serialization.load_pem_public_key(pub.read_bytes())
            if not isinstance(local_key, Ed25519PublicKey):
                raise PermissionError("Invalid local attestor key type")
            raw = local_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            if hashlib.sha256(raw).hexdigest() != grant["attestor_key_sha256"]:
                raise PermissionError("Local attestor pin mismatch")
        expected: dict[str, MCPTool] = {}
        proof_hashes: dict[str, str] = {}
        expiries: list[int] = []
        for row in bundle["tools"]:
            if not isinstance(row, dict) or set(row) != {"name", "input_schema", "attestation"}:
                raise PermissionError("Untrusted tool attestation format")
            tool = MCPTool(name=row["name"], description="", input_schema=row["input_schema"])
            if tool.name in expected or not _TOOL.fullmatch(tool.name):
                raise PermissionError("Duplicate or unsupported external tool")
            if profile == "windows-job-stdio":
                identity = local_binding(
                    repository=repository, source_sha256=sha,
                    tree_sha256=tree, tool=tool, category=decision.category,
                )
                expiry = verify_local(
                    row["attestation"], key=local_key, grant=grant,
                    source_sha256=sha, tree_sha256=tree, binding_digest=identity,
                )
                expiries.append(expiry)
            else:
                identity = tool_binding_digest(
                    repository=repository, source_sha256=sha,
                    tree_sha256=tree, image=grant["oci_image"],
                    tool=tool, category=decision.category,
                )
                envelope = SignedSandboxAttestation.from_dict(row["attestation"])
                if envelope.claims.expires_at <= int(time.time()):
                    raise PermissionError("Independent sandbox attestation expired")
                if not attestor.verify(envelope, source_sha256=sha, binding_digest=identity):
                    raise PermissionError("Independent sandbox attestation rejected")
                expiries.append(envelope.claims.expires_at)
            expected[tool.name] = tool
            proof_hashes[tool.name] = hashlib.sha256(
                json.dumps(row["attestation"], sort_keys=True).encode()
            ).hexdigest()
        if _schema_json_size({name: tool.input_schema
                              for name, tool in expected.items()}) > _MAX_SCHEMA_JSON_BYTES:
            raise PermissionError("Signed MCP schemas exceed delegated size budget")
        expiry = min(expiries)
        provider = await self._connect(name, grant, entry, expiry, execution_profile=profile)
        try:
            tools = await asyncio.wait_for(provider.list_tools(), timeout=6)
            if (len(tools) != len(expected)
                    or set(tool.name for tool in tools) != set(expected)):
                raise PermissionError("Healthy MCP tool identity changed")
            for tool in tools:
                if canonical_hash(tool.input_schema) != canonical_hash(expected[tool.name].input_schema):
                    raise PermissionError("Healthy MCP schema changed")
            # Re-check after startup: external runner must not mutate files.
            if runtime_fingerprint(self.workspace, name) != tree:
                raise PermissionError("Runtime changed after independent attestation")
            return decision, provider, tools, proof_hashes, expiry
        except BaseException:
            await provider.close()
            raise

    async def scan(self, *, limit: int = 3) -> list[str]:
        grant = self.delegation.verified_grant()
        if grant is None:
            # Revoke every live capability when standing consent expires.
            for name in tuple(self._active):
                await self.quarantine(name)
            return []
        successes: list[str] = []
        attempted = 0
        # Expired sandbox evidence always retires old live providers before
        # another trust decision. No MCP call may use stale evidence.
        expired_this_scan: set[str] = set()
        for name, active in tuple(self._active.items()):
            if not self._still_authorized(name):
                await self.quarantine(name)
            elif time.time() >= active.attestation_expires_at:
                # Expiry is a dependency. Disconnect now; only a subsequent
                # scan with independently renewed evidence can reactivate.
                expired_this_scan.add(name)
                await self._remove(name, quarantine=False)
                self._persist(name.replace("__", "/"), "WAITING_ATTESTATION",
                              reason_code="EXPIRED_ATTESTATION",
                              reason_detail="Independent attestation expired; renewal required")
        async with self._lock:
            existing = frozenset(value.category for value in self._active.values())
            persistent = {
                row["repository"]: row
                for row in self._load_inventory()["active"]
                if isinstance(row, dict)
                and isinstance(row.get("repository"), str)
                and row.get("status") in {"ACTIVE", "QUARANTINED", "REVOKED",
                                           "WAITING_ATTESTATION"}
            }
            # Existing signed observations plus a prepared runtime go first,
            # even when their repository names sort after unsatisfied packages.
            # Presence is only a scheduling hint, NEVER proof authorization.
            pending = self.decisions.evaluate_pending(limit=100)
            def is_prepared(decision) -> bool:
                if decision.status != "AUTO_APPROVED_BY_POLICY":
                    return False
                name = decision.repository.replace("/", "__")
                package = self.workspace.root / "verified" / name
                evidence = package / "independent-attestations.json"
                runtime = self.workspace.root / "runtime" / name
                marker = package / "local-windows-quarantined.json"
                return (not marker.exists() and not marker.is_symlink()
                        and evidence.is_file() and not evidence.is_symlink()
                        and runtime.is_dir() and not runtime.is_symlink())
            pending.sort(key=lambda decision: 0 if is_prepared(decision) else 1)
            for decision in pending:
                if decision.status != "AUTO_APPROVED_BY_POLICY":
                    continue
                name = decision.repository.replace("/", "__")
                previous = persistent.get(decision.repository, {})
                status = previous.get("status")
                local_signed = (os.name == "nt" and
                                grant.get("allow_local_windows_process", False) is True)
                package = self.workspace.root / "verified" / name
                # Operator-quarantined providers and Owner revocations stay
                # blocked. A completed independent refresh may re-enter normal
                # verification even after a previous recovery attempt: the
                # *entire* signed bundle, source, expiry and runtime are checked
                # in _verify_and_connect before any capability is registered.
                marker = package / "local-windows-quarantined.json"
                evidence = package / "independent-attestations.json"
                recovery = (
                    status == "QUARANTINED"
                    and local_signed
                    and previous.get("reason_code") not in {
                        "PROVIDER_FAILED_OR_REVOKED", "OWNER_REVOKED",
                    }
                    and not marker.exists() and not marker.is_symlink()
                    and evidence.is_file() and not evidence.is_symlink()
                )
                if (name in self._active or name in expired_this_scan
                        or status == "REVOKED"
                        or (status == "QUARANTINED" and not recovery)):
                    continue

                # Checking the independent operator marker is metadata-only:
                # do not invoke untrusted MCP nor charge the live connection
                # budget. Preserve signed-expiry refresh only when verifiable.
                if marker.exists() or marker.is_symlink():
                    if status != "QUARANTINED":
                        renewal = (local_signed and not marker.is_symlink()
                                   and expired_attestation_evidence(
                                       self.workspace, name, grant=grant))
                        self._persist(
                            decision.repository,
                            "WAITING_ATTESTATION" if renewal else "QUARANTINED",
                            reason_code=("EXPIRED_ATTESTATION" if renewal
                                         else "INDEPENDENT_ATTESTOR_QUARANTINE"),
                            reason_detail=("Signed evidence expired; awaiting independent renewal"
                                           if renewal else
                                           "Independent attestor quarantined this candidate"),
                        )
                    continue

                runtime = self.workspace.root / "runtime" / name
                if evidence.is_symlink() or runtime.is_symlink() or (
                        hasattr(runtime, "is_junction") and runtime.is_junction()):
                    if status != "QUARANTINED":
                        self._persist(
                            decision.repository, "QUARANTINED",
                            reason_code="UNSAFE_RUNTIME_OR_EVIDENCE_PATH",
                            reason_detail="Symlink or junction in evidence/runtime path",
                        )
                    continue
                if not evidence.is_file() or not runtime.is_dir():
                    reason = ("INDEPENDENT_ATTESTATION_MISSING"
                              if not evidence.is_file() else "RUNTIME_NOT_PREPARED")
                    if status != "WAITING_ATTESTATION" or previous.get("reason_code") != reason:
                        self._persist(
                            decision.repository, "WAITING_ATTESTATION",
                            reason_code=reason,
                            reason_detail=("Signed independent attestation missing"
                                           if reason == "INDEPENDENT_ATTESTATION_MISSING"
                                           else "Sandbox runtime not prepared"),
                        )
                    continue

                # Category dedupe applies to ACTUAL activation only. Missing
                # evidence and independent quarantine were reported above and
                # must not get hidden by a previously activated sibling.
                if decision.category in existing:
                    continue
                # Only candidates with BOTH evidence and a runtime consume
                # live MCP connection slots. Full signatures and tree hashes
                # remain mandatory inside _verify_and_connect().
                if attempted >= max(1, min(3, limit)):
                    continue
                attempted += 1
                try:
                    details, provider, tools, proofs, expiry = await self._verify_and_connect(name, grant)
                    await self._register(name, details, provider, tools, proofs, expiry)
                    successes.append(decision.repository)
                    existing = existing | {decision.category}
                except Exception as exc:
                    # Missing/expired attestor observation is a dependency,
                    # not an executed provider failure. Keep eligible for a
                    # later independently signed observation, never execute.
                    waiting = isinstance(exc, PermissionError) and (
                        "signed sandbox results missing" in str(exc)
                        or "Sandbox runtime not prepared" in str(exc)
                        or "pinned attestor key missing" in str(exc)
                        or "attestation expired" in str(exc)
                        or (
                            local_signed
                            and "Local Windows MCP candidate quarantined by independent attestor" in str(exc)
                            and expired_attestation_evidence(self.workspace, name, grant=grant)
                        )
                    )
                    self._persist(
                        decision.repository,
                        "WAITING_ATTESTATION" if waiting else "QUARANTINED",
                        reason_code=type(exc).__name__,
                        reason_detail=self._reason_detail(exc),
                        recovery_version=1 if recovery else 0,
                    )
        return successes

    async def _register(self, name, decision, provider, tools, proofs, expiry):
        short = hashlib.sha256(name.encode()).hexdigest()[:16]
        provider_id = "aura.external." + short
        service = ServiceDefinition(
            name="external-mcp-" + short, version="1.0.0", provider="aura",
            category=ServiceCategory.MCP, capabilities=frozenset(),
            tags=frozenset({"external", "isolated", "delegated"}),
        )
        capability_ids: list[str] = []
        policy_ids: list[str] = []
        registered_service = False
        registered_provider = False
        try:
            self.kernel.service_registry.register(service, provider)
            registered_service = True
            self.kernel.provider_registry.register(ProviderDefinition(
                provider_id=provider_id, name=decision.repository,
                version="1.0.0", service_id=service.service_id,
            ), provider)
            registered_provider = True
            grant = self.delegation.verified_grant()
            if grant is None:
                raise PermissionError("Owner delegation revoked")
            for tool in tools:
                capability = "external.mcp." + short + "." + tool.name
                scope = "evolution:isolated:" + decision.source_sha256 + ":" + tool.name
                self.kernel.capability_registry.register(CapabilityDefinition(
                    capability_id=capability, name=tool.name,
                    version="1.0.0", description="Offline, sandboxed external MCP tool",
                    provider_id=provider_id, provider_type=ProviderType.MCP,
                    category=_CATEGORY[decision.category], tool_name=tool.name,
                    risk_level="low", required_permissions=frozenset({capability}),
                ))
                capability_ids.append(capability)
                # Revoked PermissionPolicy records remain retained by the
                # immutable PermissionEngine. A renewed independently signed
                # attestation must therefore produce a new policy identity.
                policy_id = ("local-owner:external-mcp:" + short + ":" +
                             tool.name + ":" + proofs[tool.name][:10])
                self.kernel.permission_engine.add_policy(PermissionPolicy(
                    policy_id=policy_id, policy_version="1.0.0",
                    principal_id="local_owner",
                    capability_id=capability, operation_id=capability,
                    resource_scope=scope, authorization_level=AuthorizationLevel.EXECUTE,
                    decision=AuthorizationDecision.ALLOW,
                ))
                policy_ids.append(policy_id)
                self.tools.register(provider_id, tool)
            self._persist(decision.repository, "ACTIVE",
                          source_sha256=decision.source_sha256,
                          provider_id=provider_id, category=decision.category,
                          capabilities=capability_ids,
                          tool_attestation_sha256=proofs,
                          attestation_expires_at=expiry)
            self._active[name] = _Live(provider, provider_id, service.service_id,
                                       tuple(capability_ids), tuple(policy_ids),
                                       decision.category, expiry)
            if self.kernel.event_bus:
                self.kernel.event_bus.publish(KernelEvent(
                    event_type="AutonomousCapabilityActivated",
                    source_component="delegated_mcp_activation",
                    payload={"repository": decision.repository,
                             "capabilities": capability_ids},
                ))
                self.kernel.event_bus.publish(KernelEvent(
                    event_type="ProactiveNotificationReady",
                    source_component="delegated_mcp_activation",
                    payload={
                        "principal_id": "local_owner",
                        "message": "Otomatik etkinleştirilen yeni yetenekler: " +
                                   ", ".join(capability_ids),
                        "requires_user_attention": False,
                    },
                ))
        except BaseException:
            for policy in policy_ids:
                try: self.kernel.permission_engine.revoke_policy(policy)
                except KeyError: pass
            for capability in capability_ids:
                try: self.kernel.capability_registry.unregister(capability, provider_id)
                except KeyError: pass
            self.tools.unregister_provider(provider_id)
            if registered_provider:
                self.kernel.provider_registry.unregister(provider_id)
            if registered_service:
                self.kernel.service_registry.update_state(service.service_id, ServiceState.FAILED)
                self.kernel.service_registry.unregister(service.service_id)
            await provider.close()
            raise

    async def _remove(self, name: str, *, quarantine: bool) -> None:
        async with self._lock:
            active = self._active.pop(name, None)
            if active is None:
                return
            for policy in active.policies:
                self.kernel.permission_engine.revoke_policy(policy)
            for capability in active.capabilities:
                self.kernel.capability_registry.unregister(capability, active.provider_id)
            self.tools.unregister_provider(active.provider_id)
            self.kernel.provider_registry.unregister(active.provider_id)
            self.kernel.service_registry.update_state(
                active.service_id, ServiceState.FAILED if quarantine else ServiceState.STOPPED,
            )
            self.kernel.service_registry.unregister(active.service_id)
            if quarantine:
                self._persist(name.replace("__", "/"), "QUARANTINED",
                              reason_code="PROVIDER_FAILED_OR_REVOKED",
                              reason_detail="External provider failed or was explicitly revoked")
            await active.provider.close()

    async def quarantine(self, name: str) -> None:
        await self._remove(name, quarantine=True)

    async def revoke(self, repository: str) -> None:
        await self.quarantine(repository.replace("/", "__"))

    async def start(self) -> None:
        """Recover signed, still-fresh live capabilities at process startup."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        # The initial scan may include a 20s Windows MCP handshake. Never
        # hold the ASGI lifespan or /health behind an external process.
        self._task = asyncio.create_task(self._run(), name="aura-delegated-mcp")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                # First scan happens after start() returns to the event loop.
                await self.scan(limit=3)
            except asyncio.CancelledError:
                raise
            except Exception:
                # External MCP/transport exceptions cannot crash the daemon.
                # Each candidate failure is quarantined with bounded details.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    def active_summary(self) -> list[dict]:
        """Expose only metadata, never protected credentials or source code."""
        inventory = self._load_inventory()
        return [
            {key: row[key] for key in
             ("repository", "status", "capabilities", "category", "time")
             if key in row}
            for row in inventory["active"]
            if isinstance(row, dict)
        ]

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        # Graceful shutdown closes workers and policies; retains ACTIVE
        # inventory, so restart may reload only after fresh proof validation.
        for name in tuple(self._active):
            await self._remove(name, quarantine=False)
