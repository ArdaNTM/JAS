"""Persona suggestions must be opt-in, correctly timed, and non-authoritative."""
from __future__ import annotations

import pytest

from aura_core.application.persona_policy import PersonaPolicy, persona_from_mapping


def args(**changes):
    defaults = dict(
        signal_strength=4, local_hour=12, suggestions_today=0,
        user_opted_in=True, action_is_authorized=True,
    )
    defaults.update(changes)
    return defaults


def test_initiative_is_strictly_opt_in_and_authorized():
    policy = PersonaPolicy(initiative_enabled=True)
    assert policy.may_suggest_initiative(**args())
    assert not policy.may_suggest_initiative(**args(user_opted_in=False))
    assert not policy.may_suggest_initiative(**args(action_is_authorized=False))
    assert not PersonaPolicy().may_suggest_initiative(**args())


def test_quiet_hours_and_daily_budget_respected():
    policy = PersonaPolicy(initiative_enabled=True, daily_suggestion_budget=2,
                           quiet_hours_start=22, quiet_hours_end=8)
    assert not policy.may_suggest_initiative(**args(local_hour=23))
    assert not policy.may_suggest_initiative(**args(local_hour=7))
    assert policy.may_suggest_initiative(**args(local_hour=8, suggestions_today=1))
    assert not policy.may_suggest_initiative(**args(suggestions_today=2))


@pytest.mark.parametrize("changed", [
    {"signal_strength": True}, {"signal_strength": 4.5},
    {"local_hour": -1}, {"local_hour": 24}, {"local_hour": "12"},
    {"local_hour": True}, {"suggestions_today": -1},
    {"suggestions_today": True}, {"suggestions_today": 1.2},
    {"user_opted_in": 1}, {"action_is_authorized": "yes"},
])
def test_bad_runtime_signals_never_trigger_initiative(changed):
    policy = PersonaPolicy(initiative_enabled=True)
    assert not policy.may_suggest_initiative(**args(**changed))


@pytest.mark.parametrize("override", [
    {"humor_intensity": True}, {"quiet_hours_start": True},
    {"daily_suggestion_budget": 2.0}, {"initiative_threshold": "3"},
    {"initiative_enabled": 1}, {"allow_unsolicited_followups": "false"},
])
def test_invalid_persona_configuration_is_rejected(override):
    with pytest.raises(ValueError):
        persona_from_mapping(override)


def test_persona_prompt_explicitly_denies_execution_authority():
    policy = PersonaPolicy(tone="witty", language="tr")
    instructions = policy.system_style_prompt()
    assert "Permission Engine" in instructions
    assert "MCP Gateway" in instructions
    assert "never" in instructions.lower()


def test_unknown_config_keys_fail_closed():
    with pytest.raises(ValueError, match="unsupported persona settings"):
        persona_from_mapping({"admin_override": True})
