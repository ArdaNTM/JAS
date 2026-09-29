"""Provider-agnostic model selection; Ollama is only one adapter target."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    model_id: str
    provider_id: str
    capabilities: frozenset[str]
    priority: int = 0
    quality: int = 0
    latency_ms: int = 0
    max_context_tokens: int = 0
    available: bool = True
    healthy: bool = True

    def __post_init__(self) -> None:
        if not self.model_id or not self.provider_id or not self.capabilities:
            raise ValueError("Model id, provider id and capabilities are required")


@dataclass(frozen=True, slots=True)
class ModelRequirements:
    required_capabilities: frozenset[str]
    min_context_tokens: int = 0


class ModelProvider(Protocol):
    async def generate(self, model_id: str, prompt: str, options: dict[str, Any] | None = None) -> str:
        raise NotImplementedError


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelDefinition] = {}

    def register(self, definition: ModelDefinition) -> None:
        if definition.model_id in self._models:
            raise ValueError(f"Model already registered: {definition.model_id}")
        self._models[definition.model_id] = definition

    def models(self) -> tuple[ModelDefinition, ...]:
        return tuple(self._models[key] for key in sorted(self._models))


class ModelRouter:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def select(self, requirements: ModelRequirements) -> ModelDefinition:
        candidates = [model for model in self._registry.models() if model.available and model.healthy and requirements.required_capabilities <= model.capabilities and model.max_context_tokens >= requirements.min_context_tokens]
        if not candidates:
            raise LookupError("No eligible model")
        return min(candidates, key=lambda model: (-model.priority, -model.quality, model.latency_ms, model.provider_id, model.model_id))
