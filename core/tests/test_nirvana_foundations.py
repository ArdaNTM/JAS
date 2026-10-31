"""Bounded streaming speech orchestration and context-selection regressions."""
import asyncio
import pytest

from aura_core.application.context_synthesizer import ContextSynthesizer
from aura_core.application.streaming_speech import (
    SentenceAccumulator, StreamingSpeechCoordinator,
)


def test_sentence_assembler_waits_for_real_boundaries_and_preserves_order():
    b = SentenceAccumulator(min_chars=8, max_chars=60)
    assert b.feed("Merhaba bu uzun bir") == ()
    assert b.feed(" cevap. İkinci cüm") == ("Merhaba bu uzun bir cevap.",)
    assert b.feed("le hazır!") == ("İkinci cümle hazır!",)
    assert b.finish() == ()


def test_sentence_assembler_bounds_untrusted_deltas_and_audio_text():
    b = SentenceAccumulator(min_chars=8, max_chars=36)
    with pytest.raises(ValueError):
        b.feed("x" * 5000)
    out = b.feed("A" * 64)
    assert len(out) > 0
    assert all(len(x) <= 36 for x in out)
    assert b.finish()


def test_incremental_audio_overlaps_model_generation_and_preserves_order():
    async def run():
        first_audio = asyncio.Event()
        input_finished = asyncio.Event()
        rendered = []
        async def tokens():
            yield "Birinci cümle tamamlandı."
            await first_audio.wait()
            yield " İkinci cümle de bitti."
            input_finished.set()
        async def authorized_tts(text: str) -> bytes:
            if text.startswith("Birinci"):
                assert not input_finished.is_set()
                first_audio.set()
            return b"wav-bytes"
        coordinator = StreamingSpeechCoordinator(authorized_tts)
        async for segment in coordinator.render(tokens()):
            rendered.append(segment)
        assert [s.sequence for s in rendered] == [1, 2]
        assert [s.text for s in rendered] == [
            "Birinci cümle tamamlandı.", "İkinci cümle de bitti.",
        ]
        assert coordinator.last_stats is not None
        assert coordinator.last_stats.first_audio_ms is not None
        assert coordinator.last_stats.speech_segments == 2
    asyncio.run(asyncio.wait_for(run(), timeout=3))


def test_cancel_drops_pending_segments_without_replaying_audio():
    async def run():
        stop = asyncio.Event()
        async def tokens():
            yield "Merhaba. " * 100
            await asyncio.sleep(0.3)
        async def tts(text):
            stop.set()
            return b"safe"
        coordinator = StreamingSpeechCoordinator(tts, max_segments=200)
        chunks = []
        async for segment in coordinator.render(tokens(), interrupt=stop):
            chunks.append(segment)
        assert not chunks
        assert coordinator.last_stats is not None
        assert coordinator.last_stats.interrupted
    asyncio.run(run())


def test_relevance_budget_prefers_matching_memory_without_fabricating_context():
    synthesizer = ContextSynthesizer(max_memory_chars=256, memory_selection="relevance")
    result = synthesizer.synthesize(
        message="Orca proje durumunu özetle",
        memories=["Unrelated weather forecast " * 8,
                  "ORCA proje durumu: test sürüyor",
                  "ORCA proje durumu: test sürüyor"],
    )
    assert result.recalled_items == 2
    assert "ORCA proje durumu" in result.user_content
    assert result.user_content.index("ORCA proje durumu") < result.user_content.index("Unrelated")
    assert "untrusted reference data" in result.system_prompt


def test_legacy_context_selection_remains_default():
    memories = ["Birinci not", "İkinci not"]
    result = ContextSynthesizer().synthesize(message="Hello", memories=memories)
    assert result.user_content.index("Birinci not") < result.user_content.index("İkinci not")
    with pytest.raises(ValueError):
        ContextSynthesizer(memory_selection="model_decides")
