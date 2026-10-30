"""Preflight the same faster-whisper model used by /api/speech/transcribe.

Run from the Windows launcher, before advertising AURA as ready. The initial
invocation may download the selected model into the standard Hugging Face
cache. No cloud inference endpoint is contacted; only model acquisition
may require network access.
"""
from __future__ import annotations

import os
import sys


def prepare_stt_model() -> tuple[str, str]:
    from faster_whisper import WhisperModel
    from aura_core.application.api import resolve_stt_runtime

    name = os.getenv("AURA_STT_MODEL", "small").strip()
    if not name:
        raise ValueError("AURA_STT_MODEL must not be empty")
    threads = max(1, min(16, int(os.getenv("AURA_STT_CPU_THREADS", str(min(8, os.cpu_count() or 4))))))

    try:
        device, compute_type = resolve_stt_runtime()
    except Exception:
        # Match the Core transcription endpoint's bounded CPU fallback.
        device, compute_type = "cpu", "int8"
    try:
        WhisperModel(name, device=device, compute_type=compute_type, cpu_threads=threads)
    except Exception:
        if device != "cuda":
            raise
        # Never accept an unavailable CUDA runtime as a reason to silently
        # route audio to a remote service.
        WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)
        device = "cpu"
    return name, device


def main() -> int:
    try:
        model, device = prepare_stt_model()
    except Exception as exc:
        print(
            "AURA STT preflight failed: local faster-whisper model cannot load "
            f"({type(exc).__name__}). Check AURA_STT_MODEL, model download/cache, "
            "internet access for initial model acquisition, and Windows CTranslate2 dependencies.",
            file=sys.stderr,
        )
        return 1
    print(f"AURA STT ready: model={model}, device={device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
