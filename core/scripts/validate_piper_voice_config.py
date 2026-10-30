"""Validate a locally downloaded Piper voice JSON with UTF-8, case-sensitive keys.

Windows PowerShell 5.1 ConvertFrom-Json treats JSON object keys as
case-insensitive, so valid distinct IPA/phoneme keys can collide. Piper's
Python loader uses the standard JSON parser; match that behavior here.
No dependency on Piper or a model download is required for validation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def validate_turkish_voice_config(path: Path) -> bool:
    with path.open("r", encoding="utf-8-sig") as handle:
        metadata = json.load(handle)
    if not isinstance(metadata, dict):
        return False
    language = metadata.get("language")
    return isinstance(language, dict) and language.get("code") == "tr_TR"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: validate_piper_voice_config.py <voice.onnx.json>", file=sys.stderr)
        return 2
    try:
        valid = validate_turkish_voice_config(Path(args[0]))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("Piper voice configuration is unreadable or invalid JSON.", file=sys.stderr)
        return 1
    if not valid:
        print("Piper voice configuration is missing language.code=tr_TR.", file=sys.stderr)
        return 1
    print("PASS: Turkish Piper voice JSON (UTF-8, case-sensitive phoneme keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
