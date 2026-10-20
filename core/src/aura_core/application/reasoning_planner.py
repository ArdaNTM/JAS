"""Bounded, deterministic reasoning plans; this module never executes tools.

The planner may propose only allow-listed step kinds. External actions remain
separate task submissions handled by AgentTaskService and MCPGateway.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata


MAX_DIRECTIVE_CHARS = 4000
MAX_PLAN_STEPS = 8


def normalize_text(value: str) -> str:
    value = value.casefold().translate(str.maketrans({
        "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
    }))
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    step_id: str
    kind: str
    description: str
    depends_on: tuple[str, ...]
    requires_authorization: bool = False


@dataclass(frozen=True, slots=True)
class ReasoningPlan:
    directive: str
    strategy: str
    steps: tuple[ReasoningStep, ...]
    requires_user_confirmation: bool
    execution_started: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "directive": self.directive,
            "strategy": self.strategy,
            "steps": [asdict(step) for step in self.steps],
            "requires_user_confirmation": self.requires_user_confirmation,
            "execution_started": self.execution_started,
        }


class ReasoningPlanner:
    """Produce small inspectable plans without granting execution authority."""

    _RESEARCH_WORDS = frozenset({
        "research", "search", "find", "investigate", "compare", "arastir",
        "arastirma", "ara", "bul", "incele", "karsilastir", "hakkinda",
    })
    _MULTI_STEP_WORDS = frozenset({
        "and", "then", "after", "compare", "summarize", "report",
        "ve", "sonra", "ardindan", "karsilastir", "ozetle", "raporla",
    })
    _EXTERNAL_ACTION_WORDS = frozenset({
        "send", "delete", "purchase", "buy", "publish", "execute",
        "gonder", "sil", "satinal", "yayinla", "calistir",
    })

    def plan(self, directive: str) -> ReasoningPlan:
        original = " ".join(str(directive).split())
        if not original:
            raise ValueError("Directive is required.")
        if len(original) > MAX_DIRECTIVE_CHARS:
            raise ValueError(f"Directive exceeds {MAX_DIRECTIVE_CHARS} characters.")

        normalized = normalize_text(original)
        words = set(re.findall(r"[a-z0-9]+", normalized))
        if not words.intersection(self._RESEARCH_WORDS):
            raise ValueError(
                "No supported reasoning strategy matches this directive. "
                "Current strategies are bounded research and comparison."
            )

        external_action = bool(words.intersection(self._EXTERNAL_ACTION_WORDS))
        multi_step = bool(words.intersection(self._MULTI_STEP_WORDS))
        steps = [
            ReasoningStep(
                step_id="research",
                kind="capability_request",
                description="Collect relevant public-web evidence through the governed internet.search capability.",
                depends_on=(),
                requires_authorization=True,
            )
        ]
        if multi_step or external_action:
            steps.append(
                ReasoningStep(
                    step_id="analyze-evidence",
                    kind="reasoning",
                    description="Analyze retrieved evidence, note uncertainty, and compare claims without inventing sources.",
                    depends_on=("research",),
                )
            )
        steps.append(
            ReasoningStep(
                step_id="compose-response",
                kind="response",
                description="Prepare a concise answer with source attribution and explicit limitations.",
                depends_on=(steps[-1].step_id,),
            )
        )
        if len(steps) > MAX_PLAN_STEPS:
            raise ValueError("Generated plan exceeds the configured step limit.")

        return ReasoningPlan(
            directive=original,
            strategy="bounded_research_v1",
            steps=tuple(steps),
            requires_user_confirmation=external_action,
        )
