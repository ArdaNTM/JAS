from aura_core.learning.models import LearningObjective
from aura_core.learning.planner import ResearchPlanner


def test_learning_planner_is_deterministic():
    planner = ResearchPlanner()

    queries = planner.plan_queries(
        "Python architecture",
        4,
    )

    assert queries == [
        "Python architecture",
        "Python architecture overview",
        "Python architecture latest developments",
        "Python architecture authoritative documentation",
    ]


def test_learning_objective():
    objective = LearningObjective(
        objective_id="x",
        title="X",
        description="Y",
    )

    assert objective.enabled is True
