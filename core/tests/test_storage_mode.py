import pytest

from aura_core.config.storage import (
    StorageMode,
    storage_mode_from_environment,
    validate_storage_mode,
)


def test_storage_mode_defaults_to_local_for_existing_development(monkeypatch) -> None:
    monkeypatch.delenv("AURA_STORAGE_MODE", raising=False)
    assert storage_mode_from_environment() is StorageMode.LOCAL
    validate_storage_mode()


@pytest.mark.parametrize("value", ["local", "LOCAL", " Local "])
def test_storage_mode_accepts_local_case_insensitively(monkeypatch, value: str) -> None:
    monkeypatch.setenv("AURA_STORAGE_MODE", value)
    assert storage_mode_from_environment() is StorageMode.LOCAL
    validate_storage_mode()


def test_storage_mode_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("AURA_STORAGE_MODE", "fallback")
    with pytest.raises(RuntimeError, match="AURA_STORAGE_MODE must be"):
        validate_storage_mode()


def test_remote_mode_fails_closed_even_if_endpoints_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", "postgresql+asyncpg://example.invalid/aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_BUCKET", "aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "not-a-real-key")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", "not-a-real-secret")
    with pytest.raises(RuntimeError, match="Startup is blocked"):
        validate_storage_mode()
