"""STT preflight regressions; never download or initialize real models in CI."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_preflight():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_stt.py"
    spec = importlib.util.spec_from_file_location("_aura_test_stt_prepare", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_initializes_same_configured_local_model(monkeypatch):
    from aura_core.application import api as api_module
    calls = []

    class Whisper:
        def __init__(self, model, **kwargs):
            calls.append((model, kwargs))

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(api_module, "resolve_stt_runtime", lambda: ("cpu", "int8"))
    monkeypatch.setenv("AURA_STT_MODEL", "small")
    name, device = load_preflight().prepare_stt_model()
    assert (name, device) == ("small", "cpu")
    assert calls[0][0] == "small"
    assert calls[0][1]["compute_type"] == "int8"


def test_preflight_cuda_model_failure_tries_local_cpu(monkeypatch):
    from aura_core.application import api as api_module
    calls = []

    class Whisper:
        def __init__(self, model, **kwargs):
            calls.append(kwargs["device"])
            if kwargs["device"] == "cuda":
                raise RuntimeError("no CUDA library")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(api_module, "resolve_stt_runtime", lambda: ("cuda", "float16"))
    monkeypatch.setenv("AURA_STT_MODEL", "small")
    assert load_preflight().prepare_stt_model() == ("small", "cpu")
    assert calls == ["cuda", "cpu"]


def test_preflight_failure_reports_type_without_private_path(monkeypatch, capsys):
    from aura_core.application import api as api_module

    class Whisper:
        def __init__(self, model, **kwargs):
            raise OSError("private-path C:/Users/person/secret-file")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(api_module, "resolve_stt_runtime", lambda: ("cpu", "int8"))
    assert load_preflight().main() == 1
    stderr = capsys.readouterr().err
    assert "OSError" in stderr
    assert "private-path" not in stderr
    assert "secret-file" not in stderr


def test_preflight_rejects_blank_model(monkeypatch):
    monkeypatch.setenv("AURA_STT_MODEL", " ")
    with pytest.raises(ValueError, match="must not be empty"):
        load_preflight().prepare_stt_model()
