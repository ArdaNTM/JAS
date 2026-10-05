from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StorageLayout:
    root: Path

    def initialize(self) -> None:
        directories = (
            "raw",
            "normalized",
            "sources",
            "knowledge",
            "embeddings",
            "indexes",
            "snapshots",
            "manifests",
            "audit",
            "logs",
            "checkpoints",
        )

        for name in directories:
            (self.root / name).mkdir(
                parents=True,
                exist_ok=True,
            )
