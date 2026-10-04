from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMProvider(Protocol):
    provider_id: str
    model: str

    async def generate(
        self,
        prompt: str,
        options: dict[str, object] | None = None,
    ) -> str:
        ...


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: LLMProvider
    priority: int = 0
    enabled: bool = True


class MultiProviderRouter:
    """
    Deterministic provider selection.

    Ordering:
      1. enabled
      2. priority descending
      3. provider_id ascending
      4. model ascending

    If the selected provider fails, the next deterministic route is tried.
    """

    def __init__(
        self,
        routes: list[ProviderRoute],
    ) -> None:
        self._routes = tuple(routes)

    def routes(self) -> tuple[ProviderRoute, ...]:
        return tuple(
            sorted(
                (
                    route
                    for route in self._routes
                    if route.enabled
                ),
                key=lambda route: (
                    -route.priority,
                    route.provider.provider_id,
                    route.provider.model,
                ),
            )
        )

    async def generate(
        self,
        prompt: str,
        options: dict[str, object] | None = None,
    ) -> str:
        routes = self.routes()

        if not routes:
            raise RuntimeError(
                "No enabled LLM provider is configured"
            )

        failures: list[str] = []

        for route in routes:
            try:
                return await route.provider.generate(
                    prompt,
                    options,
                )
            except Exception as exc:
                failures.append(
                    f"{route.provider.provider_id}: "
                    f"{type(exc).__name__}"
                )

        raise RuntimeError(
            "All configured LLM providers failed: "
            + "; ".join(failures)
        )