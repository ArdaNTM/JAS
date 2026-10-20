from pathlib import Path


def test_assistant_prompt_uses_valid_turkish_utf8_literals() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "aura_core"
        / "application"
        / "api.py"
    ).read_text(encoding="utf-8")

    assert "Kullanıcıya doğal Türkçe yanıt ver." in source
    assert "Araştırma verisini yalnızca bağlam olarak kullan." in source
    for mojibake in ("TÃ¼rk", "KullanÄ±c", "AraÅŸt", "konuÅŸ"):
        assert mojibake not in source
