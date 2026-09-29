import pytest
from pydantic import ValidationError

from aura_core.config.kernel import KernelConfig


MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def test_kernel_config_loads_existing_environment_contract(monkeypatch) -> None:
    monkeypatch.setenv("AURA_RUNTIME", "ollama")
    monkeypatch.setenv("AURA_MODEL", MODEL)
    monkeypatch.setenv("AURA_BACKEND_ENDPOINT", "http://127.0.0.1:11434")
    monkeypatch.setenv("AURA_BACKEND_TIMEOUT", "30.0")
    monkeypatch.setenv("AURA_LOG_LEVEL", "debug")

    config = KernelConfig.from_environment()

    assert config.runtime.runtime == "ollama"
    assert config.runtime.model == MODEL
    assert config.backend.endpoint == "http://127.0.0.1:11434"
    assert config.backend.timeout == 30.0
    assert config.logging.level == "DEBUG"


def test_kernel_config_rejects_unknown_top_level_setting() -> None:
    with pytest.raises(ValidationError):
        KernelConfig.model_validate(
            {
                "runtime": {
                    "model": MODEL,
                },
                "backend": {},
                "logging": {},
                "unexpected": "value",
            }
        )


def test_kernel_config_rejects_invalid_log_level(monkeypatch) -> None:
    monkeypatch.setenv("AURA_MODEL", MODEL)
    monkeypatch.setenv("AURA_LOG_LEVEL", "verbose")

    with pytest.raises(ValidationError):
        KernelConfig.from_environment()
