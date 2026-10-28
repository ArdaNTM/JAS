"""Fail-closed rollout gate for portable remote-persistence mode.

Local mode preserves the existing development/test behavior. Remote mode is
intentionally blocked until every durable store and artifact writer has been
migrated to remote adapters; accepting endpoint settings alone would create a
false sense of safety while SQLite stores still write to disk.
"""
from __future__ import annotations

import os
from enum import StrEnum


class StorageMode(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


def storage_mode_from_environment() -> StorageMode:
    raw = os.getenv("AURA_STORAGE_MODE", StorageMode.LOCAL.value).strip().lower()
    try:
        return StorageMode(raw)
    except ValueError as exc:
        raise RuntimeError("AURA_STORAGE_MODE must be 'local' or 'remote'") from exc


def validate_storage_mode() -> None:
    """Prevent remote deployments from silently using the existing local stores.

    The remote persistence adapters are not yet wired into every composition
    path. Refusing startup is safer than partially remote operation with hidden
    SQLite/temp-file persistence.
    """
    if storage_mode_from_environment() is StorageMode.REMOTE:
        raise RuntimeError(
            "AURA_STORAGE_MODE=remote is fail-closed: remote persistence adapters "
            "are not yet integrated across all durable stores. Startup is blocked "
            "to prevent local-disk fallback. Use local mode only for development "
            "until the remote-storage migration is complete."
        )
