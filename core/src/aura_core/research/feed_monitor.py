"""Bounded read-only RSS/Atom comparison of pre-authorized input."""
from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

FEED_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z", re.ASCII)
ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True, slots=True)
class FeedItem:
    item_id: str
    title: str
    url: str
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class FeedSnapshot:
    feed_key: str
    items: tuple[FeedItem, ...]
    fingerprint: str
    publisher_verified: bool = False


def _public_https_url(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 1500:
        raise ValueError("invalid feed item URL")
    parsed = urlsplit(value.strip())
    host = parsed.hostname
    if (parsed.scheme != "https" or not host
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise ValueError("HTTPS URL without credentials required")
    if host.lower() == "localhost" or host.lower().endswith((".local", ".internal")):
        raise ValueError("local host is not accepted")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            raise ValueError("unqualified host is not accepted")
    else:
        if not address.is_global:
            raise ValueError("non-global IP is not accepted")
    return parsed.geturl()


def _text(node: ET.Element, selector: str) -> str:
    value = node.find(selector)
    return value.text.strip() if value is not None and value.text else ""


def parse_feed(xml_text: str, *, feed_key: str, max_items: int = 200) -> FeedSnapshot:
    """Parse input locally; never fetch a link or grant execution authority."""
    if type(feed_key) is not str or not FEED_KEY.fullmatch(feed_key):
        raise ValueError("invalid feed key")
    if type(max_items) is not int or not 1 <= max_items <= 200:
        raise ValueError("max_items must be 1..200")
    if type(xml_text) is not str or len(xml_text.encode("utf-8")) > 262144:
        raise ValueError("bounded XML text required")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml_text, re.IGNORECASE):
        raise ValueError("DTD and entities are forbidden")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("invalid feed XML") from exc
    if sum(1 for _ in root.iter()) > 2000:
        raise ValueError("too many XML elements")
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS channel required")
        nodes = channel.findall("item")
        def fields(node: ET.Element) -> tuple[str, str, str]:
            title = _text(node, "title")
            url = _text(node, "link")
            return title, url, _text(node, "guid") or url
    elif root.tag == ATOM_NS + "feed":
        nodes = root.findall(ATOM_NS + "entry")
        def fields(node: ET.Element) -> tuple[str, str, str]:
            links = [
                link.attrib.get("href", "")
                for link in node.findall(ATOM_NS + "link")
                if link.attrib.get("rel", "alternate") == "alternate"
            ]
            url = links[0] if links else ""
            return _text(node, ATOM_NS + "title"), url, _text(node, ATOM_NS + "id") or url
    else:
        raise ValueError("unsupported feed format")
    if len(nodes) > max_items:
        raise ValueError("feed item budget exceeded")
    found: dict[str, FeedItem] = {}
    for node in nodes:
        title, url, key = fields(node)
        if not 1 <= len(title) <= 180 or any(ord(c) < 32 for c in title):
            raise ValueError("invalid feed title")
        safe_url = _public_https_url(url)
        if not key or len(key) > 1500:
            raise ValueError("invalid entry ID")
        identity = hashlib.sha256(key.encode("utf-8")).hexdigest()
        item = FeedItem(identity, title, safe_url)
        if identity in found and found[identity] != item:
            raise ValueError("conflicting duplicate entry identity")
        found[identity] = item
    ordered = tuple(found[k] for k in sorted(found))
    digest = hashlib.sha256(
        "\n".join(item.item_id for item in ordered).encode("ascii")
    ).hexdigest()
    return FeedSnapshot(feed_key, ordered, digest)


def detect_new_items(before: FeedSnapshot, after: FeedSnapshot) -> tuple[FeedItem, ...]:
    """Return newly observed IDs, never infer publication deletion."""
    if type(before) is not FeedSnapshot or type(after) is not FeedSnapshot:
        raise ValueError("FeedSnapshot objects required")
    if before.feed_key != after.feed_key:
        raise ValueError("different feeds cannot be compared")
    previous = {item.item_id for item in before.items}
    return tuple(item for item in after.items if item.item_id not in previous)
