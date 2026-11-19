"""Presentation-only speech sanitization must handle escaped web content."""
from __future__ import annotations

import pytest

from aura_core.tts.text import clean_for_speech


def test_nested_html_escape_cannot_make_url_spoken():
    spoken = clean_for_speech("Özet: &amp;#104;ttps://example.org/private Ve devam.")
    assert "example.org" not in spoken
    assert "private" not in spoken
    assert "Ve devam." in spoken


def test_escaped_script_style_content_removed_before_speech():
    line = "Merhaba &lt;script&gt;SECRET&lt;/script&gt; dünya."
    assert clean_for_speech(line) == "Merhaba dünya."
    assert clean_for_speech("Hello &amp;lt;style&amp;gt;SECRET&amp;lt;/style&amp;gt; world") == "Hello world"


def test_bidi_formatting_characters_not_spoken_or_preserved():
    spoken = clean_for_speech("AURA\u202e kontrol\u202c\u200f normal")
    assert "kontrol" in spoken
    assert "\u202e" not in spoken
    assert "\u200f" not in spoken


def test_fenced_code_markdown_links_and_plain_text_regressions():
    source = "Merhaba. ```sh\nsecret\n``` [Doküman](https://example.org) **güzel**."
    spoken = clean_for_speech(source)
    assert spoken == "Merhaba. Doküman güzel."
    assert clean_for_speech("Kısa yanıt.") == "Kısa yanıt."


@pytest.mark.parametrize("source", [
    "https://example.org/token",
    "&amp;#104;ttps://example.org/token",
    "www.example.org/token",
    "[link](https://example.org/token)",
])
def test_sensitive_urls_never_spoken(source):
    assert "example.org" not in clean_for_speech(source)
