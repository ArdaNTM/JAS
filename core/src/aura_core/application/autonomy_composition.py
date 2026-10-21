"""Composition helpers for explicitly enabled governed autonomy."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Sequence

from aura_core.agent.runtime import PlanState
from aura_core.application.autonomous_adapters import (
    AllowedOperation, BudgetAutonomyGovernor, CapabilityDrivenPlanner,
    DockerIsolatedSandbox,
)
from aura_core.application.governed_autonomous_loop import (
    GovernedAutonomousLoop, VerificationReport,
)
from aura_core.application.ollama_completion import OllamaJSONCompletionProvider
from aura_core.application.tasks import AgentTaskService
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.services import ServiceCategory, ServiceDefinition


class ExecutionResultVerifier:
    """Deterministic verifier: every submitted task must have succeeded."""

    async def verify(self, *, goal, principal_id, submissions, results, iteration):
        if len(results) != len(submissions):
            return VerificationReport(False, "Task/result count mismatch", ("incomplete execution evidence",))
        failed = []
        for result in results:
            if getattr(result, "state", None) is not PlanState.SUCCEEDED:
                failed.append(f"task {getattr(result, 'plan_id', 'unknown')} did not succeed")
        return VerificationReport(not failed, "All submitted plans succeeded" if not failed else "Execution results failed verification", tuple(failed))


@dataclass(frozen=True, slots=True)
class AutonomyComposition:
    loop: GovernedAutonomousLoop
    planner: CapabilityDrivenPlanner
    sandbox: DockerIsolatedSandbox
    governor: BudgetAutonomyGovernor


def _operations_from_env() -> tuple[AllowedOperation, ...]:
    raw = os.getenv("AURA_AUTONOMY_OPERATIONS", "").strip()
    if not raw:
        raise RuntimeError(
            "AURA_AUTONOMY_ENABLED requires AURA_AUTONOMY_OPERATIONS JSON allow-list"
        )
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AURA_AUTONOMY_OPERATIONS must be valid JSON") from exc
    if not isinstance(values, list) or not values:
        raise RuntimeError("AURA_AUTONOMY_OPERATIONS must be a non-empty JSON array")
    operations = []
    from aura_core.kernel.permissions import RiskLevel
    for item in values:
        if not isinstance(item, dict):
            raise RuntimeError("Every autonomy operation must be a JSON object")
        try:
            operations.append(AllowedOperation(
                capability_id=item["capability_id"],
                operation_id=item["operation_id"],
                tool_name=item["tool_name"],
                risk_level=RiskLevel(item.get("risk_level", "low")),
                allowed_argument_keys=frozenset(item["allowed_argument_keys"]),
                max_attempts=int(item.get("max_attempts", 1)),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Invalid autonomy operation allow-list entry") from exc
    return tuple(operations)


def compose_governed_autonomy(*, kernel, task_service: AgentTaskService) -> AutonomyComposition | None:
    """Register concrete autonomy services and expose them only when explicitly enabled."""
    if os.getenv("AURA_AUTONOMY_ENABLED", "0").strip().casefold() not in {"1", "true", "yes", "on"}:
        return None
    if kernel.service_registry is None or kernel.capability_registry is None:
        raise RuntimeError("Kernel registries must be ready before autonomy composition")
    operations = _operations_from_env()
    model = os.getenv("AURA_INFERENCE_MODEL", "qwen3").strip()
    endpoint = os.getenv("AURA_OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    completion = OllamaJSONCompletionProvider(
        base_url=endpoint, model=model,
        timeout_seconds=float(os.getenv("AURA_AUTONOMY_PLANNER_TIMEOUT", "30")),
    )
    planner = CapabilityDrivenPlanner(
        completion_provider=completion, operations=operations,
        max_steps=int(os.getenv("AURA_AUTONOMY_MAX_TASKS", "8")),
    )
    sandbox = DockerIsolatedSandbox(event_bus=kernel.event_bus)
    governor = BudgetAutonomyGovernor(
        max_iterations=int(os.getenv("AURA_AUTONOMY_MAX_ITERATIONS", "3")),
        max_tasks_per_iteration=int(os.getenv("AURA_AUTONOMY_MAX_TASKS", "8")),
        max_tasks_per_principal=int(os.getenv("AURA_AUTONOMY_PRINCIPAL_BUDGET", "24")),
        max_retries_after_execution=int(os.getenv("AURA_AUTONOMY_RETRIES", "0")),
        allowed_principals=frozenset(
            item.strip() for item in os.getenv("AURA_AUTONOMY_PRINCIPALS", "local_owner").split(",")
            if item.strip()
        ),
        event_bus=kernel.event_bus,
    )
    loop = GovernedAutonomousLoop(
        planner=planner, sandbox=sandbox, verifier=ExecutionResultVerifier(),
        governor=governor, task_service=task_service, event_bus=kernel.event_bus,
        max_iterations=int(os.getenv("AURA_AUTONOMY_MAX_ITERATIONS", "3")),
        max_tasks_per_iteration=int(os.getenv("AURA_AUTONOMY_MAX_TASKS", "8")),
        overall_timeout_seconds=float(os.getenv("AURA_AUTONOMY_TIMEOUT_SECONDS", "300")),
    )
    service_id = "aura:governed_autonomy:1.0.0"
    kernel.service_registry.register(
        ServiceDefinition(
            name="governed_autonomy", version="1.0.0", provider="aura",
            category=ServiceCategory.AGENT,
            capabilities=frozenset({"autonomy.run"}),
            tags=frozenset({"governed", "bounded", "opt-in"}),
        ),
        loop,
    )
    kernel.capability_registry.register(CapabilityDefinition(
        capability_id="autonomy.run", name="Governed autonomous task loop",
        version="1.0.0", description="Bounded planning, isolated validation, budget policy and verified task execution.",
        provider_id=service_id, provider_type=ProviderType.CORE,
        category=CapabilityCategory.PLANNING,
        required_permissions=frozenset({"autonomy.run"}),
    ))
    return AutonomyComposition(loop=loop, planner=planner, sandbox=sandbox, governor=governor)
