"""Gateway-only OSWorld-V2.1 Docker VM adapter and scored task runner.

AURA never executes model-supplied Python. This provider receives fixed, typed
OSWorld guest actions *only* inside a consumed MCPGateway approval dispatch,
then constructs a bounded pyautogui command inside the official disposable VM.
Task setup/evaluation is owned by the upstream OSWorld lab runner, not an AURA
tool. LangGraph/AURA Core remain the authority for real tool execution.

A real score is emitted ONLY after the official upstream DesktopEnv.evaluate()
has run on the real Ubuntu Docker VM. The upstream osworld-v2.1 checkout, assets,
self-hosted websites, Docker provider image and firewall are external,
operator-provisioned prerequisites. No CI mock is a benchmark score.
"""
from __future__ import annotations

import asyncio
import importlib
import ipaddress
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool

_LOGGER = logging.getLogger("aura.osworld.real")
_ALLOWED_KEYS = frozenset({"enter", "esc", "tab", "backspace", "space", "up", "down", "left", "right"})
_UUID = re.compile(r"^[0-9a-f-]{36}$")


class LiveEvaluationDenied(PermissionError):
    """Unverified VM provenance, approval or action budget."""


class GuestEnvironment(Protocol):
    """Subset of the upstream DesktopEnv; actual run uses the official package."""
    def reset(self, task_config: dict[str, Any]) -> dict[str, Any]: ...
    def step(self, action: str, pause: int = 0) -> Any: ...
    def evaluate(self, logger: logging.Logger) -> float: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class VMAction:
    action: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> VMAction:
        if not isinstance(value, dict) or set(value) - {"action", "x", "y", "text", "key"}:
            raise LiveEvaluationDenied("Unknown VM action fields")
        kind = value.get("action")
        if not isinstance(kind, str) or kind not in {"click", "type", "key", "wait", "done"}:
            raise LiveEvaluationDenied("Unsupported guest action")
        if kind == "click":
            if (type(value.get("x")) is not int or type(value.get("y")) is not int
                    or not 0 <= value["x"] < 1920 or not 0 <= value["y"] < 1080):
                raise LiveEvaluationDenied("Out-of-bounds guest coordinates")
            if set(value) != {"action", "x", "y"}:
                raise LiveEvaluationDenied("Click has extraneous fields")
            return cls(action=kind, x=value["x"], y=value["y"])
        if kind == "type":
            text = value.get("text")
            if (set(value) != {"action", "text"} or not isinstance(text, str)
                    or not 1 <= len(text) <= 500
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in text)):
                raise LiveEvaluationDenied("Untrusted guest text rejected")
            return cls(action=kind, text=text)
        if kind == "key":
            key = value.get("key")
            if (set(value) != {"action", "key"}
                    or not isinstance(key, str) or key not in _ALLOWED_KEYS):
                raise LiveEvaluationDenied("Guest keystroke not allowlisted")
            return cls(action=kind, key=key)
        if set(value) != {"action"}:
            raise LiveEvaluationDenied("Unexpected no-op arguments")
        return cls(action=kind)

    def command(self) -> str:
        """Only fixed pyautogui verbs and JSON-quoted literals, no free code."""
        if self.action == "click":
            return f"pyautogui.click({self.x}, {self.y})"
        if self.action == "type":
            return f"pyautogui.write({json.dumps(self.text, ensure_ascii=True)}, interval=0.01)"
        if self.action == "key":
            return f"pyautogui.press({json.dumps(self.key)})"
        if self.action == "wait":
            return "WAIT"
        if self.action == "done":
            return "DONE"
        raise LiveEvaluationDenied("No command for action")


class OSWorldVMMCPProvider:
    """Disposable VM-only adapter. Gateway authorization is mandatory."""

    provider_id = "aura.osworld.v2.1.guest"
    requires_approval = True

    def __init__(self, environment: GuestEnvironment) -> None:
        self._env = environment
        self._lock = asyncio.Lock()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            "osworld_guest_action",
            "A single approved, strictly bounded action in disposable OSWorld VM",
            {
                "type": "object", "additionalProperties": False,
                "required": ["action"],
                "properties": {
                    "action": {"type": "string", "enum": ["click", "type", "key", "wait", "done"]},
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                    "text": {"type": "string", "maxLength": 500},
                    "key": {"type": "string", "enum": sorted(_ALLOWED_KEYS)},
                },
            },
        ),)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or name != "osworld_guest_action"
                or grant.tool_name != name or grant.capability_id != "OSWorldVM"
                or grant.principal_id != "local_owner"
                or not grant.approval_consumed or grant.risk_level not in {"high", "critical"}):
            raise LiveEvaluationDenied("Guest actions require consumed MCP Gateway Owner approval")
        action = VMAction.from_dict(arguments or {})
        async with self._lock:
            # The official guest VM executes the fixed command. Never execute
            # model-generated scripts in the host Python interpreter.
            observation, _, done, _ = await asyncio.to_thread(
                self._env.step, action.command(), 0,
            )
            return {
                "executed": True, "done": bool(done),
                "untrusted": True,
                "accessibility_tree": str(observation.get("accessibility_tree") or "")[:12000],
            }


