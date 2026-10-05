from __future__ import annotations

from .environment import knowledge_root_from_env
from .layout import StorageLayout


def initialize_knowledge_storage() -> StorageLayout:
    layout = StorageLayout(
        knowledge_root_from_env()
    )

    layout.initialize()

    return layout
