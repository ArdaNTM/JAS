"""Regression for Piper phoneme keys that collide in PowerShell's JSON parser."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate_piper_voice_config.py"


def run_validator(config: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(config)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_case_distinct_phoneme_keys_and_utf8_bom_pass(tmp_path: Path) -> None:
    config = tmp_path / "tr_TR-dfki-medium.onnx.json"
    # Windows PowerShell 5.1 ConvertFrom-Json can reject these distinct keys.
    data = {"language": {"code": "tr_TR"}, "phoneme_id_map": {
        "ÊŒ": [1], "Êœ": [2], "A": [3], "a": [4],
    }}
    config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
    result = run_validator(config)
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_real_duplicate_case_sensitive_keys_use_piper_python_semantics(tmp_path: Path) -> None:
    config = tmp_path / "tr_TR.onnx.json"
    config.write_text(
        '{"language":{"code":"tr_TR"},"phoneme_id_map":{"a":[1],"a":[2]}}',
        encoding="utf-8",
    )
    assert run_validator(config).returncode == 0


def test_language_mismatch_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "en_US.onnx.json"
    config.write_text('{"language":{"code":"en_US"}}', encoding="utf-8")
    result = run_validator(config)
    assert result.returncode == 1
    assert "tr_TR" in result.stderr


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "broken.onnx.json"
    config.write_text('{"language":{"code":"tr_TR"', encoding="utf-8")
    result = run_validator(config)
    assert result.returncode == 1
    assert "invalid JSON" in result.stderr


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    result = run_validator(tmp_path / "missing.onnx.json")
    assert result.returncode == 1


def test_wrong_number_of_arguments_is_rejected() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
