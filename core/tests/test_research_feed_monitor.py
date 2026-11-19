"""Offline RSS/Atom detector with deterministic and fail-closed XML handling."""
import pytest
from aura_core.research.feed_monitor import detect_new_items, parse_feed


def rss(*items):
    return "<rss><channel>" + "".join(items) + "</channel></rss>"


def item(title, url, guid):
    return (f"<item><title>{title}</title><link>{url}</link>"
            f"<guid>{guid}</guid></item>")


def test_new_feed_items_and_order_invariance():
    first = item("First", "https://example.org/1", "guid-1")
    second = item("Second", "https://example.org/2", "guid-2")
    a = parse_feed(rss(first), feed_key="feed-1")
    b = parse_feed(rss(second, first), feed_key="feed-1")
    c = parse_feed(rss(first, second), feed_key="feed-1")
    assert b.fingerprint == c.fingerprint
    new = detect_new_items(a, b)
    assert len(new) == 1
    assert new[0].title == "Second"
    assert new[0].untrusted is True
    assert b.publisher_verified is False
    assert detect_new_items(b, c) == ()


def test_atom_alternate_link_and_id():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><id>tag:example.org,2026:item</id><title>Article</title>
    <link rel="alternate" href="https://example.org/a"/></entry></feed>"""
    snap = parse_feed(xml, feed_key="academic")
    assert snap.items[0].url == "https://example.org/a"


@pytest.mark.parametrize("xml", [
    '<!DOCTYPE rss [<!ENTITY x "secret">]><rss><channel/></rss>',
    rss(item("x", "http://example.org/x", "x")),
    rss(item("x", "https://127.0.0.1/x", "x")),
    rss(item("x", "https://localhost/x", "x")),
    rss(item("x", "https://user:password@example.org/x", "x")),
    rss(item("x", "https://example.org:8080/x", "x")),
    rss(item("x", "file:///etc/passwd", "x")),
])
def test_unsafe_feed_urls_and_entities_rejected(xml):
    with pytest.raises(ValueError):
        parse_feed(xml, feed_key="safe")


def test_duplicate_identity_conflict_and_cross_feed_guard():
    first = item("A", "https://example.org/a", "same")
    changed = item("B", "https://example.org/b", "same")
    with pytest.raises(ValueError):
        parse_feed(rss(first, changed), feed_key="safe")
    with pytest.raises(ValueError):
        detect_new_items(
            parse_feed(rss(first), feed_key="a"),
            parse_feed(rss(first), feed_key="b"),
        )


def test_bounded_input_and_config():
    with pytest.raises(ValueError):
        parse_feed("x" * 262145, feed_key="safe")
    with pytest.raises(ValueError):
        parse_feed(rss(), feed_key="safe", max_items=True)
    xml = rss(*(item(str(i), f"https://example.org/{i}", str(i))
                for i in range(3)))
    with pytest.raises(ValueError):
        parse_feed(xml, feed_key="safe", max_items=2)
