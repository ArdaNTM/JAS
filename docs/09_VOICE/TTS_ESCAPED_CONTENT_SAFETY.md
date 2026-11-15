# Voice speech text preprocessing — encoded-content safety (feature #15 support)

The existing `clean_for_speech` function now decodes a bounded two levels of escaped HTML before applying URL/code/markup stripping. It also removes Unicode format controls (for example bidi overrides), and excludes script/style element bodies from spoken output. No change is made to inference, MCP authorization, voice provider selection, or original source/audit evidence: the function is presentation-only.

This reduces the chance that encoded URLs or invisible controls cause unintended narration. It **does not** guarantee secret detection, perfect markdown parsing, naturalness, measured latency, or a complete multilingual interruption pipeline. Feature #15 remains partial until real Piper/Kokoro hardware playback, streaming latency and interaction acceptance are verified.

Tests: `cd core && uv run pytest -q tests/test_tts_text_safety.py`; full CI and deterministic release-lock verifier required.
