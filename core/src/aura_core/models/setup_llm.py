from __future__ import annotations
import os
from .multi_router import MultiProviderRouter, ProviderRoute
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider

def build_llm_router() -> MultiProviderRouter:
    routes = [
        ProviderRoute(
            provider=OllamaProvider(model="qwen3:4b-instruct-2507-q4_K_M"),
            priority=1,
            enabled=True
        ),
        ProviderRoute(
            provider=OpenAICompatibleProvider(
                provider_id="llm:openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                api_key_env="OPENAI_API_KEY"
            ),
            priority=2,
            enabled=bool(os.getenv("OPENAI_API_KEY"))
        )
    ]
    return MultiProviderRouter(routes=routes)
