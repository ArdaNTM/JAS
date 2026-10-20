"""Rule-based proactive event observer.

The observer turns selected Kernel events into reviewable suggestions. It does
not call providers, create tasks, or execute side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aura_core.kernel.events import KernelEvent


@dataclass(frozen=True, slots=True)
class ProactiveSuggestion:
    event_type: str
    title: str
    summary: str
    correlation_id: str | None
    requires_user_action: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "correlation_id": self.correlation_id,
            "requires_user_action": self.requires_user_action,
        }


class ProactiveEventObserver:
    """Convert a small allow-list of system events into suggestions."""

    _RULES = {
        "CapabilityUnavailable": (
            "Capability unavailable",
            "A registered capability became unavailable. Review health and provider status.",
        ),
        "ServiceFailed": (
            "Service failure detected",
            "A service reported failure. Review diagnostics before attempting recovery.",
        ),
        "TaskFailed": (
            "Task failed",
            "A task failed. Review the recorded step results before deciding whether to retry.",
        ),
        "TaskSucceeded": (
            "Task completed",
            "A task completed. Review its result and decide whether further action is needed.",
        ),
    }

    def observe(self, event: KernelEvent) -> ProactiveSuggestion | None:
        rule = self._RULES.get(event.event_type)
        if rule is None:
            return None
        # Only select safe, compact identifiers; never expose arbitrary event
        # payloads or treat event contents as executable instructions.
        task_id = event.payload.get("task_id")
        suffix = f" Task: {str(task_id)[:100]}." if task_id else ""
        return ProactiveSuggestion(
            event_type=event.event_type,
            title=rule[0],
            summary=rule[1] + suffix,
            correlation_id=event.correlation_id,
        )
