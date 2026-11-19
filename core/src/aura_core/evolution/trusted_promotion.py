"""Async, owner-only promotion bridge for preinstalled AURA MCP capabilities.

This module does NOT import untrusted Python, create a ProviderRegistry entry,
change the release lock, or issue any signature. An independent Owner Control
Plane performs Windows Hello / WebAuthn assertion validation and signs a
single-use receipt; a separate sandbox attestor signs execution evidence.

The bridge strictly binds the preexisting GovernedSkillRegistry to the exact
DurableOwnerReceiptConsumer and DurableAttestationReceiptRegistry instances.
All actual operations remain MCPGatewayRequest objects that must be submitted
to MCPGateway (and independently authorized by PermissionEngine).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from functools import partial
from typing import Any

from aura_core.evolution.durable_attestation import DurableAttestationReceiptRegistry
from aura_core.evolution.evolution_gateway import EvolutionReviewGateway
from aura_core.evolution.owner_receipt import DurableOwnerReceiptConsumer
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.mcp.gateway import MCPGatewayRequest

_DRAFT_ID = re.compile(r"^[0-9a-f]{24}$")
_ATTESTATION = re.compile(r"^[0-9a-f]{64}$")


class PromotionDenied(PermissionError):
    """Independent trust evidence did not satisfy the Owner release boundary."""


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Unforgeable activation is represented by registry state, not this report."""
    draft_id: str
    name: str
    revision: str
    source_sha256: str
    status: str = "preinstalled_binding_activated"
    release_lock_modified: bool = False
    generated_source_imported: bool = False
    provider_registry_mutated: bool = False


class TrustedPromotionBridge:
    """Check immutable draft, independent signatures and single-use Owner receipt.

    No HTTP endpoint invokes this object. The trusted operator/owner process
    supplies a signed WebAuthn receipt obtained from the separate Owner Control
    Plane. The review gateway checks the on-disk guarded source digest, and the
    governed registry validates the healthy, *already registered* MCP provider,
    consumes the Owner receipt atomically, then activates the binding alias.

    The bridge serializes local activations but does not purport to be a
    distributed transaction coordinator. If an async caller is cancelled while
    a thread is committing a one-shot receipt, it MUST query the registry rather
    than replaying the receipt. The receipt store itself rejects replay.
    """

    def __init__(
        self, *,
        review_gateway: EvolutionReviewGateway,
        registry: GovernedSkillRegistry,
        owner_receipts: DurableOwnerReceiptConsumer,
        attestations: DurableAttestationReceiptRegistry,
    ) -> None:
        if not isinstance(review_gateway, EvolutionReviewGateway):
            raise TypeError("A trusted on-disk review gateway is mandatory")
        if not isinstance(registry, GovernedSkillRegistry):
            raise TypeError("The existing governed registry is mandatory")
        if not isinstance(owner_receipts, DurableOwnerReceiptConsumer):
            raise TypeError("A public-key-only durable Owner receipt consumer is mandatory")
        if not isinstance(attestations, DurableAttestationReceiptRegistry):
            raise TypeError("The durable independent attestation registry is mandatory")
        if registry._owner is not owner_receipts:
            raise PromotionDenied("Registry has a different Owner receipt authority")
        signed = registry._signed
        if (getattr(signed, "__self__", None) is not attestations
                or getattr(signed, "__func__", None)
                   is not DurableAttestationReceiptRegistry.verify_binding):
            raise PromotionDenied("Registry is not bound to the pinned attestation verifier")
        self._review = review_gateway
        self._registry = registry
        self._owner = owner_receipts
        self._attestor = attestations
        self._mutex = asyncio.Lock()

    async def activate_preinstalled(
        self, *,
        draft_id: str,
        binding: SkillBinding,
        principal_id: str,
        owner_receipt: str,
        sandbox_receipt: str,
    ) -> PromotionResult:
        """Activate only an exact reviewed preinstalled binding; never deploy code.

        The transition is executed in a worker thread because the existing
        durable receipt stores use synchronous SQLite. We intentionally never
        apply wait_for() to this side effect (timeout could lie about outcome).
        """
        if principal_id != "local_owner":
            raise PromotionDenied("Local Owner is mandatory")
        if not isinstance(binding, SkillBinding):
            raise TypeError("Expected immutable SkillBinding")
        if not isinstance(draft_id, str) or not _DRAFT_ID.fullmatch(draft_id):
            raise ValueError("Invalid immutable draft identifier")
        if not isinstance(owner_receipt, str) or not 1 <= len(owner_receipt) <= 4096:
            raise PromotionDenied("External signed Owner receipt required")
        if not isinstance(sandbox_receipt, str) or not _ATTESTATION.fullmatch(sandbox_receipt):
            raise PromotionDenied("Independently signed sandbox evidence required")

        async with self._mutex:
            # Trust roots are rechecked just before the irreversible transition.
            if self._registry._owner is not self._owner:
                raise PromotionDenied("Owner receipt verifier changed")
            signed = self._registry._signed
            if (getattr(signed, "__self__", None) is not self._attestor
                    or getattr(signed, "__func__", None)
                       is not DurableAttestationReceiptRegistry.verify_binding):
                raise PromotionDenied("Sandbox attestation verifier changed")
            if not await asyncio.to_thread(
                self._attestor.verify_binding, binding, sandbox_receipt,
            ):
                raise PromotionDenied("Sandbox attestation does not bind this reviewed capability")

            transition = partial(
                self._review.activate_pre_registered,
                draft_id=draft_id, binding=binding,
                sandbox_receipt=sandbox_receipt, owner_receipt=owner_receipt,
                registrar=self._registry, owner_receipts=self._owner,
                attestations=self._attestor, principal_id=principal_id,
            )
            # A committed receipt may outlive task cancellation; no retry is
            # offered here. Independent audit reads the resulting registry.
            revision = await asyncio.to_thread(transition)
            return PromotionResult(
                draft_id=draft_id, name=binding.name,
                revision=revision, source_sha256=binding.source_sha256,
            )

    def gateway_request(
        self, *, name: str, principal_id: str,
        arguments: dict[str, Any] | None = None,
        approval_id: str | None = None,
    ) -> MCPGatewayRequest:
        """Build a gateway request, not execute it or bypass authorization."""
        if principal_id != "local_owner":
            raise PromotionDenied("Only Local Owner may invoke activated skills")
        return self._registry.to_gateway_request(
            name, principal_id=principal_id,
            arguments=arguments, approval_id=approval_id,
        )
