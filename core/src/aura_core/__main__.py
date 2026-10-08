from __future__ import annotations

import os

import uvicorn

from aura_core.main import app


def main() -> None:
    host = os.getenv(
        "AURA_CORE_HOST",
        "127.0.0.1",
    )

    port = int(
        os.getenv(
            "AURA_CORE_PORT",
            "8000",
        )
    )

    uvicorn.run(
        app,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
