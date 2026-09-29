import pytest
from pydantic import ValidationError

from aura_core.config.backend import BackendConfig


def test_backend_config_accepts_valid_values() -> None:
    config = BackendConfig(
        endpoint="http://127.0.0.1:11434",
        timeout=45.0,
    )

    assert config.endpoint == "http://127.0.0.1:11434"
    assert config.timeout == 45.0


def test_backend_config_defaults() -> None:
    config = BackendConfig()

    assert config.endpoint == "http://127.0.0.1:11434"
    assert config.timeout == 120.0


def test_backend_config_rejects_empty_endpoint() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(endpoint="")


def test_backend_config_rejects_zero_timeout() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(timeout=0.0)


def test_backend_config_rejects_negative_timeout() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(timeout=-1.0)


def test_backend_config_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(
            unexpected="value",
        )


def test_backend_config_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "AURA_BACKEND_ENDPOINT",
        "http://127.0.0.1:11435",
    )
    monkeypatch.setenv(
        "AURA_BACKEND_TIMEOUT",
        "30.0",
    )

    config = BackendConfig.from_environment()

    assert config.endpoint == "http://127.0.0.1:11435"
    assert config.timeout == 30.0


def test_backend_config_environment_defaults(monkeypatch) -> None:
    monkeypatch.delenv(
        "AURA_BACKEND_ENDPOINT",
        raising=False,
    )
    monkeypatch.delenv(
        "AURA_BACKEND_TIMEOUT",
        raising=False,
    )

    config = BackendConfig.from_environment()

    assert config.endpoint == "http://127.0.0.1:11434"
    assert config.timeout == 120.0