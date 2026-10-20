import pytest

from aura_core.application.reasoning_planner import ReasoningPlanner


def test_research_plan_is_bounded_and_does_not_execute() -> None:
    plan = ReasoningPlanner().plan(
        "Araştırma yap ve sonuçları karşılaştırıp özetle."
    )
    result = plan.to_dict()

    assert result["strategy"] == "bounded_research_v1"
    assert result["execution_started"] is False
    assert [step["step_id"] for step in result["steps"]] == [
        "research", "analyze-evidence", "compose-response"
    ]
    assert result["steps"][0]["requires_authorization"] is True
    assert result["steps"][1]["depends_on"] == ("research",)
    assert result["steps"][2]["depends_on"] == ("analyze-evidence",)


def test_reasoning_planner_rejects_unknown_capability() -> None:
    with pytest.raises(ValueError, match="No supported reasoning strategy"):
        ReasoningPlanner().plan("Kahvemi hazırla.")


def test_reasoning_planner_requires_confirmation_for_external_action() -> None:
    plan = ReasoningPlanner().plan("Araştır ve raporu gönder.")
    assert plan.requires_user_confirmation is True
    assert plan.execution_started is False


def test_reasoning_planner_enforces_input_limit() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        ReasoningPlanner().plan("araştır " + "x" * 4000)
