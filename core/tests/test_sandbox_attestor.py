"""Independent Ed25519 evidence, provenance binding and replay regressions."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution.sandbox_attestor import (
    DOMAIN, SCHEMA, AttestationReceiptRegistry, IndependentAttestationVerifier,
    SandboxClaims, SignedSandboxAttestation, canonical_claims,
)
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.kernel.capabilities import CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType
from aura_core.kernel.permissions import RiskLevel
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def example_binding(version: str = "1.0.0") -> SkillBinding:
    return SkillBinding(
        name="sample_skill", version=version, source_sha256=digest(b"python tool source"),
        capability_id="SampleCapability", provider_id="mcp.review", operation_id="read",
        tool_name="review_tool", resource_scope="sandbox:review",
        risk_level=RiskLevel.LOW,
    )


@pytest.fixture
def evidence():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    binding = example_binding()
    now = int(time.time())
    claims = SandboxClaims(
        source_sha256=binding.source_sha256,
        tests_sha256=digest(b"trusted tests"),
        image_digest="sha256:" + digest(b"oci image"),
        policy_sha256=digest(b"network:none readonly:true cap_drop:all"),
        binding_digest=binding.review_digest,
        run_id="runner-job-000001", runner_id="trusted-worker-01",
        issued_at=now-5, expires_at=now+240, exit_code=0, outcome="passed",
        network_disabled=True, rootfs_readonly=True,
    )

    def sign(claims=claims, signing_key=key):
        return SignedSandboxAttestation(
            key_id="trusted-attestor-01", claims=claims,
            signature_b64=base64.b64encode(signing_key.sign(DOMAIN+canonical_claims(claims))).decode(),
        )

    verifier = IndependentAttestationVerifier(
        trusted_public_keys={"trusted-attestor-01": public},
        expected_image_digest=claims.image_digest,
        expected_policy_sha256=claims.policy_sha256,
        expected_tests_sha256=claims.tests_sha256,
        trusted_runner_id=claims.runner_id,
    )
    return binding, key, claims, sign, verifier


def test_valid_attestation_roundtrip_and_receipt_accepted(evidence):
    binding, key, claims, sign, verifier = evidence
    attestation = sign()
    roundtrip = SignedSandboxAttestation.from_dict(json.loads(json.dumps(attestation.to_dict())))
    assert roundtrip == attestation
    assert verifier.verify(roundtrip, source_sha256=binding.source_sha256,
                           binding_digest=binding.review_digest)
    store = AttestationReceiptRegistry(verifier)
    receipt = store.register(roundtrip, source_sha256=binding.source_sha256,
                             binding_digest=binding.review_digest)
    assert len(receipt) == 64
    assert store.verify_binding(binding, receipt)
    assert not store.verify_binding(example_binding("1.0.1"), receipt)
    assert not store.verify_binding(binding, "unknown")


@pytest.mark.parametrize("field,replacement", [
    ("source_sha256", digest(b"malicious version")),
    ("tests_sha256", digest(b"different test suite")),
    ("image_digest", "sha256:" + digest(b"different image")),
    ("policy_sha256", digest(b"network:on")),
    ("binding_digest", digest(b"different MCP scope")),
    ("runner_id", "untrusted-runner"),
    ("network_disabled", False),
    ("rootfs_readonly", False),
    ("exit_code", 1),
    ("outcome", "failed"),
])
def test_tampered_signed_claims_fail_closed(evidence, field, replacement):
    binding, _, claims, sign, verifier = evidence
    with pytest.raises(ValueError) if field in {"network_disabled", "rootfs_readonly", "exit_code", "outcome"} else _nullcontext():
        tampered = replace(claims, **{field: replacement})
    if field not in {"network_disabled", "rootfs_readonly", "exit_code", "outcome"}:
        untrusted = SignedSandboxAttestation(key_id="trusted-attestor-01",
            claims=tampered, signature_b64=sign().signature_b64)
        assert not verifier.verify(untrusted, source_sha256=binding.source_sha256,
                                   binding_digest=binding.review_digest)


class _nullcontext:
    def __enter__(self): return self
    def __exit__(self, typ, value, tb): return False


def test_signed_but_wrong_digest_policy_or_runner_rejected(evidence):
    binding, _, claims, sign, verifier = evidence
    for modification in (
        {"tests_sha256": digest(b"another tests")},
        {"image_digest": "sha256:"+digest(b"mutable image")},
        {"policy_sha256": digest(b"allow network")},
        {"runner_id": "attacker-runner"},
        {"binding_digest": digest(b"new capabilities")},
    ):
        wrong = replace(claims, **modification)
        att = sign(wrong)  # even signed with the trusted key -> policy denies
        assert not verifier.verify(att, source_sha256=binding.source_sha256,
                                   binding_digest=binding.review_digest)


def test_wrong_signer_key_and_unknown_key_id_rejected(evidence):
    binding, _, claims, sign, verifier = evidence
    attacker_key = Ed25519PrivateKey.generate()
    assert not verifier.verify(sign(signing_key=attacker_key),
                               source_sha256=binding.source_sha256,
                               binding_digest=binding.review_digest)
    wrong_id = replace(sign(), key_id="untrusted-attestor")
    assert not verifier.verify(wrong_id, source_sha256=binding.source_sha256,
                               binding_digest=binding.review_digest)


def test_expired_not_yet_valid_or_extended_expiry_rejected(evidence):
    binding, _, claims, sign, verifier = evidence
    assert not verifier.verify(sign(), source_sha256=binding.source_sha256,
                               binding_digest=binding.review_digest, now=claims.expires_at)
    assert not verifier.verify(sign(), source_sha256=binding.source_sha256,
                               binding_digest=binding.review_digest, now=claims.issued_at-31)
    with pytest.raises(ValueError):
        replace(claims, expires_at=claims.issued_at+901)
    with pytest.raises(ValueError):
        replace(claims, issued_at=claims.expires_at)


def test_duplicate_job_and_registration_replays_rejected(evidence):
    binding, _, claims, sign, verifier = evidence
    ledger = AttestationReceiptRegistry(verifier)
    receipt = ledger.register(sign(), source_sha256=binding.source_sha256,
                              binding_digest=binding.review_digest)
    assert ledger.verify_binding(binding, receipt)
    with pytest.raises(PermissionError, match="already registered"):
        ledger.register(sign(), source_sha256=binding.source_sha256,
                        binding_digest=binding.review_digest)
    reused_job = replace(claims, source_sha256=digest(b"another code"))
    with pytest.raises(PermissionError):
        ledger.register(sign(reused_job), source_sha256=reused_job.source_sha256,
                        binding_digest=binding.review_digest)


def test_strict_schema_and_signature_base64(evidence):
    binding, _, claims, sign, verifier = evidence
    bad = sign().to_dict()
    bad["extra"] = "untrusted"
    with pytest.raises(ValueError):
        SignedSandboxAttestation.from_dict(bad)
    bad = sign().to_dict()
    bad["claims"]["untrusted"] = "injection"
    with pytest.raises(ValueError):
        SignedSandboxAttestation.from_dict(bad)
    bad = replace(sign(), signature_b64="***")
    assert not verifier.verify(bad, source_sha256=binding.source_sha256,
                               binding_digest=binding.review_digest)
    with pytest.raises(ValueError):
        IndependentAttestationVerifier(
            trusted_public_keys={}, expected_image_digest=claims.image_digest,
            expected_policy_sha256=claims.policy_sha256,
            expected_tests_sha256=claims.tests_sha256,
            trusted_runner_id=claims.runner_id,
        )


def test_governed_registry_signed_verification_fails_closed(evidence):
    binding, _, claims, sign, verifier = evidence
    services = ServiceRegistry()
    service = ServiceDefinition(name="mcp", version="1", provider="attested-test",
                                category=ServiceCategory.MCP)
    services.register(service, object())
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="mcp.review", name="AttestedTest", version="1", service_id=service.service_id,
    ), object())
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id=binding.capability_id, name="Test", version="1", description="Test tool",
        provider_id=binding.provider_id, provider_type=ProviderType.MCP,
        category=CapabilityCategory.DIAGNOSTICS,
        tool_name=binding.tool_name, risk_level=binding.risk_level.value,
    ))
    attestor = AttestationReceiptRegistry(verifier)
    allow_owner = {"allowed": False}
    registry = GovernedSkillRegistry(
        capabilities=caps, providers=providers,
        validation_verifier=lambda source, receipt: True,  # lax legacy hook
        signed_attestation_verifier=attestor.verify_binding,  # hardened gate
        owner_receipt_consumer=lambda principal, op, d, receipt: allow_owner["allowed"],
    )
    registry.stage(binding)
    with pytest.raises(PermissionError, match="Signed attestation"):
        registry.validate(binding.name, sandbox_receipt="unsigned-smoke")
    receipt = attestor.register(sign(), source_sha256=binding.source_sha256,
                                binding_digest=binding.review_digest)
    assert registry.validate(binding.name, sandbox_receipt=receipt)
    with pytest.raises(PermissionError):
        registry.activate(binding.name, principal_id="local_owner", owner_receipt="missing")
    assert registry.catalog() == ()
    allow_owner["allowed"] = True
    registry.activate(binding.name, principal_id="local_owner", owner_receipt="owner-approved")
    assert registry.catalog()[0]["name"] == binding.name
    # A cryptographic attestation does not grant a new MCP capability.
    assert registry.to_gateway_request(binding.name, principal_id="local_owner").capability_id == binding.capability_id


def test_external_signer_uses_protected_files_not_source_tree(evidence, tmp_path):
    import importlib.util
    source = Path(__file__).resolve().parents[1] / "scripts" / "evolution_attestor_sign.py"
    spec = importlib.util.spec_from_file_location("trusted_attestor_cli", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binding, key, claims, _, verifier = evidence
    observation = tmp_path / "observed.json"
    keyfile = tmp_path / "private.pem"
    observation.write_text(json.dumps(asdict(claims)))
    keyfile.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    observation.chmod(0o600)
    keyfile.chmod(0o600)
    signed = module.sign_observation(
        observation=observation, private_key=keyfile, key_id="trusted-attestor-01",
    )
    assert verifier.verify(signed, source_sha256=binding.source_sha256,
                           binding_digest=binding.review_digest)
    with pytest.raises(PermissionError):
        module.sign_observation(
            observation=source, private_key=keyfile, key_id="trusted-attestor-01",
        )
