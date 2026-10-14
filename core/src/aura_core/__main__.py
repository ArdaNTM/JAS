from __future__ import annotations

import os
import uvicorn

from aura_core.main import app


def main() -> None:
    host = os.getenv("AURA_CORE_HOST", "127.0.0.1").strip()

    if host != "127.0.0.1":
        raise SystemExit(
            "AURA security policy: AURA_CORE_HOST must be 127.0.0.1. "
            "Network-facing binds are disabled by default."
        )

    port = int(os.getenv("AURA_CORE_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("AURA_CORE_PORT must be between 1 and 65535.")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
