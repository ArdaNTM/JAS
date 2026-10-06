from aura_core.application.directive_planner import DirectivePlanner
from aura_core.kernel.permissions import RiskLevel


def test_research_directive_generates_governed_search_plan():
    plan = DirectivePlanner().plan(
        "Yapay zeka hakkında araştırma yap."
    )

    assert plan.resource_scope == "public-web"
    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.capability_id == "internet.search"
    assert step.operation_id == "internet.search"
    assert step.tool_name == "search"
    assert step.risk_level is RiskLevel.LOW
    assert step.arguments["query"] == (
        "Yapay zeka hakkında araştırma yap."
    )


def test_empty_directive_is_rejected():
    try:
        DirectivePlanner().plan(" ")
    except ValueError as exc:
        assert "Directive is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_unknown_directive_is_rejected():
    try:
        DirectivePlanner().plan("Kahvemi hazırla.")
    except ValueError as exc:
        assert "No governed capability" in str(exc)
    else:
        raise AssertionError("Expected ValueError")