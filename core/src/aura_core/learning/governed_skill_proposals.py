"""Deterministic, non-executable skill/workflow proposal builder.

Creates *candidate data only* using the existing Skill/SkillStep model and
CapabilityRegistry. No script generation, imports, dynamic tool registration,
persistence, Owner approval or MCP dispatch can happen from this module.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityRegistry, ProviderType,
)
from aura_core.learning.skill_library import Skill, SkillLibrary, SkillStep

_ID = re.compile(r"[a-z][a-z0-9_.:-]{2,64}\Z")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_READONLY_CATEGORIES = frozenset({
    CapabilityCategory.RESEARCH,
    CapabilityCategory.DIAGNOSTICS,
    CapabilityCategory.STORAGE,
})


class SkillProposalDenied(PermissionError):
    """Unregistered, unapproved or high-risk workflow step."""


@dataclass(frozen=True, slots=True)
class ProposedStep:
    capability_id: str
    operation_id: str
    tool_name: str
    provider_id: str
    arguments: tuple[tuple[str, str | int | float | bool | None], ...]


@dataclass(frozen=True, slots=True)
class SkillProposalPreview:
    skill_id: str
    name: str
    description: str
    steps: tuple[ProposedStep, ...]
    status: str = "CANDIDATE_UNVERIFIED"
    authority: str = "NO_EXECUTION_OR_PROMOTION"

    def to_unapproved_candidate(self) -> Skill:
        """Return a fresh disabled legacy Skill for existing validation pipeline."""
        return Skill(
            skill_id=self.skill_id,
            name=self.name,
            description=self.description,
            steps=[
                SkillStep(
                    action="invoke_registered_capability",
                    capability_id=item.capability_id,
                    operation_id=item.operation_id,
                    arguments_template=dict(item.arguments),
                )
                for item in self.steps
            ],
            preconditions=["Owner and existing PermissionEngine must explicitly authorize execution"],
            postconditions=["Evidence/actual provider response must be independently reviewed"],
            source_run_ids=[],  # never invent promotion/replay evidence
            success_count=0,
            failure_count=0,
            confidence=0.0,
            enabled=False,
        )


def _bounded_text(value: str, name: str, max_chars: int) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value.strip()) <= max_chars
        or value != value.strip()
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError(f"Invalid {name}")
    return value


def _arguments(value: object) -> tuple[tuple[str, str | int | float | bool | None], ...]:
    if not isinstance(value, dict) or len(value) > 12:
        raise ValueError("Only bounded flat JSON-safe argument maps are accepted")
    out = []
    for key, item in sorted(value.items()):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ValueError("Invalid argument key")
        if isinstance(item, str):
            if len(item) > 256 or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in item):
                raise ValueError("Invalid argument text")
        elif item is None or type(item) in (bool, int):
            if type(item) is int and abs(item) > 999_999_999_999:
                raise ValueError("Argument integer too large")
        elif type(item) is float:
            if not math.isfinite(item) or abs(item) > 999_999_999_999:
                raise ValueError("Argument float is unsafe")
        else:
            raise ValueError("Argument type cannot be serialized safely")
        out.append((key, item))
    return tuple(out)


class GovernedSkillProposalBuilder:
    """Strict allowlisted preview using current healthy registered capabilities."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        *,
        allowed_operations: dict[str, tuple[str, ...]],
    ) -> None:
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("Existing Core CapabilityRegistry is required")
        if not isinstance(allowed_operations, dict) or not allowed_operations:
            raise ValueError("Explicit read-only operation allowlist is required")
        rules: dict[str, frozenset[str]] = {}
        for cap, operations in allowed_operations.items():
            if not isinstance(cap, str) or not _ID.fullmatch(cap):
                raise ValueError("Invalid allowlisted capability ID")
            if not isinstance(operations, (tuple, list)) or not operations or len(operations) > 8:
                raise ValueError("Expected bounded allowlisted operation IDs")
            if any(not isinstance(op, str) or not _ID.fullmatch(op) for op in operations):
                raise ValueError("Invalid allowlisted operation")
            rules[cap] = frozenset(operations)
        self._capabilities = capabilities
        self._allowed = rules

    def preview(
        self,
        *,
        name: str,
        description: str,
        steps: list[dict[str, object]] | tuple[dict[str, object], ...],
    ) -> SkillProposalPreview:
        name = _bounded_text(name, "skill name", 80)
        description = _bounded_text(description, "skill description", 300)
        if not isinstance(steps, (list, tuple)) or not 1 <= len(steps) <= 8:
            raise ValueError("Expected 1..8 declarative workflow steps")
        candidates: list[ProposedStep] = []
        for raw in steps:
            if not isinstance(raw, dict) or set(raw) != {"capability_id", "operation_id", "arguments"}:
                raise ValueError("Workflow step has unexpected schema")
            capability_id = raw["capability_id"]
            operation_id = raw["operation_id"]
            if (
                not isinstance(capability_id, str) or not isinstance(operation_id, str)
                or operation_id not in self._allowed.get(capability_id, frozenset())
            ):
                raise SkillProposalDenied("Workflow capability/operation was not preapproved")
            try:
                registered = self._capabilities.resolve(capability_id)
            except LookupError as exc:
                raise SkillProposalDenied("Registered workflow capability unavailable") from exc
            definition = registered.definition
            if (
                definition.category not in _READONLY_CATEGORIES
                or definition.provider_type is not ProviderType.MCP
                or definition.risk_level != "low"
                or not definition.tool_name
            ):
                raise SkillProposalDenied("High-risk or non-MCP workflow capability denied")
            candidates.append(ProposedStep(
                capability_id=capability_id, operation_id=operation_id,
                tool_name=definition.tool_name, provider_id=definition.provider_id,
                arguments=_arguments(raw["arguments"]),
            ))
        return SkillProposalPreview(
            skill_id=SkillLibrary.make_id(name, description),
            name=name, description=description, steps=tuple(candidates),
        )
