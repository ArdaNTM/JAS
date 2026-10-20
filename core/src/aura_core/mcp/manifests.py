"""Deterministic, policy-bearing manifests for the AURA MCP fleet."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Iterable

from aura_core.kernel.permissions import RiskLevel


class MCPManifestStatus(StrEnum):
    DISABLED = "disabled"
    CANDIDATE = "candidate"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class MCPManifest:
    """The minimum immutable contract required to admit an MCP provider."""

    provider_id: str
    version: str
    transport: str
    risk_level: RiskLevel
    quota_per_minute: int
    permission_policy_id: str
    status: MCPManifestStatus = MCPManifestStatus.CANDIDATE
    artifact_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id or not self.version:
            raise ValueError("MCP manifest provider_id and version are required")
        if self.transport not in {"stdio", "http"}:
            raise ValueError("MCP manifest transport must be stdio or http")
        if self.quota_per_minute < 1:
            raise ValueError("MCP manifest quota_per_minute must be positive")
        if not self.permission_policy_id:
            raise ValueError("MCP manifest permission_policy_id is required")
        if self.status is MCPManifestStatus.APPROVED and not self.artifact_digest:
            raise ValueError("Approved MCP manifests require an artifact digest")


class DeterministicMCPManifestLoader:
    """Validates and loads a profile in stable provider-id order."""

    def __init__(self, registrar: Callable[[MCPManifest], None]) -> None:
        self._registrar = registrar

    def load(self, manifests: Iterable[MCPManifest]) -> tuple[MCPManifest, ...]:
        ordered = tuple(sorted(manifests, key=lambda item: item.provider_id))
        provider_ids = [item.provider_id for item in ordered]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("MCP manifest provider_id values must be unique")
        for manifest in ordered:
            if manifest.status is MCPManifestStatus.APPROVED:
                self._registrar(manifest)
        return ordered
