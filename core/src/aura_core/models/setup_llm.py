from __future__ import annotations

import os

from .multi_router import MultiProviderRouter, ProviderRoute
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


DEFAULT_OLLAMA_MODEL = (
    "qwen3:4b-instruct-2507-q4_K_M"
)


def build_llm_router() -> MultiProviderRouter:
    ollama_url = os.getenv(
        "AURA_OLLAMA_URL",
        "http://127.0.0.1:11434",
    )

    ollama_model = os.getenv(
        "AURA_OLLAMA_MODEL",
        DEFAULT_OLLAMA_MODEL,
    )

    routes = [
        ProviderRoute(
            provider=OllamaProvider(
                model=ollama_model,
                base_url=ollama_url,
            ),
            priority=int(
                os.getenv(
                    "AURA_OLLAMA_PRIORITY",
                    "100",
                )
            ),
            enabled=os.getenv(
                "AURA_DISABLE_OLLAMA",
                "0",
            ) != "1",
        ),
    ]

    openai_key = os.getenv("OPENAI_API_KEY")

    if openai_key:
        routes.append(
            ProviderRoute(
                provider=OpenAICompatibleProvider(
                    provider_id="llm:openai",
                    base_url=os.getenv(
                        "OPENAI_BASE_URL",
                        "https://api.openai.com/v1",
                    ),
                    model=os.getenv(
                        "OPENAI_MODEL",
                        "gpt-4o",
                    ),
                    api_key_env="OPENAI_API_KEY",
                ),
                priority=int(
                    os.getenv(
                        "AURA_OPENAI_PRIORITY",
                        "50",
                    )
                ),
                enabled=True,
            )
        )

    return MultiProviderRouter(routes)