"""Bounded, principal-scoped lexical context for local speech recognition.

Retrieved memories are treated as untrusted text: only short candidate terms are
extracted, never instructions. This adapts decoding context; it does not train
or fine-tune the acoustic model.
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter

_DEFAULT_PROMPT = (
    "Türkçe konuşma. Doğa hakkında araştırma yap. Yapay zeka hakkında araştırma yap. "
    "Türkçe kelimeleri doğru yaz: araştırma, yapay zeka, doğa, hakkında, bilgi, "
    "özet, kaynaklar, dosyalar, hafıza, görsel, analiz, görev, izin, araç."
)
_STOP_WORDS = {
    "assistant", "user", "about", "please", "could", "would", "should", "have",
    "this", "that", "with", "from", "your", "they", "them", "there", "what",
    "when", "where", "which", "into", "then", "also", "only", "make", "use",
    "hakkında", "yap", "yapma", "yapın", "lütfen", "bunu", "şunu", "bana",
    "için", "ile", "veya", "ama", "fakat", "gibi", "daha", "çok", "bir", "bu",
    "şu", "ben", "sen", "biz", "siz", "onlar", "olarak", "olsun", "var", "yok",
}
_TOKEN_RE = re.compile(r"(?<![\w])(?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü.-]{2,}|[A-Z]{2,}(?:-[A-Z0-9]+)?|[\wÇĞİÖŞÜçğıöşü]{4,})(?![\w])", re.UNICODE)
_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
_lock = threading.Lock()


def extract_context_terms(records: list[object], *, limit: int = 12) -> tuple[str, ...]:
    """Extract frequent domain terms from scoped memory records, with strict bounds."""
    counts: Counter[str] = Counter()
    for record in records[:30]:
        content = getattr(record, "content", "")
        if not isinstance(content, str):
            continue
        # Cap each memory and ignore anything that looks like a prompt-control block.
        content = content[:1200]
        content = re.sub(r"(?is)<(system|assistant|developer|instruction)[^>]*>.*?</\1>", " ", content)
        for token in _TOKEN_RE.findall(content):
            clean = token.strip("._-")[:40]
            if len(clean) < 4 or clean.casefold() in _STOP_WORDS or clean.isdigit():
                continue
            if clean.isupper() or clean[0].isupper() or any(ch.isdigit() for ch in clean):
                counts[clean] += 2
            else:
                counts[clean] += 1
    return tuple(term for term, _ in counts.most_common(max(0, min(limit, 12))))


def build_stt_prompt(
    *,
    principal_id: str,
    static_prompt: str = _DEFAULT_PROMPT,
    memory_store: object | None = None,
    cache_seconds: int = 60,
) -> str:
    """Build a bounded prompt from scoped episodic memory; fail closed to static text."""
    terms: tuple[str, ...] = ()
    key = principal_id.strip()[:128]
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < max(0, cache_seconds):
            terms = cached[1]
    if not terms and memory_store is not None and key:
        try:
            records = memory_store.recall(principal_id=key, query="", limit=20)
            terms = extract_context_terms(records)
            with _lock:
                _cache[key] = (now, terms)
        except Exception:
            # STT must remain available if optional memory is offline.
            terms = ()
    prompt = re.sub(r"[\r\n\x00-\x1f]+", " ", static_prompt).strip()[:800]
    if terms:
        prompt += " Önceki konuşmalarda geçen olası özel adlar ve teknik terimler: " + ", ".join(terms) + "."
    return prompt[:1200]


def clear_context_cache() -> None:
    """Clear cached terms; exposed for deterministic tests and memory lifecycle hooks."""
    with _lock:
        _cache.clear()
