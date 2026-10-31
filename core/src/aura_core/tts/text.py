"""Deterministic, bounded text normalization for local spoken output.

Only presentation is transformed; model/tool results and audit evidence remain
unchanged. In particular URLs and fenced code are never spoken verbatim.
"""
from __future__ import annotations

import html
import re


def clean_for_speech(source: str) -> str:
    text = source[:16000]
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\(\s*(?:https?://|www\.)[^)]*\)", r"\1", text, flags=re.I)
    text = re.sub(r"(?<!\w)(?:https?://|www\.)[^\s<>{}\[\]\"']+", " ", text, flags=re.I)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m[1] or m[2], text)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)", lambda m: m[1] or m[2], text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\[\^?\d+\]|\[kaynak\s*\d+\]", " ", text, flags=re.I)
    text = re.sub(r"[*#`~_]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()
