# Persona and initiative gate hardening — partial features #3 and #4

The existing `PersonaPolicy` retains its presentation-only role. This change rejects boolean/float/string values where integer setting fields are required, and rejects non-boolean opt-in/initiative flags. `may_suggest_initiative` now fails closed on invalid local clock hours, invalid suggestion counts, type confusion and missing explicit authorization. No time-zone, scheduler, PermissionEngine policy, or MCP capability is added.

The `system_style_prompt` remains non-authoritative. These pure checks cannot prove identity, Owner approval, or policy grants; executing actions still requires the existing Gateway boundary. No proactive task is run by this feature.

Features #3 and #4 remain partial: user profile persistence, multi-device synchronization, actual preference/initiative UI and measured real-world acceptance are out of scope.

Test: `cd core && uv run pytest -q tests/test_persona_initiative_validation.py`; full CI and deterministic Release Lock.
