"""#47/#73: AST architecture graph and reproducible experiment through real MCPGateway.

The fixture provider supplies bounded local data; these tests do not claim
production source trust, compiler-grade cross-language analysis or human study approval.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from aura_core.application.code_insight import (
    analyze_governed_python_repository, analyze_python_repository,
)
from aura_core.application.experiment_design import (
    design_balanced_experiment, formulate_hypothesis,
)
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
    RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.science.experiment_dataset import (
    analyze_experiment_with_design, analyze_governed_experiment,
    render_design_linked_experiment_markdown,
)

SOURCES = {
    "pkg.a": "import pkg.b\n\ndef public():\n    return 'SAFE'\n",
    "pkg.b": "import pkg.a\nimport pkg.missing\nx = 'UNTRUSTED STRING'\n",
}


def study_plan():
    hypothesis = formulate_hypothesis(
        independent_variable="light", dependent_variable="response",
        control_condition="off", treatment_condition="on",
        expected_direction="different",
    )
    return design_balanced_experiment(hypothesis, sample_size=6, seed=23)


def study_csv(plan):
    return "unit_id,group,measure\n" + "".join(
        f"{a.simulated_unit_id},{a.group},{i + 1}\n"
        for i, a in enumerate(plan.allocations)
    )


class FixtureSourceProvider:
    """Real MCPProvider protocol and Gateway dispatch, fixture *data* only."""

    def __init__(self, csv_text):
        self.calls = []
        self.csv_text = csv_text

    async def list_tools(self):
        return (
            MCPTool("fetch_repository", "Return fixture source", {
                "type": "object", "properties": {}, "additionalProperties": False,
            }),
            MCPTool("fetch_experiment", "Return fixture observations", {
                "type": "object", "properties": {}, "additionalProperties": False,
            }),
        )

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        if name == "fetch_repository":
            return {"sources": SOURCES}
        if name == "fetch_experiment":
            return {"csv_text": self.csv_text}
        raise ValueError("unknown fixture tool")


def real_gateway(*, allow=True):
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(name="group-a-source", version="1.0.0",
                          provider="mcp", category=ServiceCategory.MCP), object())
    providers = ProviderRegistry(services)
    provider = FixtureSourceProvider(study_csv(study_plan()))
    providers.register(
        ProviderDefinition(provider_id="test.group-a-source", name="Source Fixture",
                           version="1.0.0", service_id=service.service_id),
        provider,
    )
    caps = CapabilityRegistry(services)
    for tool, capability, category, scope in (
        ("fetch_repository", "aura.repo.sources.read", CapabilityCategory.RESEARCH,
         "repository/demo"),
        ("fetch_experiment", "aura.science.dataset.read", CapabilityCategory.RESEARCH,
         "science/demo"),
    ):
        caps.register(CapabilityDefinition(
            capability_id=capability, name=tool, version="1.0.0",
            description="test fixture, no production source trust",
            provider_id="test.group-a-source", provider_type=ProviderType.MCP,
            category=category, tool_name=tool, risk_level="low",
        ))
    engine = PermissionEngine(caps)
    if allow:
        for capability, scope in (("aura.repo.sources.read", "repository/demo"),
                                   ("aura.science.dataset.read", "science/demo")):
            engine.add_policy(PermissionPolicy(
                policy_id=capability, policy_version="1", principal_id="owner",
                capability_id=capability, operation_id=capability,
                resource_scope=scope, authorization_level=AuthorizationLevel.READ,
                decision=AuthorizationDecision.ALLOW,
            ))
    return MCPGateway(caps, providers, engine), provider, engine


def request(*, study=False, principal="owner"):
    capability = "aura.science.dataset.read" if study else "aura.repo.sources.read"
    tool = "fetch_experiment" if study else "fetch_repository"
    return MCPGatewayRequest(
        request_id=tool + "-" + principal, principal_id=principal,
        capability_id=capability, operation_id=capability,
        resource_scope="science/demo" if study else "repository/demo",
        risk_level=RiskLevel.LOW, tool_name=tool, arguments={},
    )


def test_python_cross_file_cycle_and_missing_import_are_deterministic():
    report = analyze_python_repository(SOURCES)
    assert report.local_edges == (("pkg.a", "pkg.b"), ("pkg.b", "pkg.a"))
    assert report.missing_local_modules == (("pkg.b", "pkg.missing"),)
    assert report.cycles == (("pkg.a", "pkg.b"),)
    assert len(report.graph_sha256) == 64
    assert report == analyze_python_repository(dict(reversed(list(SOURCES.items()))))
    assert not report.code_executed and not report.cross_language_compiler_verified
    assert not report.authorization_checked


def test_architecture_source_never_runs_and_rejects_unsafe_inputs(tmp_path):
    marker = tmp_path / "must-not-exist"
    malicious = f"import pathlib\npathlib.Path({str(marker)!r}).write_text('BAD')\n"
    graph = analyze_python_repository({"pkg.mal": malicious})
    assert not marker.exists()
    assert graph.module_ids == ("pkg.mal",)
    with pytest.raises(ValueError):
        analyze_python_repository({"../../escape": malicious})
    with pytest.raises(ValueError):
        analyze_python_repository({"valid": "def broken("})
    with pytest.raises(ValueError, match="budget"):
        analyze_python_repository({"valid": "x = 'a'\n" * 16000})


def test_experiment_design_link_rejects_tampered_allocations_and_forged_approval():
    plan = study_plan()
    csv = study_csv(plan)
    linked = analyze_experiment_with_design(csv, plan=plan, study_id="study-1")
    assert linked.report.sample_count == 6
    assert linked == analyze_experiment_with_design(csv, plan=plan, study_id="study-1")
    assert linked.design_sha256 == plan.plan_sha256
    assert linked.design_record_consistent
    assert not linked.actual_randomization_verified
    assert not linked.independent_scientific_review
    assert not linked.source_authenticated
    text = render_design_linked_experiment_markdown(linked)
    assert linked.design_sha256 in text
    assert linked.linkage_sha256 in text
    assert "NOT VERIFIED" in text
    with pytest.raises(ValueError, match="allocation"):
        analyze_experiment_with_design(
            csv.replace(",control,", ",treatment,", 1), plan=plan, study_id="study-1")
    with pytest.raises(ValueError, match="duplicate"):
        duplicated = csv.splitlines()
        duplicated[2] = duplicated[1]
        analyze_experiment_with_design(
            "\n".join(duplicated) + "\n", plan=plan, study_id="study-1")
    with pytest.raises(ValueError, match="non-canonical"):
        analyze_experiment_with_design(
            csv, plan=replace(plan, human_subjects_approved=True), study_id="study-1")


def test_real_gateway_authorizes_source_and_experiment_retrieval_and_denies_other():
    gateway, provider, engine = real_gateway()
    graph = asyncio.run(analyze_governed_python_repository(
        gateway=gateway, request=request(), principal_id="owner"))
    assert graph.cycles == (("pkg.a", "pkg.b"),)
    linked = asyncio.run(analyze_governed_experiment(
        gateway=gateway, request=request(study=True),
        principal_id="owner", plan=study_plan(), study_id="study-1"))
    assert linked.report.result["summary"]["count"] == 6
    assert provider.calls == ["fetch_repository", "fetch_experiment"]
    assert len(engine.audit_records()) == 2

    with pytest.raises(PermissionError):
        asyncio.run(analyze_governed_python_repository(
            gateway=gateway, request=request(), principal_id="attacker"))
    with pytest.raises(PermissionError):
        asyncio.run(analyze_governed_experiment(
            gateway=gateway, request=request(study=True),
            principal_id="attacker", plan=study_plan(), study_id="study-1"))
    assert len(provider.calls) == 2

    denied, no_calls, audit = real_gateway(allow=False)
    with pytest.raises(PermissionError, match="denied"):
        asyncio.run(analyze_governed_python_repository(
            gateway=denied, request=request(), principal_id="owner"))
    with pytest.raises(PermissionError, match="denied"):
        asyncio.run(analyze_governed_experiment(
            gateway=denied, request=request(study=True),
            principal_id="owner", plan=study_plan(), study_id="study-1"))
    assert no_calls.calls == []
    assert len(audit.audit_records()) == 2
