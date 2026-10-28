"""Versioned, fail-closed policy bundles for enterprise governance.

This is a deterministic policy artifact/evaluation primitive. It does not replace
AURA PermissionEngine and must be integrated by the composition root before it can
govern production requests. Matching is exact; wildcard semantics are intentionally
not supported.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
from enum import StrEnum


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    rule_id: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    effect: PolicyEffect
    priority: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "rule_id", "principal_id", "capability_id", "operation_id", "resource_scope",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
            if len(value) > 256 or any(ord(ch) < 32 for ch in value):
                raise ValueError(f"{field_name} is invalid")
        if type(self.priority) is not int or not -1000 <= self.priority <= 1000:
            raise ValueError("priority must be an integer between -1000 and 1000")
        if not isinstance(self.effect, PolicyEffect):
            raise ValueError("effect must be a PolicyEffect")


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str

    def __post_init__(self) -> None:
        for field_name in ("principal_id", "capability_id", "operation_id", "resource_scope"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
            if len(value) > 256 or any(ord(ch) < 32 for ch in value):
                raise ValueError(f"{field_name} is invalid")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    effect: PolicyEffect
    reason_code: str
    matched_rule_ids: tuple[str, ...]
    bundle_version: str
    bundle_digest: str


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    version: str
    rules: tuple[PolicyRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("Policy bundle version is required")
        if len(self.version) > 64 or any(ord(ch) < 32 for ch in self.version):
            raise ValueError("Policy bundle version is invalid")
        if not self.rules:
            raise ValueError("Policy bundle must contain at least one rule")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("Policy rule IDs must be unique")

    @classmethod
    def from_json_file(cls, path: str | Path) -> "PolicyBundle":
        """Load a strict JSON policy bundle from a local configuration file.

        The file is read once during application composition. Invalid configuration
        raises ValueError so startup cannot silently fall back to legacy-only policy.
        """
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ValueError("Policy bundle path is required")
        source = Path(path)
        try:
            if source.stat().st_size > 1_048_576:
                raise ValueError("Policy bundle file exceeds 1 MiB")
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Unable to load policy bundle JSON") from exc

        if not isinstance(payload, dict) or set(payload) != {"version", "rules"}:
            raise ValueError("Policy bundle JSON must contain only version and rules")
        raw_rules = payload["rules"]
        if not isinstance(raw_rules, list):
            raise ValueError("Policy bundle rules must be an array")

        rules = []
        required = {
            "rule_id", "principal_id", "capability_id", "operation_id",
            "resource_scope", "effect",
        }
        allowed = required | {"priority"}
        for index, raw in enumerate(raw_rules):
            if not isinstance(raw, dict) or not required.issubset(raw) or not set(raw).issubset(allowed):
                raise ValueError(f"Policy bundle rule {index} has an invalid schema")
            try:
                rules.append(PolicyRule(
                    rule_id=raw["rule_id"],
                    principal_id=raw["principal_id"],
                    capability_id=raw["capability_id"],
                    operation_id=raw["operation_id"],
                    resource_scope=raw["resource_scope"],
                    effect=PolicyEffect(raw["effect"]),
                    priority=raw.get("priority", 0),
                ))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Policy bundle rule {index} is invalid") from exc

        try:
            return cls(version=payload["version"], rules=tuple(rules))
        except (TypeError, ValueError) as exc:
            raise ValueError("Policy bundle metadata is invalid") from exc

    @property
    def digest(self) -> str:
        canonical = {
            "version": self.version,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "principal_id": rule.principal_id,
                    "capability_id": rule.capability_id,
                    "operation_id": rule.operation_id,
                    "resource_scope": rule.resource_scope,
                    "effect": rule.effect.value,
                    "priority": rule.priority,
                }
                for rule in sorted(self.rules, key=lambda item: item.rule_id)
            ],
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        matches = tuple(
            rule for rule in self.rules
            if rule.principal_id == request.principal_id
            and rule.capability_id == request.capability_id
            and rule.operation_id == request.operation_id
            and rule.resource_scope == request.resource_scope
        )
        if not matches:
            return PolicyDecision(
                PolicyEffect.DENY, "no_matching_rule", (), self.version, self.digest,
            )

        # Deny overrides every other effect. Approval also overrides allow so a
        # lower-priority allow can never silently bypass a human approval gate.
        denies = tuple(rule for rule in matches if rule.effect is PolicyEffect.DENY)
        if denies:
            effect, reason = PolicyEffect.DENY, "explicit_deny"
            selected = denies
        else:
            approvals = tuple(rule for rule in matches if rule.effect is PolicyEffect.REQUIRE_APPROVAL)
            if approvals:
                effect, reason, selected = PolicyEffect.REQUIRE_APPROVAL, "approval_required", approvals
            else:
                effect, reason = PolicyEffect.ALLOW, "explicit_allow"
                selected = tuple(rule for rule in matches if rule.effect is PolicyEffect.ALLOW)

        ordered = tuple(sorted(selected, key=lambda item: (-item.priority, item.rule_id)))
        return PolicyDecision(
            effect, reason, tuple(rule.rule_id for rule in ordered), self.version, self.digest,
        )
