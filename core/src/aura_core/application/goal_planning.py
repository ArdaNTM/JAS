"""Deterministic, read-only goal dependency planning over explicit input.

No executor, scheduler, task dispatcher, Owner authorization, persistent
store or agent privilege is created by this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z", re.ASCII)
_STEP = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class GoalStep:
    step_id: str
    description: str
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    estimated_minutes: int = 30


@dataclass(frozen=True, slots=True)
class GoalPlanProjection:
    ordered_step_ids: tuple[str, ...]
    current_ready_ids: tuple[str, ...]
    current_blocked_ids: tuple[str, ...]
    hypothetical_waves: tuple[tuple[str, ...], ...]
    estimated_critical_chain_minutes: int
    untrusted_descriptions: bool = True
    claimed_completion_verified: bool = False
    owner_approval_verified: bool = False
    authorization_checked: bool = False
    actions_executed: bool = False


def _scope(value: str) -> str:
    if type(value) is not str or not _IDENT.fullmatch(value):
        raise ValueError("invalid goal/principal scope identity")
    return value


def plan_goal_steps(
    steps: tuple[GoalStep, ...],
    *, principal_id: str, goal_id: str,
    claimed_completed: tuple[str, ...] = (),
) -> GoalPlanProjection:
    """Topologically group bounded steps into possible sequential waves.

    Any completed IDs supplied by the caller are *unverified claims*.
    The returned waves are mathematical prerequisites, not a schedule or
    permission to perform an action.
    """
    _scope(principal_id)
    _scope(goal_id)
    if type(steps) is not tuple or not 1 <= len(steps) <= 100:
        raise ValueError("goal requires 1..100 explicit steps")
    if type(claimed_completed) is not tuple or len(claimed_completed) > len(steps):
        raise ValueError("bounded completed-step tuple required")
    normalized: dict[str, GoalStep] = {}
    seen: set[str] = set()
    total_deps = 0
    for step in steps:
        if type(step) is not GoalStep:
            raise ValueError("GoalStep required")
        if type(step.step_id) is not str or not _STEP.fullmatch(step.step_id):
            raise ValueError("invalid step identity")
        if step.step_id.casefold() in seen:
            raise ValueError("duplicate goal step")
        seen.add(step.step_id.casefold())
        if (
            type(step.description) is not str
            or not 1 <= len(step.description.strip()) <= 300
            or any(ord(char) < 32 or ord(char) == 127 for char in step.description)
        ):
            raise ValueError("invalid goal step description")
        if type(step.priority) is not int or not -10 <= step.priority <= 10:
            raise ValueError("priority must be -10..10")
        if type(step.estimated_minutes) is not int or not 1 <= step.estimated_minutes <= 10080:
            raise ValueError("estimated minutes must be 1..10080")
        if (
            type(step.dependencies) is not tuple
            or len(step.dependencies) > 20
            or any(type(dep) is not str or not _STEP.fullmatch(dep) for dep in step.dependencies)
            or len(set(step.dependencies)) != len(step.dependencies)
            or step.step_id in step.dependencies
        ):
            raise ValueError("invalid goal dependencies")
        total_deps += len(step.dependencies)
        if total_deps > 500:
            raise ValueError("dependency budget exceeded")
        normalized[step.step_id] = step

    for step in steps:
        if any(dep not in normalized for dep in step.dependencies):
            raise ValueError("missing referenced dependency")
    # Validate the entire graph *before* claimed completion can remove
    # nodes. Otherwise a caller could conceal a cycle by claiming every
    # member of that cycle as already completed.
    all_incoming = {
        key: len(step.dependencies) for key, step in normalized.items()
    }
    all_children: dict[str, set[str]] = {key: set() for key in normalized}
    for step in normalized.values():
        for dependency in step.dependencies:
            all_children[dependency].add(step.step_id)
    queue = sorted(key for key, count in all_incoming.items() if count == 0)
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for child in sorted(all_children[node]):
            all_incoming[child] -= 1
            if all_incoming[child] == 0:
                queue.append(child)
        queue.sort()
    if visited != len(normalized):
        raise ValueError("goal dependency cycle detected")

    complete = set()
    for step_id in claimed_completed:
        if type(step_id) is not str or step_id not in normalized or step_id in complete:
            raise ValueError("invalid or duplicate completed-step claim")
        complete.add(step_id)
    for step_id in complete:
        if not set(normalized[step_id].dependencies).issubset(complete):
            raise ValueError("completed-step claims omit required predecessors")

    pending = set(normalized) - complete
    children: dict[str, set[str]] = {key: set() for key in pending}
    incoming = {
        key: len(set(normalized[key].dependencies) & pending)
        for key in pending
    }
    for key in pending:
        for dep in normalized[key].dependencies:
            if dep in pending:
                children[dep].add(key)
    def sort_ids(ids: set[str]) -> tuple[str, ...]:
        return tuple(sorted(ids, key=lambda key: (normalized[key].priority, key)))

    waves: list[tuple[str, ...]] = []
    ordered: list[str] = []
    ready = {key for key in pending if incoming[key] == 0}
    current_ready = sort_ids(ready)
    longest_minutes: dict[str, int] = {}
    while ready:
        wave = sort_ids(ready)
        waves.append(wave)
        next_ready: set[str] = set()
        for key in wave:
            parents = [
                longest_minutes[parent]
                for parent in normalized[key].dependencies
                if parent in pending
            ]
            longest_minutes[key] = normalized[key].estimated_minutes + (
                max(parents) if parents else 0
            )
            ordered.append(key)
            for child in children[key]:
                incoming[child] -= 1
                if incoming[child] == 0:
                    next_ready.add(child)
        ready = next_ready
    if len(ordered) != len(pending):
        raise ValueError("goal dependency cycle detected")
    return GoalPlanProjection(
        ordered_step_ids=tuple(ordered),
        current_ready_ids=current_ready,
        current_blocked_ids=sort_ids(pending - set(current_ready)),
        hypothetical_waves=tuple(waves),
        estimated_critical_chain_minutes=max(longest_minutes.values(), default=0),
    )
