"""Configuration validation for portable remote-persistence mode.

Remote composition selects PostgreSQL and S3-backed adapters exclusively. Missing
remote settings are fatal; there is no SQLite or local-file fallback.
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
    """Validate every mandatory endpoint before selecting remote persistence."""
    if storage_mode_from_environment() is not StorageMode.REMOTE:
        return
    database_url = os.getenv("AURA_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        raise RuntimeError("AURA_STORAGE_MODE=remote requires a PostgreSQL AURA_DATABASE_URL")
    required = (
        "AURA_OBJECT_STORAGE_ENDPOINT",
        "AURA_OBJECT_STORAGE_BUCKET",
    )
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if not (os.getenv("AURA_OBJECT_STORAGE_ACCESS_KEY", "").strip()
            or os.getenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "").strip()):
        missing.append("AURA_OBJECT_STORAGE_ACCESS_KEY")
    if not (os.getenv("AURA_OBJECT_STORAGE_SECRET_KEY", "").strip()
            or os.getenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", "").strip()):
        missing.append("AURA_OBJECT_STORAGE_SECRET_KEY")
    if missing:
        raise RuntimeError(
            "AURA_STORAGE_MODE=remote requires remote persistence settings: "
            + ", ".join(missing)
        )
