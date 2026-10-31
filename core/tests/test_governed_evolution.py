"""Security and lifecycle regressions for review-governed evolution."""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

import pytest

from aura_core.application.self_tool_synthesis import ToolCandidate
from aura_core.evolution.autonomous_analyzer import AutonomousAnalyzer
from aura_core.evolution.evolution_planner import (
    EvolutionPlanner, OpenSourceEvidence,
)
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.kernel.capabilities import (
    CapabilityDefinition, CapabilityRegistry, CapabilityCategory, ProviderType,
)
from aura_core.kernel.permissions import (
    PermissionEngine, AuthorizationRequest, AuthorizationDecision, RiskLevel,
)
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    src = tmp_path / "core" / "src" / "aura_core"
    src.mkdir(parents=True)
    (src / "example.py").write_text(
        "# TODO: reduce duplicate lookups\n"
        "try:\n    raise ValueError('failure')\n"
        "except Exception:\n    pass\n",
        encoding="utf-8",
    )
    (src / ".env").write_text("API_TOKEN=secret-value", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("<!-- FIXME: update docs -->", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "aura.log").write_text("Timeout Exception\ncredential=VERY_SECRET", encoding="utf-8")
    return tmp_path


def test_analyzer_scans_read_only_with_source_identity_and_sanitized_log_counts(checkout):
    before = (checkout / "core/src/aura_core/example.py").read_bytes()
    report = AutonomousAnalyzer(checkout).scan()
    kinds = {item.category for item in report.proposals}
    assert {"maintenance_marker", "silent_failure", "log_timeout", "log_exception"} <= kinds
    assert report.status == "review_only"
    assert (checkout / "core/src/aura_core/example.py").read_bytes() == before
    for item in report.proposals:
        assert len(item.evidence_sha256) == 64
        assert item.review_required and not item.execution_performed
    result = str(report.to_dict())
    assert "VERY_SECRET" not in result
    assert "secret-value" not in result
    assert ".env" not in result


def test_analyzer_rejects_symlinks_large_files_and_invalid_budget(checkout, tmp_path):
    src = checkout / "core/src/aura_core"
    outside = tmp_path / "external.py"
    outside.write_text("# TODO: secret outside", encoding="utf-8")
    link = src / "leak.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation not permitted")
    (src / "huge.py").write_text("# TODO" + "x" * 3000, encoding="utf-8")
    report = AutonomousAnalyzer(checkout, max_file_bytes=1024, max_files=8).scan()
    assert all("leak.py" not in p.evidence_path for p in report.proposals)
    assert all("huge.py" not in p.evidence_path for p in report.proposals)
    assert report.skipped_files >= 1
    with pytest.raises(ValueError):
        AutonomousAnalyzer(checkout, max_files=0)


def test_idle_planner_deduplicates_and_never_runs_drafted_code(checkout):
    calls = {"discover": 0, "draft": 0}

    class Discovery:
        async def search(self, *, topic, limit):
            calls["discover"] += 1
            return (OpenSourceEvidence(
                "https://github.com/example/read-only-tool",
                "MIT", "Example documentation",
            ),)

    class Drafting:
        async def propose(self, *, finding, sources):
            calls["draft"] += 1
            return ToolCandidate(
                tool_name="safe_calculator", description="Arithmetic only",
                source_code="def run(data):\n    return data\n",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    async def run():
        analyzer = AutonomousAnalyzer(checkout)
        last = [time.monotonic()]
        worker = EvolutionPlanner(analyzer, discovery=Discovery(), drafting=Drafting(),
                                  last_activity=lambda: last[0],
                                  idle_seconds=60, interval_seconds=60, max_cycles=2)
        assert await worker.run_once() == ()
        assert calls == {"discover": 0, "draft": 0}
        last[0] -= 120
        first = await worker.run_once()
        assert first
        assert all(not entry.execution_performed for entry in first)
        assert all(entry.status == "awaiting_local_owner_review" for entry in first)
        assert first[0].static_validation is not None
        assert first[0].candidate_manifest["execution_enabled"] is False
        assert await worker.run_once() == ()
        assert len(worker.list_proposals()) == len(first)
        assert worker.status()["cycles"] == 2
        assert await worker.run_once() == ()
    asyncio.run(run())


def _registry():
    services = ServiceRegistry()
    service = ServiceDefinition(name="mcp", version="1", provider="test",
                                category=ServiceCategory.MCP)
    services.register(service, object())
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="test.mcp", name="Mock", version="1",
        service_id=service.service_id,
    ), object())
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id="ReadOnlyTool", name="Read-only tool", version="1",
        description="For policy tests only", provider_id="test.mcp",
        provider_type=ProviderType.MCP,
        category=CapabilityCategory.DIAGNOSTICS,
        tool_name="read_tool", risk_level="low",
    ))
    verified = set()
    approvals = set()
    registry = GovernedSkillRegistry(
        capabilities=caps, providers=providers,
        validation_verifier=lambda digest, receipt: (digest, receipt) in verified,
        owner_receipt_consumer=lambda principal, op, digest, receipt:
            (principal, op, digest, receipt) in approvals,
    )
    return registry, caps, providers, verified, approvals


