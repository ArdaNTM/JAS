"""One-shot local Kokoro WAV verification; run with the Core venv Python."""

from __future__ import annotations

from pathlib import Path

import soundfile as sf
from kokoro import KPipeline


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "artifacts" / "kokoro-smoke.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code="a")
    chunks = list(pipeline("Hello from AURA. Local speech synthesis is ready.", voice="af_heart", speed=1.0))
    if not chunks:
        raise RuntimeError("Kokoro returned no audio")
    sf.write(output, chunks[0].audio, 24000, format="WAV")
    if not output.is_file() or output.stat().st_size < 1024:
        raise RuntimeError("Kokoro WAV output was not created")
    print(output)


if __name__ == "__main__":
    main()
