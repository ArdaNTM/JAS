from aura_core.tts.config import KokoroMCPConfig


def test_piper_provider_can_be_selected_without_changing_capability_contract(monkeypatch) -> None:
    monkeypatch.setenv("AURA_TTS_PROVIDER", "piper")
    config = KokoroMCPConfig.from_env()
    assert config.provider_id == "tts.piper"
    assert config.service_name == "piper-local-tts"
    assert config.args[0].endswith("piper_tts_mcp.py")


def test_kokoro_remains_default_tts_provider(monkeypatch) -> None:
    monkeypatch.delenv("AURA_TTS_PROVIDER", raising=False)
    config = KokoroMCPConfig.from_env()
    assert config.provider_id == "tts.kokoro"
    assert config.args[0].endswith("kokoro_tts_mcp.py")


def test_unknown_tts_provider_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("AURA_TTS_PROVIDER", "imaginary")
    try:
        KokoroMCPConfig.from_env()
    except ValueError as exc:
        assert "AURA_TTS_PROVIDER" in str(exc)
    else:
        raise AssertionError("Unsupported provider must be rejected")
