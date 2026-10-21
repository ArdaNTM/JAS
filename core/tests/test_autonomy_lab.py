from __future__ import annotations

import pytest

from aura_core.application.autonomy_lab import (
    AutonomyBudget,
    AutonomyValidationError,
    TaskNode,
    evaluate_safe_expression,
    validate_task_graph,
)


def test_task_graph_accepts_bounded_acyclic_plan():
    nodes = [
        TaskNode("observe", "Gather local evidence", kind="observe"),
        TaskNode("reason", "Compare evidence", depends_on=("observe",), kind="reason"),
        TaskNode("verify", "Check result", depends_on=("reason",), kind="verify", requires_approval=True),
    ]
    assert validate_task_graph(nodes) == nodes


@pytest.mark.parametrize(
    "nodes",
    [
        [TaskNode("a", "A", depends_on=("missing",))],
        [TaskNode("a", "A", depends_on=("b",)), TaskNode("b", "B", depends_on=("a",))],
        [TaskNode("a", "A", depends_on=("a",))],
    ],
)
def test_task_graph_rejects_missing_dependencies_and_cycles(nodes):
    with pytest.raises(AutonomyValidationError):
        validate_task_graph(nodes)


def test_task_graph_obeys_step_budget():
    nodes = [TaskNode(str(i), f"Step {i}") for i in range(3)]
    with pytest.raises(AutonomyValidationError, match="subtask budget"):
        validate_task_graph(nodes, AutonomyBudget(max_steps=4, max_subtasks=1))


def test_safe_expression_supports_pure_computation():
    assert evaluate_safe_expression("sum_values * 2 + 1", {"sum_values": 20}) == 41
    assert evaluate_safe_expression("items[0] if len_ok else items[1]", {"items": [4, 9], "len_ok": False}) == 9
    assert evaluate_safe_expression("score >= 0 and score < 100", {"score": 55}) is True


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "open('secret.txt').read()",
        "data.__class__",
        "[x for x in range(1000000)]",
        "lambda: 1",
    ],
)
def test_safe_expression_rejects_code_execution_and_introspection(expression):
    with pytest.raises(AutonomyValidationError):
        evaluate_safe_expression(expression, {"data": {}})


def test_safe_expression_bounds_exponents_and_output_size():
    with pytest.raises(AutonomyValidationError):
        evaluate_safe_expression("2 ** 100", {})
    with pytest.raises(AutonomyValidationError):
        evaluate_safe_expression("'x' * 100000", {})