class ActionPlanner(Protocol):
    async def next_action(
        self, *, instruction: str, accessibility_tree: str,
        action_number: int, remaining: int,
    ) -> dict[str, Any]: ...


class ApprovalSource(Protocol):
    async def wait_for_owner_approval(self, approval_id: str, timeout_seconds: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class LiveEvaluationResult:
    task_id: str
    score: float | None
    actions_attempted: int
    all_actions_gateway_approved: bool
    vm_provider: str = "docker"
    benchmark_release: str = "osworld-v2.1"


async def evaluate_live_vm(
    *, environment: GuestEnvironment,
    gateway: MCPGateway, planner: ActionPlanner,
    approvals: ApprovalSource, task_config: dict[str, Any],
    max_actions: int = 8, wall_time_seconds: int = 120,
) -> LiveEvaluationResult:
    """Run a real upstream OSWorld VM task; no owner approval = no guest action.

    Actual gateway must be independently composed with PermissionEngine,
    ApprovalStore, OSWorldVMMCPProvider, hash-chain audit and an external
    WebAuthn-backed owner approver. The planner cannot mint approval IDs.
    The provider enforces the same dispatch grant again before guest input.
    """
    if not 1 <= max_actions <= 8 or not 10 <= wall_time_seconds <= 120:
        raise ValueError("OSWorld Safety Profile budgets must be bounded")
    if not isinstance(task_config, dict) or not isinstance(task_config.get("id"), str):
        raise ValueError("Official task config with unique ID is required")
    begin = time.monotonic()
    observation = await asyncio.to_thread(environment.reset, task_config)
    tree = str(observation.get("accessibility_tree") or "")[:12000]
    instruction = str(task_config.get("instruction", ""))[:2000]
    attempted = 0
    finished = False
    while attempted < max_actions and not finished:
        remaining = wall_time_seconds - (time.monotonic() - begin)
        if remaining <= 0:
            break
        proposed = await asyncio.wait_for(planner.next_action(
            instruction=instruction, accessibility_tree=tree,
            action_number=attempted + 1, remaining=max_actions - attempted,
        ), timeout=min(15, remaining))
        action = VMAction.from_dict(proposed)
        # Each operation is a unique, fingerprint-bound approval request.
        request = MCPGatewayRequest(
            request_id=str(uuid4()), principal_id="local_owner",
            capability_id="OSWorldVM", operation_id="GuestAction",
            resource_scope="osworld:v2.1:disposable_vm",
            risk_level=RiskLevel.HIGH, tool_name="osworld_guest_action",
            arguments=proposed, task_id=task_config["id"],
        )
        response = await gateway.invoke(request)
        attempted += 1
        if response.decision is not AuthorizationDecision.REQUIRE_APPROVAL or not response.approval_id:
            raise LiveEvaluationDenied("Gateway did not issue an explicit owner approval request")
        deadline = min(60.0, wall_time_seconds - (time.monotonic() - begin))
        if deadline <= 0 or not await approvals.wait_for_owner_approval(
            response.approval_id, deadline,
        ):
            # No second guess and no implicit retry of the physical action.
            raise LiveEvaluationDenied("External WebAuthn Owner approval was not received")
        from dataclasses import replace
        authorized = await gateway.invoke(replace(request, approval_id=response.approval_id))
        if (authorized.decision is not AuthorizationDecision.ALLOW
                or not isinstance(authorized.result, dict)
                or not authorized.result.get("executed")):
            raise LiveEvaluationDenied("Gateway declined or guest execution outcome unknown")
        tree = str(authorized.result.get("accessibility_tree", ""))[:12000]
        finished = bool(authorized.result.get("done")) or action.action == "done"
    if not finished:
        return LiveEvaluationResult(task_config["id"], None, attempted, True)
    # Official evaluator runs only after the task has received an authorized DONE.
    score = await asyncio.to_thread(environment.evaluate, _LOGGER)
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
        raise LiveEvaluationDenied("Official evaluator returned an invalid score")
    return LiveEvaluationResult(task_config["id"], float(score), attempted, True)
