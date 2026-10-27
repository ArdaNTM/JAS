import pytest

from aura_core.enterprise.policy_bundle import (
    PolicyBundle, PolicyEffect, PolicyRequest, PolicyRule,
)


def rule(rule_id, effect, priority=0, principal="user-a"):
    return PolicyRule(
        rule_id=rule_id, principal_id=principal,
        capability_id="files.read", operation_id="read",
        resource_scope="workspace:alpha", effect=effect, priority=priority,
    )


def request(principal="user-a"):
    return PolicyRequest(
        principal_id=principal, capability_id="files.read",
        operation_id="read", resource_scope="workspace:alpha",
    )


def test_policy_bundle_fails_closed_without_matching_rule():
    bundle = PolicyBundle("2026.10.1", (rule("allow-a", PolicyEffect.ALLOW),))
    decision = bundle.evaluate(request("user-b"))
    assert decision.effect is PolicyEffect.DENY
    assert decision.reason_code == "no_matching_rule"
    assert decision.matched_rule_ids == ()


def test_explicit_deny_overrides_allow_even_at_lower_priority():
    bundle = PolicyBundle("2026.10.1", (
        rule("allow", PolicyEffect.ALLOW, priority=100),
        rule("deny", PolicyEffect.DENY, priority=-100),
    ))
    decision = bundle.evaluate(request())
    assert decision.effect is PolicyEffect.DENY
    assert decision.reason_code == "explicit_deny"
    assert decision.matched_rule_ids == ("deny",)


def test_approval_gate_overrides_allow():
    bundle = PolicyBundle("2026.10.1", (
        rule("allow", PolicyEffect.ALLOW),
        rule("approval", PolicyEffect.REQUIRE_APPROVAL),
    ))
    decision = bundle.evaluate(request())
    assert decision.effect is PolicyEffect.REQUIRE_APPROVAL
    assert decision.reason_code == "approval_required"


def test_policy_digest_is_stable_and_changes_with_policy():
    first = PolicyBundle("v1", (rule("allow", PolicyEffect.ALLOW),))
    reordered = PolicyBundle("v1", (rule("allow", PolicyEffect.ALLOW),))
    changed = PolicyBundle("v2", (rule("allow", PolicyEffect.ALLOW),))
    assert first.digest == reordered.digest
    assert first.digest != changed.digest
    assert first.evaluate(request()).bundle_digest == first.digest


def test_policy_bundle_rejects_duplicate_ids_and_invalid_metadata():
    with pytest.raises(ValueError):
        PolicyBundle("v1", (
            rule("same", PolicyEffect.ALLOW), rule("same", PolicyEffect.DENY),
        ))
    with pytest.raises(ValueError):
        rule("bad\nrule", PolicyEffect.ALLOW)
