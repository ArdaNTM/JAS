"""Offline Stage D hardware, pinned proxy and signed promotion acceptance.

All cryptographic private keys here are ephemeral TEST FIXTURES. Passing this
suite does NOT mean a physical Windows Hello assertion, live microphone, VM
benchmark, OS firewall or external sandbox signer was tested in production.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import sqlite3
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.acceptance.hardware_gate import (
    HardwareAcceptanceGate, HardwareCheck, HardwareThresholds,
    PinnedEd25519HardwareVerifier, SignedHardwareEvidence,
)
from aura_core.network_egress.policy import (
    EgressDenied, EgressPolicy, PinnedConnectProxy, canonical_hostname,
)
from aura_core.evolution.trusted_promotion import (
    PromotionDenied, TrustedPromotionBridge,
)
from aura_core.evolution.evolution_gateway import EvolutionReviewGateway
from aura_core.evolution.durable_attestation import DurableAttestationReceiptRegistry
from aura_core.evolution.owner_receipt import (
    DurableOwnerReceiptConsumer, OwnerReceiptIssuer,
)
from aura_core.evolution.sandbox_attestor import (
    DOMAIN as SANDBOX_DOMAIN, SandboxClaims, SignedSandboxAttestation,
    IndependentAttestationVerifier, canonical_claims,
)
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.application.self_tool_synthesis import ToolCandidate
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.events import EventBus
from aura_core.kernel.capabilities import (
    CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine,
    PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )


def metrics(check: HardwareCheck) -> dict[str, float]:
    return {
        HardwareCheck.WEBAUTHN_UV: {
            "uv_flag_verified": 1, "exact_origin_verified": 1,
            "challenge_replay_rejected": 1, "platform_authenticator": 1,
        },
        HardwareCheck.MICROPHONE_LATENCY: {
            "p50_ms": 45, "p95_ms": 90, "sample_count": 50,
        },
        HardwareCheck.VOICE_BARGE_IN: {
            "p50_ms": 85, "p95_ms": 120, "sample_count": 50,
        },
        HardwareCheck.HUD_MULTIMONITOR: {
            "monitor_count": 2, "mixed_dpi_verified": 1, "display_hotplug_verified": 1,
        },
        HardwareCheck.HUD_NEGATIVE_COORDINATES: {
            "negative_virtual_x_observed": 1, "hit_test_verified": 1,
            "click_through_verified": 1,
        },
        HardwareCheck.EMERGENCY_STOP: {
            "no_new_dispatch_after_kill": 1, "restart_stays_killed": 1,
            "p95_ms": 100,
        },
    }[check]


def make_evidence(
    key: Ed25519PrivateKey, run_id: str, check: HardwareCheck,
    *, override: dict[str, float] | None = None, timestamp: int | None = None,
) -> SignedHardwareEvidence:
    sample = SignedHardwareEvidence(
        run_id=run_id, check=check, signer_id="physical-lab",
        device_digest=sha(b"one-physical-device"), timestamp=timestamp or int(time.time()),
        nonce=uuid4().hex, metrics=override if override is not None else metrics(check),
        signature_b64="AA==",
    )
    signature = base64.b64encode(key.sign(sample.signing_payload())).decode("ascii")
    return replace(sample, signature_b64=signature)


def test_signed_hardware_evidence_accepts_complete_test_fixture_only() -> None:
    async def exercise() -> None:
        key = Ed25519PrivateKey.generate()
        verifier = PinnedEd25519HardwareVerifier(
            trusted_public_keys={"physical-lab": public(key)},
        )
        run_id = str(uuid4())
        proofs = tuple(make_evidence(key, run_id, check) for check in HardwareCheck)
        gate = HardwareAcceptanceGate(verifier=verifier)
        report = await gate.assess(run_id=run_id, evidence=proofs)
        assert report.accepted and report.independently_signed
        assert report.checked == len(HardwareCheck)
        assert not hasattr(report, "release_lock_modified")

        missing = await gate.assess(run_id=run_id, evidence=proofs[:-1])
        assert not missing.accepted
        # A changed field or new signer cannot reuse a previously valid proof.
        tampered = replace(proofs[0], metrics={**metrics(HardwareCheck.WEBAUTHN_UV),
                                               "exact_origin_verified": 0})
        assert not (await gate.assess(
            run_id=run_id, evidence=(tampered,) + proofs[1:]
        )).accepted
        forged = make_evidence(Ed25519PrivateKey.generate(), run_id, proofs[0].check)
        assert (await gate.assess(run_id=run_id, evidence=(forged,) + proofs[1:])
                ).reason == "signature_rejected"
        stale = make_evidence(key, run_id, proofs[0].check, timestamp=int(time.time()) - 4000)
        assert (await gate.assess(run_id=run_id, evidence=(stale,) + proofs[1:])
                ).reason == "stale_or_repeated"
        exceeded = make_evidence(
            key, run_id, HardwareCheck.MICROPHONE_LATENCY,
            override={"p50_ms": 50, "p95_ms": 101, "sample_count": 50},
        )
        assert (await gate.assess(
            run_id=run_id, evidence=(exceeded,) + proofs[1:]
        )).reason == "measurement_failed"
        duplicates = (proofs[0],) + proofs[1:-1] + (proofs[0],)
        assert not (await gate.assess(run_id=run_id, evidence=duplicates)).accepted
    asyncio.run(exercise())


def test_hardware_thresholds_never_assert_biometrics_or_live_microphone() -> None:
    with pytest.raises(ValueError):
        HardwareThresholds(first_audio_p95_ms=float("nan"))
    with pytest.raises(ValueError):
        HardwareThresholds(minimum_audio_samples=0)
    with pytest.raises(ValueError):
        SignedHardwareEvidence(
            run_id=str(uuid4()), check=HardwareCheck.WEBAUTHN_UV,
            signer_id="physical-lab", device_digest=sha(b"device"),
            timestamp=int(time.time()), nonce=uuid4().hex,
            metrics={"uv_flag_verified": float("inf")}, signature_b64="AA==",
        )


@pytest.mark.parametrize("host", [
    "localhost", "127.0.0.1", "localhost.localdomain", "example.org.local",
    "example.org.internal", "example.org.test", "EXAMPLE.ORG", "example.org.",
    "http://example.org", "example.org:443", "example..org",
    "user@example.org", "foo-.org", "_meta.example.org",
])
def test_rejects_noncanonical_hostnames(host: str) -> None:
    with pytest.raises(EgressDenied):
        canonical_hostname(host)


def test_egress_policy_pins_public_addresses_and_denies_rebinding() -> None:
    policy = EgressPolicy(frozenset({"example.org"}))
    approved = policy.authorize(
        hostname="example.org", port=443, resolved_addresses=["8.8.8.8", "1.1.1.1"],
    )
    assert approved.addresses == ("1.1.1.1", "8.8.8.8")
    policy.require_pinned_peer(approved, "1.1.1.1")
    with pytest.raises(EgressDenied):
        policy.require_pinned_peer(approved, "9.9.9.9")
    for answers in [
        ["8.8.8.8", "127.0.0.1"], ["::1"], ["10.0.0.3"],
        ["169.254.169.254"], ["192.168.1.10"], ["8.8.8.8", "fc00::1"],
        [],
    ]:
        with pytest.raises(EgressDenied):
            policy.authorize(
                hostname="example.org", port=443, resolved_addresses=answers,
            )
    with pytest.raises(EgressDenied):
        policy.authorize(
            hostname="another.org", port=443, resolved_addresses=["8.8.8.8"],
        )
    with pytest.raises(EgressDenied):
        policy.authorize(
            hostname="example.org", port=80, resolved_addresses=["8.8.8.8"],
        )


def test_proxy_authentication_connect_contract_and_private_dns_denial() -> None:
    class PrivateResolver:
        async def resolve(self, hostname: str) -> tuple[str, ...]:
            assert hostname == "example.org"
            return ("169.254.169.254",)

    async def exercise() -> None:
        policy = EgressPolicy(frozenset({"example.org"}))
        token = "e" * 64
        proxy = PinnedConnectProxy(policy=policy, token=token, resolver=PrivateResolver())
        valid_header = base64.b64encode(("aura:" + token).encode()).decode()
        connect = (
            "CONNECT example.org:443 HTTP/1.1\r\n"
            "Host: example.org:443\r\n"
            f"Proxy-Authorization: Basic {valid_header}\r\n\r\n"
        )
        assert proxy._parse(connect.encode()) == "example.org"
        for malformed in [
            connect.replace("CONNECT ", "GET "),
            connect.replace("example.org:443", "example.org:80"),
            connect.replace(valid_header, base64.b64encode(b"aura:wrong").decode()),
            connect.replace("Host: example.org:443", "Host: another.org:443"),
            connect.replace("\r\n\r\n", "\r\nContent-Length: 1\r\n\r\n"),
        ]:
            with pytest.raises(EgressDenied):
                proxy._parse(malformed.encode())
        port = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(connect.encode())
            await writer.drain()
            result = await asyncio.wait_for(reader.read(512), timeout=3)
            assert b"403 Forbidden" in result
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
    asyncio.run(exercise())


def _private_sqlite(directory: Path, name: str) -> Path:
    path = directory / name
    sqlite3.connect(path).close()
    path.chmod(0o600)
    from aura_core.evolution.windows_owner_storage import harden_private_acl
    harden_private_acl(path)
    return path


def test_trusted_promotion_requires_exact_signed_receipts_and_preinstalled_gateway(
    tmp_path: Path, owner_private_dir: Path,
) -> None:
    async def exercise() -> None:
        checkout = tmp_path / "checkout"
        (checkout / "core/src/aura_core").mkdir(parents=True)
        review_dir = owner_private_dir / "quarantine"
        review_dir.mkdir(mode=0o700)
        if __import__("os").name == "nt":
            from aura_core.evolution.windows_owner_storage import harden_private_acl
            harden_private_acl(review_dir)
        gate = EvolutionReviewGateway(
            directory=review_dir, checkout_root=checkout, event_bus=EventBus(),
        )
        candidate = ToolCandidate(
            tool_name="safe_reader", description="Test-owned pure identity candidate",
            source_code="def run(data):\n    return data\n",
            input_schema={"type": "object"}, output_schema={"type": "object"},
        )
        draft = gate.stage(candidate, test_count=1)

        services = ServiceRegistry()
        service = ServiceDefinition(
            name="mcp", version="1", provider="review", category=ServiceCategory.MCP,
        )
        services.register(service, object())
        providers = ProviderRegistry(services)
        providers.register(ProviderDefinition(
            provider_id="review.mcp", name="Existing MCP", version="1",
            service_id=service.service_id,
        ), object())
        caps = CapabilityRegistry(services)
        caps.register(CapabilityDefinition(
            capability_id="ReviewedTool", name="Pre-registered", version="1",
            description="Existing capability", provider_id="review.mcp",
            provider_type=ProviderType.MCP, category=CapabilityCategory.DIAGNOSTICS,
            tool_name="safe_read", risk_level="low",
        ))
        caps.register(CapabilityDefinition(
            capability_id="GovernedSkillActivation", name="Owner", version="1",
            description="Signed Owner approval", provider_id="review.mcp",
            provider_type=ProviderType.MCP, category=CapabilityCategory.SECURITY,
            tool_name="owner_review", risk_level="critical",
        ))
        binding = SkillBinding(
            name="safe_reader", version="1.0.0",
            source_sha256=draft.source_sha256, capability_id="ReviewedTool",
            provider_id="review.mcp", operation_id="read",
            tool_name="safe_read", resource_scope="diagnostic:public",
            risk_level=RiskLevel.LOW,
        )
        permissions = PermissionEngine(caps)
        permissions.add_policy(PermissionPolicy(
            policy_id="owner:activate:test", policy_version="1",
            principal_id="local_owner", capability_id="GovernedSkillActivation",
            operation_id="activate",
            resource_scope="evolution:skill:" + binding.review_digest,
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
            decision=AuthorizationDecision.REQUIRE_APPROVAL,
        ))

        owner_key = Ed25519PrivateKey.generate()
        owner_policy = sha(b"test-owner-policy")
        owner_ledger = _private_sqlite(owner_private_dir, "owner.sqlite3")
        owner = DurableOwnerReceiptConsumer(
            trusted_public_keys={"owner-test": public(owner_key)},
            policy_digest=owner_policy, permissions=permissions, ledger_path=owner_ledger,
        )
        attestor_key = Ed25519PrivateKey.generate()
        image = "sha256:" + sha(b"immutable sandbox image")
        policy_sha, tests_sha = sha(b"sandbox policy"), sha(b"test suite")
        verifier = IndependentAttestationVerifier(
            trusted_public_keys={"attestor-test": public(attestor_key)},
            expected_image_digest=image, expected_policy_sha256=policy_sha,
            expected_tests_sha256=tests_sha, trusted_runner_id="independent-lab",
        )
        evidence_db = _private_sqlite(owner_private_dir, "attestations.sqlite3")
        attestor = DurableAttestationReceiptRegistry(
            database_path=evidence_db, verifier=verifier,
        )
        now = int(time.time())
        claims = SandboxClaims(
            source_sha256=binding.source_sha256, tests_sha256=tests_sha,
            image_digest=image, policy_sha256=policy_sha,
            binding_digest=binding.review_digest, run_id="sandbox-test-run-123456",
            runner_id="independent-lab", issued_at=now, expires_at=now + 300,
            exit_code=0, outcome="passed", network_disabled=True,
            rootfs_readonly=True,
        )
        envelope = SignedSandboxAttestation(
            key_id="attestor-test", claims=claims,
            signature_b64=base64.b64encode(
                attestor_key.sign(SANDBOX_DOMAIN + canonical_claims(claims))
            ).decode("ascii"),
        )
        sandbox_receipt = attestor.register(
            envelope, source_sha256=binding.source_sha256,
            binding_digest=binding.review_digest,
        )
        registry = GovernedSkillRegistry(
            capabilities=caps, providers=providers,
            validation_verifier=lambda source, receipt:
                source == binding.source_sha256 and receipt == sandbox_receipt,
            owner_receipt_consumer=owner,
            signed_attestation_verifier=attestor.verify_binding,
        )
        bridge = TrustedPromotionBridge(
            review_gateway=gate, registry=registry,
            owner_receipts=owner, attestations=attestor,
        )
        with SQLiteApprovalStore(":memory:") as approvals:
            request = approvals.create(
                principal_id="local_owner", capability_id="GovernedSkillActivation",
                operation_id="activate",
                resource_scope="evolution:skill:" + binding.review_digest,
                request_fingerprint=binding.review_digest,
                policy_digest=owner_policy,
            )
            approved = approvals.decide(
                request.approval_id, expected_version=request.version,
                approver_id="human:local-owner", decision=ApprovalStatus.APPROVED,
            )
            signed_owner = OwnerReceiptIssuer(
                key_id="owner-test", private_key=owner_key, policy_digest=owner_policy,
            ).issue(approved)
        try:
            with pytest.raises(PromotionDenied):
                await bridge.activate_preinstalled(
                    draft_id=draft.draft_id, binding=binding,
                    principal_id="untrusted_agent", owner_receipt=signed_owner,
                    sandbox_receipt=sandbox_receipt,
                )
            with pytest.raises(PromotionDenied):
                await bridge.activate_preinstalled(
                    draft_id=draft.draft_id, binding=binding,
                    principal_id="local_owner", owner_receipt=signed_owner,
                    sandbox_receipt="0" * 64,
                )
            result = await bridge.activate_preinstalled(
                draft_id=draft.draft_id, binding=binding, principal_id="local_owner",
                owner_receipt=signed_owner, sandbox_receipt=sandbox_receipt,
            )
            assert result.revision
            assert not result.generated_source_imported
            assert not result.release_lock_modified
            assert not result.provider_registry_mutated
            req = bridge.gateway_request(name="safe_reader", principal_id="local_owner")
            assert req.capability_id == "ReviewedTool"
            assert req.tool_name == "safe_read"
            assert registry.catalog()[0]["source_sha256"] == draft.source_sha256
            with pytest.raises(PermissionError):
                await bridge.activate_preinstalled(
                    draft_id=draft.draft_id, binding=binding,
                    principal_id="local_owner", owner_receipt=signed_owner,
                    sandbox_receipt=sandbox_receipt,
                )
            # Review artifact tampering cannot be made valid by any receipt.
            (review_dir / f"{draft.draft_id}.review.py.txt").write_text(
                "def run(data):\n    return {'forged': 1}\n", encoding="utf-8",
            )
            with pytest.raises(PermissionError):
                await bridge.activate_preinstalled(
                    draft_id=draft.draft_id, binding=binding,
                    principal_id="local_owner", owner_receipt=signed_owner,
                    sandbox_receipt=sandbox_receipt,
                )
        finally:
            attestor.close()
            owner.close()
    asyncio.run(exercise())
