from __future__ import annotations

import os

from aura_core.application.composition import create_composed_app
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


def build_app():
    runtime = os.getenv(
        "AURA_RUNTIME",
        "ollama",
    )

    model = os.getenv(
        "AURA_MODEL",
        "qwen3:4b-instruct-2507-q4_K_M",
    )

    backend_endpoint = os.getenv(
        "AURA_BACKEND_ENDPOINT",
        "http://127.0.0.1:11434",
    )

    timeout = float(
        os.getenv(
            "AURA_BACKEND_TIMEOUT",
            "30",
        )
    )

    config = RuntimeConfig(
        runtime=runtime,
        model=model,
        temperature=float(
            os.getenv(
                "AURA_TEMPERATURE",
                "0.7",
            )
        ),
        max_tokens=int(
            os.getenv(
                "AURA_MAX_TOKENS",
                "1024",
            )
        ),
    )

    backend_config = BackendConfig(
        endpoint=backend_endpoint,
        timeout=timeout,
    )

    return create_composed_app(
        config=config,
        backend_config=backend_config,
    )


app = build_app()