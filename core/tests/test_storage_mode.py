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


def test_remote_mode_requires_complete_remote_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", "postgresql+asyncpg://example.invalid/aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_BUCKET", "aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "not-a-real-key")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", "not-a-real-secret")
    validate_storage_mode()


def test_remote_mode_rejects_missing_object_credentials(monkeypatch) -> None:
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", "postgresql+asyncpg://example.invalid/aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_BUCKET", "aura")
    monkeypatch.delenv("AURA_OBJECT_STORAGE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AURA_OBJECT_STORAGE_SECRET_KEY", raising=False)
    monkeypatch.delenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(RuntimeError, match="requires remote persistence settings"):
        validate_storage_mode()

def test_build_app_selects_remote_stores_without_creating_local_state(
    monkeypatch, tmp_path
) -> None:
    """The production composition root must stop before opening SQLite in remote mode."""
    from aura_core.main import build_app

    local_data = tmp_path / "must-not-be-created"
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", "postgresql+asyncpg://example.invalid/aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_BUCKET", "aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "test-only-key")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-only-secret")
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setenv("HOME", str(local_data))

    app = build_app()

    assert not local_data.exists(), "remote composition must not create local persistent state"
    assert app.state.storage_mode is StorageMode.REMOTE
    assert type(app.state.task_state_machine).__name__ == "PostgreSQLTaskStateMachine"
    assert type(app.state.workflow_store).__name__ == "PostgreSQLWorkflowStore"
    assert type(app.state.task_memory).__name__ == "PostgreSQLTaskMemoryCoordinator"
    assert app.state.checkpoint_artifacts is not None
