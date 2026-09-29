import pytest
from pydantic import ValidationError

from aura_core.config.runtime import RuntimeConfig


def test_runtime_config_accepts_valid_values() -> None:
    config = RuntimeConfig(
        runtime="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.0,
        max_tokens=32,
    )

    assert config.runtime == "ollama"
    assert config.model == "qwen3:4b-instruct-2507-q4_K_M"
    assert config.temperature == 0.0
    assert config.max_tokens == 32


def test_runtime_config_defaults() -> None:
    config = RuntimeConfig(
        model="qwen3:4b-instruct-2507-q4_K_M",
    )

    assert config.runtime == "mock"
    assert config.temperature == 0.7
    assert config.max_tokens is None


def test_runtime_config_rejects_empty_model() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(model="")


def test_runtime_config_rejects_temperature_below_zero() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(
            model="qwen3:4b-instruct-2507-q4_K_M",
            temperature=-0.1,
        )


def test_runtime_config_rejects_temperature_above_two() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(
            model="qwen3:4b-instruct-2507-q4_K_M",
            temperature=2.1,
        )


def test_runtime_config_rejects_invalid_max_tokens() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(
            model="qwen3:4b-instruct-2507-q4_K_M",
            max_tokens=0,
        )


def test_runtime_config_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(
            model="qwen3:4b-instruct-2507-q4_K_M",
            unexpected="value",
        )


def test_runtime_config_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("AURA_RUNTIME", "ollama")
    monkeypatch.setenv(
        "AURA_MODEL",
        "qwen3:4b-instruct-2507-q4_K_M",
    )
    monkeypatch.setenv("AURA_TEMPERATURE", "0.0")
    monkeypatch.setenv("AURA_MAX_TOKENS", "32")

    config = RuntimeConfig.from_environment()

    assert config.runtime == "ollama"
    assert config.model == "qwen3:4b-instruct-2507-q4_K_M"
    assert config.temperature == 0.0
    assert config.max_tokens == 32


def test_runtime_config_requires_model_from_environment(monkeypatch) -> None:
    monkeypatch.delenv("AURA_MODEL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="AURA_MODEL environment variable is required",
    ):
        RuntimeConfig.from_environment()