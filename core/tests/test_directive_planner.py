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

def test_conversational_voice_request_routes_to_non_executable_assistant():
    for phrase in ("AURA tell me a short joke.", "Tell me a short joke",
                   "AURA, explain why the sky is blue", "Merhaba AURA"):
        plan = DirectivePlanner().plan(phrase)
        assert plan.resource_scope == "local-assistant"
        assert plan.steps == ()


def test_instructions_to_operate_computer_are_not_conversation_tools():
    for phrase in ("AURA delete the backups", "Run arbitrary Python",
                   "Kahvemi hazırla."):
        try:
            DirectivePlanner().plan(phrase)
        except ValueError as exc:
            assert "No governed capability" in str(exc)
        else:
            raise AssertionError("Unsupported commands must fail closed")
