"""Owner-approved versioned MCP binding switch, without importing generated code.

Only maps a reviewed skill alias to an *already registered* MCP capability.
Every actual tool execution is still submitted to MCPGateway, which independently
enforces PermissionEngine and any required human approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from threading import RLock
from typing import Callable
from uuid import uuid4

from aura_core.kernel.capabilities import CapabilityRegistry, ProviderType
from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.mcp.provider import ProviderRegistry

_VALID_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class SkillBinding:
    name: str
    version: str
    source_sha256: str
    capability_id: str
    provider_id: str
    operation_id: str
    tool_name: str
    resource_scope: str
    risk_level: RiskLevel

    def __post_init__(self) -> None:
        if not _VALID_NAME.fullmatch(self.name) or not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("Invalid skill identity")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version):
            raise ValueError("Expected semver version")
        for key in ("capability_id", "provider_id", "operation_id", "tool_name", "resource_scope"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError("Invalid MCP binding: " + key)
        if not isinstance(self.risk_level, RiskLevel) or self.risk_level == RiskLevel.MINIMAL:
            raise ValueError("Risk level must be explicitly declared")

    @property
    def review_digest(self) -> str:
        # Binds owner receipt to ALL fields; a scope change invalidates consent.
        canonical = asdict(self)
        canonical["risk_level"] = self.risk_level.value
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


ReviewVerifier = Callable[[str, str], bool]
OwnerReceiptConsumer = Callable[[str, str, str, str], bool]
SignedAttestationVerifier = Callable[["SkillBinding", str], bool]


@dataclass(frozen=True, slots=True)
class ReviewedVersion:
    revision: str
    binding: SkillBinding
    validation_receipt: str


class GovernedSkillRegistry:
    """No authority of its own: external trusted verifiers are mandatory."""

    def __init__(
        self, *, capabilities: CapabilityRegistry, providers: ProviderRegistry,
        validation_verifier: ReviewVerifier,
        owner_receipt_consumer: OwnerReceiptConsumer,
        max_staged: int = 100,
        signed_attestation_verifier: SignedAttestationVerifier | None = None,
    ) -> None:
        if not callable(validation_verifier) or not callable(owner_receipt_consumer):
            raise ValueError("Independent verifier callbacks are required")
        if not 1 <= max_staged <= 500:
            raise ValueError("Invalid staging budget")
        self._capabilities = capabilities
        self._providers = providers
        self._validation = validation_verifier
        self._owner = owner_receipt_consumer
        # Production must inject AttestationReceiptRegistry.verify_binding.
        # Existing plain validator remains for compatibility with existing
        # GovSkill tests, but does not substitute for signed verification.
        if signed_attestation_verifier is not None and not callable(signed_attestation_verifier):
            raise ValueError("Invalid signed attestation verifier")
        self._signed = signed_attestation_verifier
        self._max_staged = max_staged
        self._staged: dict[str, SkillBinding] = {}
        self._verified: dict[str, str] = {}
        self._active: dict[str, ReviewedVersion] = {}
        self._history: dict[str, list[ReviewedVersion]] = {}
        self._lock = RLock()

    def _registered(self, binding: SkillBinding) -> None:
        records = self._capabilities.providers(binding.capability_id)
        matched = [
            record for record in records
            if record.definition.provider_id == binding.provider_id
            and record.definition.provider_type == ProviderType.MCP
            and record.definition.tool_name == binding.tool_name
            and record.definition.risk_level == binding.risk_level.value
            and record.available and record.healthy
        ]
        if not matched:
            raise PermissionError("No matching healthy, pre-registered MCP capability")
        self._providers.resolve(binding.provider_id)

    def stage(self, binding: SkillBinding) -> str:
        """Stage metadata only; never execute, import, or install a candidate."""
        with self._lock:
            if binding.name not in self._staged and len(self._staged) >= self._max_staged:
                raise ValueError("Skill staging capacity exceeded")
            self._staged[binding.name] = binding
            self._verified.pop(binding.name, None)
            return binding.review_digest

    def validate(self, name: str, *, sandbox_receipt: str) -> bool:
        """Require independent, digest-bound sandbox evidence from trusted runner."""
        with self._lock:
            binding = self._staged.get(name)
            if binding is None:
                raise KeyError(name)
            self._registered(binding)
            if not sandbox_receipt or len(sandbox_receipt) > 128:
                raise PermissionError("A sandbox evidence receipt is required")
            if not self._validation(binding.source_sha256, sandbox_receipt):
                raise PermissionError("Sandbox validation cannot be independently verified")
            if self._signed is not None and not self._signed(binding, sandbox_receipt):
                raise PermissionError("Signed attestation missing, mismatched or untrusted")
            self._verified[name] = sandbox_receipt
            return True

    def activate(self, name: str, *, principal_id: str, owner_receipt: str) -> str:
        with self._lock:
            binding = self._staged.get(name)
            receipt = self._verified.get(name)
            if binding is None or receipt is None:
                raise PermissionError("Stage and independent sandbox validation required")
            if principal_id != "local_owner" or not owner_receipt:
                raise PermissionError("Local Owner consent required")
            self._registered(binding)
            if not self._validation(binding.source_sha256, receipt):
                raise PermissionError("Sandbox evidence no longer valid")
            if self._signed is not None and not self._signed(binding, receipt):
                raise PermissionError("Signed attestation has expired or changed")
            if not self._owner(principal_id, "activate", binding.review_digest, owner_receipt):
                raise PermissionError("Owner receipt rejected")
            previous = self._active.get(name)
            if previous:
                self._history.setdefault(name, []).append(previous)
            new = ReviewedVersion(str(uuid4()), binding, receipt)
            self._active[name] = new
            return new.revision

    def rollback(self, name: str, *, principal_id: str, owner_receipt: str) -> str:
        with self._lock:
            history = self._history.get(name)
            if not history or principal_id != "local_owner" or not owner_receipt:
                raise PermissionError("No reviewed rollback or owner consent")
            previous = history[-1]
            self._registered(previous.binding)
            if not self._validation(previous.binding.source_sha256, previous.validation_receipt):
                raise PermissionError("Prior validation is no longer trusted")
            if self._signed is not None and not self._signed(previous.binding, previous.validation_receipt):
                raise PermissionError("Prior signed attestation is no longer trusted")
            if not self._owner(principal_id, "rollback", previous.binding.review_digest, owner_receipt):
                raise PermissionError("Rollback owner receipt rejected")
            history.pop()
            self._active[name] = previous
            return previous.revision

    def revoke(self, name: str, *, principal_id: str, owner_receipt: str) -> None:
        with self._lock:
            current = self._active.get(name)
            if current is None or principal_id != "local_owner":
                raise PermissionError("Only owner may revoke an active skill")
            if not self._owner(principal_id, "revoke", current.binding.review_digest, owner_receipt):
                raise PermissionError("Revocation consent rejected")
            del self._active[name]

    def catalog(self) -> tuple[dict, ...]:
        with self._lock:
            return tuple({
                "name": name, "version": value.binding.version,
                "revision": value.revision,
                "source_sha256": value.binding.source_sha256,
                "capability_id": value.binding.capability_id,
                "status": "active",
            } for name, value in sorted(self._active.items()))

    def to_gateway_request(
        self, name: str, *, principal_id: str,
        arguments: dict | None = None, approval_id: str | None = None,
    ) -> MCPGatewayRequest:
        with self._lock:
            if principal_id != "local_owner":
                raise PermissionError("Only local owner may invoke activated skill alias")
            version = self._active.get(name)
            if version is None:
                raise PermissionError("Skill is not active")
            item = version.binding
            self._registered(item)
            if arguments is not None and not isinstance(arguments, dict):
                raise ValueError("MCP arguments must be a JSON object")
            # Gateway always re-checks live policies and high-risk approval.
            return MCPGatewayRequest(
                request_id=str(uuid4()), principal_id=principal_id,
                capability_id=item.capability_id,
                operation_id=item.operation_id,
                resource_scope=item.resource_scope,
                risk_level=item.risk_level, tool_name=item.tool_name,
                arguments=arguments or {}, approval_id=approval_id,
            )
