from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from aura_core.kernel.permissions import RiskLevel


@dataclass(frozen=True, slots=True)
class GeneratedStep:
    step_id: str
    capability_id: str
    operation_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, object]
    depends_on: set[str]
    max_attempts: int = 1


@dataclass(frozen=True, slots=True)
class GeneratedPlan:
    resource_scope: str
    steps: tuple[GeneratedStep, ...]


def _ascii_fold(value: str) -> str:
    """Normalize Turkish text for deterministic keyword matching."""
    value = value.casefold().translate(str.maketrans({
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }))
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


class DirectivePlanner:
    """
    Deterministic, allow-listed directive planner.

    Visualization plans are presentation directives, not executable MCP
    tools. Research plans continue through the governed task/Gateway path.
    """

    _VISUAL_VERBS = frozenset({
        "ciz", "goster", "olustur", "uret", "modelle",
        "gorsellestir", "visualize", "draw", "create", "make",
    })

    _VISUAL_OBJECTS = frozenset({
        "model", "modelini", "3d", "3b", "hologram",
        "disli", "kure", "motor", "nesne", "obje",
        "gear", "gears", "sphere", "ball", "engine",
        "object",
    })

    _RESEARCH_TERMS = (
        "arastir", "arastirma", "research", "search", "ara",
        "bul", "incele", "ogren", "bilgi", "hakkinda",
    )

    # Conversational requests are NOT tool executions. They produce an
    # explicit empty plan that the UI routes to its existing streaming LLM.
    # Unrecognized action directives must still be rejected, never promoted
    # to an MCP capability or treated as authorized OS operations.
    _CHAT_PREFIXES = (
        "tell me", "what is", "what are", "what's", "who is", "why ",
        "how does", "how do", "explain", "say ", "hello", "hi ", "hey ",
        "write me", "give me a joke", "joke", "bana anlat",
        "bana bir saka", "bir saka", "saka yap", "merhaba",
        "selam", "nedir", "nasil", "kimdir", "acikla",
    )

    # Capability/identity questions are ordinary assistant conversation.
    # These must never be promoted into a model-selected "synthesize" tool.
    _CAPABILITY_QUESTIONS = (
        "neler yapabilirsin", "ne yapabilirsin", "neleri yapabiliyorsun",
        "hangi araclarin var", "hangi yeteneklerin var", "yeteneklerin neler",
        "kendini tanit", "sen kimsin", "sistemde neler var",
        "what can you do", "what tools do you have", "what are your capabilities",
        "tell me about yourself", "who are you",
    )

    _MODEL_RULES = (
        (frozenset({"disli", "gear", "gears"}), "gear-v1"),
        (frozenset({"kure", "sphere", "ball"}), "sphere-v1"),
        (frozenset({"motor", "engine"}), "motor-v1"),
    )

    def plan(self, directive: str) -> GeneratedPlan:
        text = directive.strip()
        if not text:
            raise ValueError("Directive is required.")

        normalized = _ascii_fold(text)
        tokens = set(normalized.split())

        # Discovery is an explicit user action; plain capability questions do
        # not trigger any GitHub fetch or permission operation.
        if (normalized.strip(" .!?") == "kendini gelistir"
                or ("yeni" in normalized and "ucretsiz" in normalized
                    and "ozellik" in normalized and "arastir" in normalized)
                or ("github" in normalized and "kendine" in normalized
                    and "arac" in normalized and "bul" in normalized)):
            return GeneratedPlan(resource_scope="local-discovery", steps=())

        # Question-first classification runs before search keyword matching;
        # "hangi araştırma araçların var?" is not a request to search the web.
        if any(term in normalized for term in self._CAPABILITY_QUESTIONS):
            return GeneratedPlan(resource_scope="local-assistant", steps=())

        starts_as_3d = normalized.startswith(("3d ", "3b "))
        has_visual_verb = any(
            term in tokens for term in self._VISUAL_VERBS
        )
        has_visual_object = any(
            term in tokens for term in self._VISUAL_OBJECTS
        )

        if starts_as_3d or (has_visual_verb and has_visual_object):
            model_id = "procedural-object-v1"
            for keywords, candidate in self._MODEL_RULES:
                if tokens.intersection(keywords):
                    model_id = candidate
                    break

            return GeneratedPlan(
                resource_scope="local-ui",
                steps=(
                    GeneratedStep(
                        step_id="visualize-3d",
                        capability_id="3d.visualize",
                        operation_id="3d.visualize",
                        tool_name="visualize",
                        risk_level=RiskLevel.LOW,
                        arguments={
                            "model_id": model_id,
                            "target": " ".join(text.split())[:120],
                        },
                        depends_on=set(),
                        max_attempts=1,
                    ),
                ),
            )

        # Match standalone words, not substrings: "ara" inside "bilgisayar"
        # must never turn an ordinary question into a search tool invocation.
        research_words = set(re.findall(r"[a-z0-9_]+", normalized))
        # Turkish inflection is legal only on the explicitly research-related
        # stems. An unrelated word such as "bilgisayar" must not match "ara"
        # or "bilgi" and accidentally dispatch a network tool.
        search_stems = ("arastir", "incele", "ogren")
        if (research_words.intersection(self._RESEARCH_TERMS)
                or any(word.startswith(search_stems) for word in research_words)):
            return GeneratedPlan(
                resource_scope="public-web",
                steps=(
                    GeneratedStep(
                        step_id="research-search",
                        capability_id="internet.search",
                        operation_id="internet.search",
                        tool_name="search",
                        risk_level=RiskLevel.LOW,
                        arguments={"query": text},
                        depends_on=set(),
                        max_attempts=1,
                    ),
                ),
            )

        # An explicitly conversational directive may use ONLY the local
        # assistant response route; no MCP plan/approval is synthesized.
        conversational = normalized
        if conversational.startswith("aura"):
            suffix = conversational[4:]
            if not suffix or suffix[0] in " ,:;.!?-":
                conversational = suffix.lstrip(" ,:;.!?-")
        if any(conversational.startswith(prefix)
               for prefix in self._CHAT_PREFIXES):
            return GeneratedPlan(
                resource_scope="local-assistant",
                steps=(),
            )

        # Unknown questions stay read-only: only explicit action plans may
        # reach MCPGateway. Do not infer authority from a question mark.
        if normalized.rstrip().endswith("?"):
            return GeneratedPlan(resource_scope="local-assistant", steps=())

        raise ValueError(
            "No governed capability matches this directive. "
            "Supported autonomous directive: research/search or 3D visualization."
        )