"""Real registry-backed declarative skill proposal and fail-closed promotion tests."""
from dataclasses import FrozenInstanceError

import pytest

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition
from aura_core.learning.governed_skill_proposals import GovernedSkillProposalBuilder, SkillProposalDenied
from aura_core.learning.skill_library import SkillLibrary, Skill
from aura_core.learning.skill_validation import SkillValidator, ValidationSeverity


def _setup(*, risk="low", category=CapabilityCategory.RESEARCH, provider_type=ProviderType.MCP):
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(name="research-mcp", provider="mcp", version="1.0.0",
                          category=ServiceCategory.MCP), object(),
    )
    providers = ProviderRegistry(services)
    providers.register(
        ProviderDefinition(provider_id="mcp:research", name="research", version="1.0.0",
                           service_id=service.service_id), object(),
    )
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id="internet.search", name="Public research", version="1.0.0",
        description="Read public sources",
        provider_id=service.service_id if provider_type is ProviderType.SERVICE else "mcp:research",
        provider_type=provider_type, category=category, risk_level=risk, tool_name="search",
    ))
    return caps, providers


def _builder(**opts):
    caps, providers = _setup(**opts)
    return GovernedSkillProposalBuilder(
        caps, allowed_operations={"internet.search": ("internet.search",)},
    ), caps, providers


def _step(arguments=None, **overrides):
    item = {"capability_id": "internet.search", "operation_id": "internet.search",
            "arguments": {"query": "public sources"} if arguments is None else arguments}
    item.update(overrides)
    return item


def test_registered_low_risk_whitelist_yields_disabled_nonpromotable_candidate():
    builder, caps, providers = _builder()
    preview = builder.preview(
        name="Gather evidence", description="Read available public sources",
        steps=[_step({"query": "public sources", "limit": 3, "required": True})],
    )
    assert preview.status == "CANDIDATE_UNVERIFIED"
    assert preview.authority == "NO_EXECUTION_OR_PROMOTION"
    assert preview.steps[0].tool_name == "search"
    assert preview.steps[0].provider_id == "mcp:research"
    assert preview.steps[0].arguments == (("limit", 3), ("query", "public sources"), ("required", True))
    candidate = preview.to_unapproved_candidate()
    assert isinstance(candidate, Skill)
    assert candidate.enabled is False and candidate.confidence == 0
    assert candidate.source_run_ids == []
    assert candidate.success_count == candidate.failure_count == 0
    assert candidate.steps[0].capability_id == "internet.search"
    assert candidate.steps[0].operation_id == "internet.search"
    assert candidate.steps[0].arguments_template == dict(preview.steps[0].arguments)
    assert not candidate.can_execute()
    findings = SkillValidator().validate_structure(candidate)
    assert any(f.code == "NO_PROVENANCE" and f.severity is ValidationSeverity.ERROR for f in findings)
    assert len(caps.records()) == 1 and len(providers.records()) == 1


def test_preview_deterministic_and_does_not_share_caller_argument_state():
    builder, *_ = _builder()
    raw = _step({"query": "drought"})
    first = builder.preview(name="Read sources", description="Public climate evidence", steps=[raw])
    raw["arguments"]["query"] = "attack"
    second = builder.preview(name="Read sources", description="Public climate evidence",
                             steps=[_step({"query": "drought"})])
    assert first == second
    assert first.skill_id == SkillLibrary.make_id("Read sources", "Public climate evidence")
    with pytest.raises(FrozenInstanceError):
        first.status = "PROMOTED"
    candidate = first.to_unapproved_candidate()
    candidate.steps[0].arguments_template["query"] = "changed"
    assert first.steps[0].arguments == (("query", "drought"),)


@pytest.mark.parametrize("operation", ["internet.delete", "internet.search;run", "", "write.shell"])
def test_unapproved_operations_denied(operation):
    builder, *_ = _builder()
    with pytest.raises(SkillProposalDenied):
        builder.preview(name="Read sources", description="Public knowledge",
                        steps=[_step(operation_id=operation)])


@pytest.mark.parametrize("risk,category,provider_type", [
    ("high", CapabilityCategory.RESEARCH, ProviderType.MCP),
    ("medium", CapabilityCategory.RESEARCH, ProviderType.MCP),
    ("low", CapabilityCategory.AUTOMATION, ProviderType.MCP),
    ("low", CapabilityCategory.CODING, ProviderType.MCP),
    ("low", CapabilityCategory.RESEARCH, ProviderType.SERVICE),
])
def test_high_risk_actuation_or_non_mcp_provider_denied(risk, category, provider_type):
    builder, *_ = _builder(risk=risk, category=category, provider_type=provider_type)
    with pytest.raises(SkillProposalDenied):
        builder.preview(name="Read sources", description="Read only", steps=[_step()])


def test_unhealthy_and_unknown_capability_are_denied():
    builder, caps, _ = _builder()
    caps.update_health("internet.search", "mcp:research", available=False, healthy=False)
    with pytest.raises(SkillProposalDenied):
        builder.preview(name="Read sources", description="Read only", steps=[_step()])
    with pytest.raises(SkillProposalDenied):
        builder.preview(name="Read sources", description="Read only",
                        steps=[_step(capability_id="filesystem.delete")])


@pytest.mark.parametrize("arguments", [
    {"a": {"nested": "data"}}, {"a": [1, 2]}, {"a": float("nan")},
    {"a": float("inf")}, {"a": 10 ** 20}, {"a": 1e20},
    {"a": "hi\nworld"}, {"a": "$" + "{ENV_SECRET}"},
    {"a": "{{template}}"}, {"a": "x" * 257},
    {"../key": "foo"}, {17: "mixed-key"}, {"a": "ok", None: 1},
    {f"k{i}": i for i in range(13)},
])
def test_unsafe_nested_or_template_argument_values_rejected(arguments):
    builder, *_ = _builder()
    with pytest.raises(ValueError):
        builder.preview(name="Read sources", description="Public evidence",
                        steps=[_step(arguments=arguments)])


@pytest.mark.parametrize("steps", [
    [], [_step()] * 9, ["arbitrary"], [{"capability_id": "internet.search"}],
    [_step(extra="bypass")], None,
])
def test_bad_step_count_or_schema_rejected(steps):
    builder, *_ = _builder()
    with pytest.raises(ValueError):
        builder.preview(name="Read sources", description="Public evidence", steps=steps)


@pytest.mark.parametrize("name,description", [
    ("", "Valid"), ("bad\nname", "Valid"), (" x", "Valid"),
    ("N" * 81, "Valid"), ("Valid", ""), ("Valid", "D" * 301),
    ("Valid", "x\x00hello"), ("Valid", "\ud800bad"),
])
def test_invalid_skill_identity_rejected(name, description):
    builder, *_ = _builder()
    with pytest.raises(ValueError):
        builder.preview(name=name, description=description, steps=[_step()])


def test_no_implicit_allowlist_or_capability_registration():
    caps, _ = _setup()
    for rules in (None, {}, {"internet.search": ("",)},
                  {"internet.search": ("internet.search",) * 9}):
        with pytest.raises(ValueError):
            GovernedSkillProposalBuilder(caps, allowed_operations=rules)
    builder = GovernedSkillProposalBuilder(
        caps, allowed_operations={"filesystem.delete": ("filesystem.delete",)},
    )
    with pytest.raises(SkillProposalDenied):
        builder.preview(name="Safe", description="Safe",
                        steps=[_step(capability_id="filesystem.delete",
                                    operation_id="filesystem.delete")])
