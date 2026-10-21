"""Bounded autonomy primitives for AURA.

This module provides deterministic task-graph validation and a restricted expression
laboratory. It deliberately does not execute arbitrary Python, shell commands, imports,
network calls, or MCP tools. Any real capability invocation remains a separate
PermissionEngine/MCPGateway operation.
"""
from __future__ import annotations

import ast
import operator
import time
from dataclasses import dataclass
from typing import Any


class AutonomyValidationError(ValueError):
    """A proposed plan or experiment exceeds the supported safe subset."""


@dataclass(frozen=True, slots=True)
class AutonomyBudget:
    max_steps: int = 12
    max_seconds: float = 60.0
    max_subtasks: int = 8

    def __post_init__(self) -> None:
        if not 1 <= self.max_steps <= 32:
            raise ValueError("max_steps must be between 1 and 32")
        if not 1 <= self.max_seconds <= 300:
            raise ValueError("max_seconds must be between 1 and 300")
        if not 0 <= self.max_subtasks <= 16:
            raise ValueError("max_subtasks must be between 0 and 16")


@dataclass(frozen=True, slots=True)
class TaskNode:
    task_id: str
    title: str
    depends_on: tuple[str, ...] = ()
    kind: str = "reason"
    requires_approval: bool = False


def validate_task_graph(nodes: list[TaskNode], budget: AutonomyBudget | None = None) -> list[TaskNode]:
    """Validate bounded acyclic task graph; never executes nodes."""
    limits = budget or AutonomyBudget()
    if not nodes or len(nodes) > limits.max_steps:
        raise AutonomyValidationError("Task graph must contain 1..max_steps nodes")
    known: dict[str, TaskNode] = {}
    allowed_kinds = {"observe", "reason", "retrieve", "experiment", "verify", "reflect", "propose"}
    for node in nodes:
        if not node.task_id or len(node.task_id) > 100 or node.task_id in known:
            raise AutonomyValidationError("Task IDs must be unique, non-empty, and at most 100 characters")
        if not node.title.strip() or len(node.title) > 500:
            raise AutonomyValidationError("Task titles must contain 1..500 characters")
        if node.kind not in allowed_kinds:
            raise AutonomyValidationError(f"Unsupported task kind: {node.kind}")
        if len(node.depends_on) > limits.max_steps:
            raise AutonomyValidationError("Too many task dependencies")
        known[node.task_id] = node
    if len(nodes) - 1 > limits.max_subtasks and len(nodes) > 1:
        raise AutonomyValidationError("Task graph exceeds the subtask budget")
    for node in nodes:
        if node.task_id in node.depends_on:
            raise AutonomyValidationError("A task cannot depend on itself")
        missing = set(node.depends_on) - known.keys()
        if missing:
            raise AutonomyValidationError(f"Unknown task dependency: {sorted(missing)[0]}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise AutonomyValidationError("Task graph contains a dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in known[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in known:
        visit(task_id)
    return list(nodes)


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}


def _validate_input_value(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise AutonomyValidationError("Experiment input nesting exceeds its budget")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if abs(value) > 10**12:
            raise AutonomyValidationError("Numeric input exceeds its safe range")
        return
    if isinstance(value, str):
        if len(value) > 2000:
            raise AutonomyValidationError("String input exceeds its size budget")
        return
    if isinstance(value, list):
        if len(value) > 100:
            raise AutonomyValidationError("Input collection exceeds 100 items")
        for item in value:
            _validate_input_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 100 or any(not isinstance(key, str) for key in value):
            raise AutonomyValidationError("Input mappings must have at most 100 string keys")
        for item in value.values():
            _validate_input_value(item, depth=depth + 1)
        return
    raise AutonomyValidationError("Only JSON-like experiment input values are supported")


def evaluate_safe_expression(expression: str, data: dict[str, Any] | None = None) -> Any:
    """Evaluate a tiny, pure expression language over JSON-like input data.

    Allowed: scalar literals, lists/tuples/dicts, bounded arithmetic, comparisons,
    booleans, conditional expressions, and indexing supplied data. No attributes,
    calls, comprehensions, lambdas, imports, assignments, or arbitrary Python.
    """
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 2000:
        raise AutonomyValidationError("Expression must contain 1..2000 characters")
    if len((data or {})) > 100 or len(repr(data or {})) > 12000:
        raise AutonomyValidationError("Experiment input exceeds its size budget")
    _validate_input_value(data or {})
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise AutonomyValidationError("Expression syntax is invalid") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 200:
        raise AutonomyValidationError("Expression exceeds the 200-node budget")
    started = time.monotonic()

    def evaluate(node: ast.AST, depth: int = 0) -> Any:
        if depth > 24 or time.monotonic() - started > 0.05:
            raise AutonomyValidationError("Experiment exceeded its evaluation budget")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
            if isinstance(node.value, str) and len(node.value) > 2000:
                raise AutonomyValidationError("String literal is too large")
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and abs(node.value) > 10**12:
                raise AutonomyValidationError("Numeric literal exceeds its safe range")
            return node.value
        if isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id not in (data or {}):
                raise AutonomyValidationError(f"Unknown input name: {node.id}")
            return (data or {})[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [evaluate(item, depth + 1) for item in node.elts]
            if len(values) > 100:
                raise AutonomyValidationError("Collection exceeds 100 items")
            return tuple(values) if isinstance(node, ast.Tuple) else set(values) if isinstance(node, ast.Set) else values
        if isinstance(node, ast.Dict):
            if len(node.keys) > 100:
                raise AutonomyValidationError("Mapping exceeds 100 items")
            return {evaluate(k, depth + 1): evaluate(v, depth + 1) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and (not isinstance(right, (int, float)) or abs(right) > 8):
                raise AutonomyValidationError("Exponent is outside the safe range")
            if isinstance(left, (str, list, tuple)) and isinstance(node.op, ast.Mult):
                if not isinstance(right, int) or abs(right) > 100:
                    raise AutonomyValidationError("Sequence multiplication is outside the safe range")
            result = _BINOPS[type(node.op)](left, right)
            if isinstance(result, (str, list, tuple, dict)) and len(result) > 12000:
                raise AutonomyValidationError("Experiment result exceeds its size budget")
            if isinstance(result, (int, float)) and abs(result) > 10**12:
                raise AutonomyValidationError("Numeric result exceeds its safe range")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](evaluate(node.operand, depth + 1))
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [evaluate(value, depth + 1) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = evaluate(node.left, depth + 1)
            for op_node, comparator in zip(node.ops, node.comparators):
                if type(op_node) not in _CMPOPS:
                    raise AutonomyValidationError("Comparison operator is not allowed")
                right = evaluate(comparator, depth + 1)
                if not _CMPOPS[type(op_node)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return evaluate(node.body if evaluate(node.test, depth + 1) else node.orelse, depth + 1)
        if isinstance(node, ast.Subscript):
            container, key = evaluate(node.value, depth + 1), evaluate(node.slice, depth + 1)
            if not isinstance(container, (dict, list, tuple, str)) or not isinstance(key, (str, int)):
                raise AutonomyValidationError("Only simple input indexing is allowed")
            result = container[key]
            if isinstance(result, (str, list, tuple, dict)) and len(result) > 12000:
                raise AutonomyValidationError("Indexed value exceeds its size budget")
            return result
        raise AutonomyValidationError(f"Expression element is not allowed: {type(node).__name__}")

    try:
        result = evaluate(tree)
    except AutonomyValidationError:
        raise
    except Exception as exc:
        raise AutonomyValidationError(f"Experiment evaluation failed: {type(exc).__name__}") from exc
    if isinstance(result, (str, int, float, bool, type(None), list, tuple, dict)):
        if len(repr(result)) > 12000:
            raise AutonomyValidationError("Experiment result exceeds its size budget")
        return result
    raise AutonomyValidationError("Experiment result type is not supported")