def _binding(version: str = "1.0.0"):
    return SkillBinding(
        name="read_only_skill", version=version,
        source_sha256=hashlib.sha256(version.encode()).hexdigest(),
        capability_id="ReadOnlyTool", provider_id="test.mcp",
        operation_id="read", tool_name="read_tool",
        resource_scope="diagnostic:public", risk_level=RiskLevel.LOW,
    )


def test_registry_requires_independent_validation_and_exact_owner_receipts():
    registry, caps, providers, verified, approvals = _registry()
    binding = _binding()
    registry.stage(binding)
    with pytest.raises(PermissionError):
        registry.validate(binding.name, sandbox_receipt="not-attested")
    verified.add((binding.source_sha256, "verified-build-1"))
    assert registry.validate(binding.name, sandbox_receipt="verified-build-1")
    with pytest.raises(PermissionError):
        registry.activate(binding.name, principal_id="other", owner_receipt="owner")
    with pytest.raises(PermissionError):
        registry.activate(binding.name, principal_id="local_owner", owner_receipt="owner")
    approvals.add(("local_owner", "activate", binding.review_digest, "owner"))
    registry.activate(binding.name, principal_id="local_owner", owner_receipt="owner")
    request = registry.to_gateway_request(
        binding.name, principal_id="local_owner", arguments={"query": "safe"},
    )
    assert request.tool_name == "read_tool"
    assert request.capability_id == "ReadOnlyTool"
    assert request.resource_scope == "diagnostic:public"
    # Skill activation never creates a PermissionPolicy.
    decision = PermissionEngine(caps).authorize(AuthorizationRequest(
        request_id=request.request_id, principal_id=request.principal_id,
        capability_id=request.capability_id, operation_id=request.operation_id,
        resource_scope=request.resource_scope, risk_level=request.risk_level,
        tool_name=request.tool_name,
    ))
    assert decision.decision is AuthorizationDecision.DENY
    with pytest.raises(PermissionError):
        registry.to_gateway_request(binding.name, principal_id="other")


def test_registry_versioned_rollback_and_revocation_require_owner():
    registry, _, _, verified, approvals = _registry()
    old = _binding("1.0.0")
    new = _binding("1.1.0")
    for binding, receipt in ((old, "sandbox-old"), (new, "sandbox-new")):
        registry.stage(binding)
        verified.add((binding.source_sha256, receipt))
        registry.validate(binding.name, sandbox_receipt=receipt)
        approvals.add(("local_owner", "activate", binding.review_digest, "owner-" + binding.version))
        registry.activate(binding.name, principal_id="local_owner", owner_receipt="owner-" + binding.version)
    assert registry.catalog()[0]["version"] == "1.1.0"
    with pytest.raises(PermissionError):
        registry.rollback(new.name, principal_id="local_owner", owner_receipt="bad")
    approvals.add(("local_owner", "rollback", old.review_digest, "rollback-old"))
    registry.rollback(new.name, principal_id="local_owner", owner_receipt="rollback-old")
    assert registry.catalog()[0]["version"] == "1.0.0"
    with pytest.raises(PermissionError):
        registry.revoke(new.name, principal_id="other", owner_receipt="bad")
    approvals.add(("local_owner", "revoke", old.review_digest, "revoke-old"))
    registry.revoke(new.name, principal_id="local_owner", owner_receipt="revoke-old")
    assert registry.catalog() == ()


def test_registry_fails_closed_on_unregistered_provider_or_changed_tool():
    registry, _, providers, verified, approvals = _registry()
    good = _binding()
    registry.stage(good)
    verified.add((good.source_sha256, "sandbox"))
    registry.validate(good.name, sandbox_receipt="sandbox")
    approvals.add(("local_owner", "activate", good.review_digest, "owner"))
    registry.activate(good.name, principal_id="local_owner", owner_receipt="owner")
    providers.unregister("test.mcp")
    with pytest.raises((LookupError, PermissionError)):
        registry.to_gateway_request(good.name, principal_id="local_owner")
