from __future__ import annotations

from pathlib import Path


def knowledge_root_from_env() -> Path:
    import os

    return Path(
        os.getenv(
            "AURA_KNOWLEDGE_ROOT",
            r"D:\AURA\Knowledge",
        )
    ).resolve()
