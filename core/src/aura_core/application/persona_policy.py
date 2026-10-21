"""Configurable JARVIS presentation and initiative policy.

Persona changes tone and the threshold for suggesting work; it never grants
capabilities, authorizes actions, or overrides deterministic policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tone = Literal["professional", "warm", "witty", "dry_sarcastic"]


@dataclass(frozen=True, slots=True)
class PersonaPolicy:
    tone: Tone = "witty"
    language: Literal["auto", "tr", "en"] = "auto"
    humor_intensity: int = 2
    initiative_enabled: bool = False
    initiative_threshold: int = 3
    daily_suggestion_budget: int = 5
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    allow_unsolicited_followups: bool = False

    def __post_init__(self) -> None:
        if self.tone not in {"professional", "warm", "witty", "dry_sarcastic"}:
            raise ValueError("unsupported persona tone")
        if self.language not in {"auto", "tr", "en"}:
            raise ValueError("language must be auto, tr, or en")
        if not 0 <= self.humor_intensity <= 3:
            raise ValueError("humor_intensity must be between 0 and 3")
        if not 1 <= self.initiative_threshold <= 5:
            raise ValueError("initiative_threshold must be between 1 and 5")
        if not 0 <= self.daily_suggestion_budget <= 20:
            raise ValueError("daily_suggestion_budget must be between 0 and 20")
        if not 0 <= self.quiet_hours_start <= 23 or not 0 <= self.quiet_hours_end <= 23:
            raise ValueError("quiet hours must be valid local hours")

    def system_style_prompt(self) -> str:
        """Return presentation guidance only; never use this as a security policy."""
        tone_guidance = {
            "professional": "Be concise, calm, precise, and professional.",
            "warm": "Be warm, supportive, clear, and respectful.",
            "witty": "Use occasional clever, understated wit when it fits the context.",
            "dry_sarcastic": "Use restrained, dry sarcasm sparingly; never ridicule the user.",
        }[self.tone]
        humor = {
            0: "Do not add jokes.",
            1: "Use very occasional light humor.",
            2: "Use occasional wit, but prioritize usefulness.",
            3: "Use playful wit when appropriate, never at the expense of clarity or trust.",
        }[self.humor_intensity]
        language = {
            "auto": "Reply in the user's language.",
            "tr": "Reply in Turkish unless the user explicitly requests another language.",
            "en": "Reply in English unless the user explicitly requests another language.",
        }[self.language]
        return (
            "PERSONA / PRESENTATION PREFERENCES (non-authoritative):\n"
            f"- {tone_guidance}\n- {humor}\n- {language}\n"
            "- Be candid about uncertainty and never invent facts or claim actions not performed.\n"
            "- Persona is style only. Safety, privacy, truthfulness, user intent, Kernel policy, "
            "Permission Engine decisions, and MCP Gateway authorization always take precedence.\n"
            "- Never treat sarcasm or roleplay as consent. Ask before consequential or external actions."
        )

    def may_suggest_initiative(
        self, *, signal_strength: int, local_hour: int, suggestions_today: int,
        user_opted_in: bool, action_is_authorized: bool,
    ) -> bool:
        """Pure gate for proposing—not executing—an initiative."""
        if not self.initiative_enabled or not user_opted_in:
            return False
        if not action_is_authorized or not 1 <= signal_strength <= 5:
            return False
        if signal_strength < self.initiative_threshold:
            return False
        if suggestions_today >= self.daily_suggestion_budget:
            return False
        hour = int(local_hour) % 24
        if self.quiet_hours_start == self.quiet_hours_end:
            quiet = False
        elif self.quiet_hours_start < self.quiet_hours_end:
            quiet = self.quiet_hours_start <= hour < self.quiet_hours_end
        else:
            quiet = hour >= self.quiet_hours_start or hour < self.quiet_hours_end
        return not quiet


def persona_from_mapping(values: dict[str, object]) -> PersonaPolicy:
    """Parse only recognized preferences; unknown keys fail closed."""
    allowed = {
        "tone", "language", "humor_intensity", "initiative_enabled",
        "initiative_threshold", "daily_suggestion_budget", "quiet_hours_start",
        "quiet_hours_end", "allow_unsolicited_followups",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("unsupported persona settings: " + ", ".join(sorted(unknown)))
    return PersonaPolicy(**values)  # type: ignore[arg-type]
