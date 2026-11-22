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
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight, choose_python_entrypoint
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
_TOOL_LIMIT_BYTES = 100_000
_CATEGORY = {
    "desktop_automation": CapabilityCategory.AUTOMATION,
    "code_analysis": CapabilityCategory.CODING,
    "local_memory": CapabilityCategory.MEMORY,
    "web_research": CapabilityCategory.RESEARCH,
    "developer_tools": CapabilityCategory.CODING,
}


def canonical_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                      separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()


def runtime_fingerprint(workspace: EvolutionWorkspace, name: str) -> str:
    """Reject altered, added, symlinked or missing source before every use."""
    verified = workspace.root / "verified" / name
    runtime = workspace.root / "runtime" / name
    if (not runtime.is_dir() or runtime.is_symlink()
            or not verified.is_dir() or verified.is_symlink()):
        raise PermissionError("Missing or unsafe independently prepared runtime")
    _checked_path(runtime)
    with (verified / "source.zip").open("rb") as stream:
        files, _entry, _skipped = _validated_files(stream)
    allowed = set(files) | {".aura-untrusted-review.json"}
    seen: set[str] = set()
    for path in runtime.rglob("*"):
        if len(seen) > len(allowed) + 20:
            raise PermissionError("Untrusted additional runtime files")
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise PermissionError("Unsafe runtime symlink/junction")
        if path.is_file():
            rel = path.relative_to(runtime).as_posix()
            if rel not in allowed:
                raise PermissionError("Unexpected runtime executable or data")
            seen.add(rel)
    if set(files) - seen:
        raise PermissionError("Prepared runtime missing source files")
    manifest = runtime / ".aura-untrusted-review.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 4096:
        raise PermissionError("Prepared runtime marker absent")
    data = json.loads(manifest.read_text("utf-8"))
    digest = hashlib.sha256((verified / "source.zip").read_bytes()).hexdigest()
    if data.get("source_sha256") != digest or data.get("activation_performed") is not False:
        raise PermissionError("Runtime source marker changed")
    lines = []
    for rel in sorted(files):
        actual = (runtime / rel).read_bytes()
        if actual != files[rel]:
            raise PermissionError("Prepared runtime source changed")
        lines.append(rel + "\t" + hashlib.sha256(actual).hexdigest() + "\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def tool_binding_digest(*, repository: str, source_sha256: str, tree_sha256: str,
                        image: str, tool: MCPTool, category: str) -> str:
    if (not _TO.fullmatch(tool.name) or not isinstance(tool.input_schema, dict)
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
    """Actual stdio MCP bridge, never a host Python/Node process."""

    def __init__(self, connection: MCPConnection, *, runtime: Path,
                 archive_sha256: str, workspace: EvolutionWorkspace,
                 package: str, on_failure: Callable[[str], None],
                 owner_authorized: Callable[[], bool]):
        super().__init__(connection)
        self.runtime = runtime
        self.archive_sha256 = archive_sha256
        self.workspace = workspace
        self.package = package
        self._on_failure = on_failure
        self._owner_authorized = owner_authorized
        self._healthy = True

    async def list_tools(self):
        if not self._healthy or not self._owner_authorized():
            raise PermissionError("Quarantined or revoked external provider")
        return await super().list_tools()

    async def call_tool(self, name, arguments=None):
        if not self._healthy or not self._owner_authorized():
            self._healthy = False
            self._on_failure(self.package)
            raise PermissionError("Quarantined or revoked external provider")
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


class DelegatedMCPActivationManager:
    """Fail-closed, offline Docker-only activation with independent signatures."""

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
        if self._inventory.is_symlink() or not self._inventory.is_file():
            raise PermissionError("Active inventory must be a regular external file")
        data = json.loads(self._inventory.read_text("utf-8"))
        if (not isinstance(data, dict)
                or data.get("schema") != "aura.external-capabilities.v1"
                or not isinstance(data.get("active"), list)
                or len(data["active"]) > self.workspace.max_items):
            raise PermissionError("Invalid active capability inventory")
        return data

    def _persist(self, repository: str, status: str, **fields):
        original = self._load_inventory()
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
        self._audit(repository, status)

    def _audit(self, repository: str, status: str):
        destination = self.workspace.root / "logs" / "autonomous-activations.jsonl"
        if destination.is_symlink():
            raise PermissionError("Unsafe activation audit log")
        if destination.exists() and destination.stat().st_size > 200_000:
            rotation = destination.with_suffix(".previous.jsonl")
            if rotation.is_symlink():
                raise PermissionError("Unsafe activation audit rotation")
            destination.replace(rotation)
        with destination.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": int(time.time()), "repository": repository,
                                     "status": status}, sort_keys=True) + "\n")

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

    async def _connect(self, name: str, grant: dict, entry: str):
        runtime = self.workspace.root / "runtime" / name
        if self._factory is not None:
            return await self._factory(name, grant, entry)
        import shutil
        docker = shutil.which("docker")
        if not docker:
            raise PermissionError("Isolated Docker MCP runtime unavailable")
        sandbox = IsolatedMCPPreflight(self.workspace, image=grant["oci_image"])
        connection = MCPConnection()
        try:
            await asyncio.wait_for(connection.connect_stdio(
                StdioServerParameters(
                    command=docker, args=sandbox._docker_arguments(runtime, entry),
                    env={},
                )
            ), timeout=20)
            return DockerMCPProvider(
                connection, runtime=runtime, archive_sha256="",
                workspace=self.workspace, package=name,
                on_failure=lambda key: asyncio.create_task(self.quarantine(key)),
                owner_authorized=lambda: self.delegation.verified_grant() is not None,
            )
        except BaseException:
            await connection.close()
            raise

    async def _verify_and_connect(self, name: str, grant: dict):
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
        package = self.workspace.root / "verified" / name
        bundle_file = package / "independent-attestations.json"
        if (bundle_file.is_symlink() or not bundle_file.is_file()
                or bundle_file.stat().st_size > _TOOL_LIMIT_BYTES):
            raise PermissionError("Independently signed sandbox results missing")
        bundle = json.loads(bundle_file.read_text("utf-8"))
        if (not isinstance(bundle, dict) or set(bundle) != {
            "schema", "repository", "runtime_tree_sha256", "tools",
        } or bundle["schema"] != _SCHEMA
                or bundle["repository"] != repository
                or bundle["runtime_tree_sha256"] != tree
                or not isinstance(bundle["tools"], list)
                or not 1 <= len(bundle["tools"]) <= grant["max_tools"]):
            raise PermissionError("Untrusted sandbox bundle")
        attestor = self._attestor(grant)
        expected: dict[str, MCPTool] = {}
        proof_hashes: dict[str, str] = {}
        for row in bundle["tools"]:
            if not isinstance(row, dict) or set(row) != {"name", "input_schema", "attestation"}:
                raise PermissionError("Untrusted tool attestation format")
            tool = MCPTool(name=row["name"], description="", input_schema=row["input_schema"])
            if tool.name in expected or not _TO.fullmatch(tool.name):
                raise PermissionError("Duplicate or unsupported external tool")
            identity = tool_binding_digest(
                repository=repository, source_sha256=sha,
                tree_sha256=tree, image=grant["oci_image"],
                tool=tool, category=decision.category,
            )
            envelope = SignedSandboxAttestation.from_dict(row["attestation"])
            if not attestor.verify(envelope, source_sha256=sha, binding_digest=identity):
                raise PermissionError("Independent sandbox attestation rejected")
            expected[tool.name] = tool
            proof_hashes[tool.name] = hashlib.sha256(
                json.dumps(row["attestation"], sort_keys=True).encode()
            ).hexdigest()
        provider = await self._connect(name, grant, entry)
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
            return decision, provider, tools, proof_hashes
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
        async with self._lock:
            existing = frozenset(value.category for value in self._active.values())
            for decision in self.decisions.evaluate_pending(limit=100):
                if attempted >= max(1, min(3, limit)):
                    break
                if decision.status != "AUTO_APPROVED_BY_POLICY":
                    continue
                name = decision.repository.replace("/", "__")
                if name in self._active or decision.category in existing:
                    continue
                attempted += 1
                try:
                    details, provider, tools, proofs = await self._verify_and_connect(name, grant)
                    await self._register(name, details, provider, tools, proofs)
                    successes.append(decision.repository)
                    existing = existing | {decision.category}
                except Exception as exc:
                    self._persist(decision.repository, "QUARANTINED",
                                  reason_code=type(exc).__name__)
        return successes

    async def _register(self, name, decision, provider, tools, proofs):
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
                policy_id = "local-owner:external-mcp:" + short + ":" + tool.name
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
                          tool_attestation_sha256=proofs)
            self._active[name] = _Live(provider, provider_id, service.service_id,
                                       tuple(capability_ids), tuple(policy_ids),
                                       decision.category)
            if self.kernel.event_bus:
                self.kernel.event_bus.publish(KernelEvent(
                    event_type="AutonomousCapabilityActivated",
                    source_component="delegated_mcp_activation",
                    payload={"repository": decision.repository,
                             "capabilities": capability_ids},
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
                              reason_code="PROVIDER_FAILED_OR_REVOKED")
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
        try:
            await self.scan(limit=3)
        except (OSError, ValueError, PermissionError, RuntimeError):
            # External code must never break Core startup.
            pass
        self._task = asyncio.create_task(self._run(), name="aura-delegated-mcp")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await self.scan(limit=3)
            except (OSError, ValueError, PermissionError, RuntimeError):
                # Failures are quarantined and audited per-package.
                continue

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
