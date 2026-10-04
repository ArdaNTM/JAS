"""CLI view of AURA provider configuration without exposing secrets."""

from __future__ import annotations

import json
import os


def status(variable: str) -> str:
    return "configured" if os.getenv(variable) else "not_configured"


def main() -> int:
    report = {
        "ollama": {
            "status": "configured",
            "url": os.getenv("AURA_OLLAMA_URL", "http://127.0.0.1:11434"),
            "model": os.getenv("AURA_OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
        },
        "openai": status("OPENAI_API_KEY"),
        "postgres": status("AURA_POSTGRES_DSN"),
        "qdrant": status("AURA_QDRANT_URL"),
        "external_capability_provider": status("AURA_MCP_PROVIDER_ENDPOINT"),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
