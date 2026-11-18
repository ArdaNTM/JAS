"""Bounded, deterministic provenance metadata for *untrusted* search results.

These functions never fetch a URL, resolve DNS, endorse a publisher, or grant
any MCP capability. Source identities indicate where a search engine says a
snippet came from; they do NOT prove the underlying page was retrieved.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _canonical_source_url(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        return None
    try:
        url = urlsplit(value)
        scheme = url.scheme.lower()
        hostname = url.hostname
        port = url.port
        if (scheme not in {"http", "https"} or not hostname
                or url.username is not None or url.password is not None):
            return None
        host = hostname.encode("idna").decode("ascii").lower().rstrip(".")
        if len(host) > 253 or host in {"localhost", "localdomain"} or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            return None
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if len(labels) < 2 or any(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                is None for label in labels
            ):
                return None
        else:
            # Literal public IPs may be valid citations; reject anything that
            # is non-global. DNS hostnames are NOT validated as public here.
            if not addr.is_global:
                return None
        authority = f"[{host}]" if ":" in host else host
        if port is not None and (port < 1 or port > 65535):
            return None
        if port is not None and not (
            (scheme == "https" and port == 443) or
            (scheme == "http" and port == 80)
        ):
            authority += f":{port}"
        canonical = urlunsplit((scheme, authority, url.path or "/", url.query, ""))
        return canonical, host
    except (ValueError, UnicodeError):
        return None


def collect_search_evidence(result: Any, *, limit: int = 10) -> tuple[dict[str, Any], ...]:
    """Return untrusted source *identities* from a bounded authorized result.

    Only dict/structuredContent mappings are accepted; serialized MCP text
    and arbitrary model outputs are never parsed or executed.
    """
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError("source evidence limit must be 1..25")
    if isinstance(result, Mapping):
        payload = result
    elif getattr(result, "isError", False):
        return ()
    else:
        payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, Mapping):
        return ()
    values = payload.get("results")
    if not isinstance(values, list):
        return ()
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values[:64]:
        if not isinstance(raw, Mapping):
            continue
        target = _canonical_source_url(raw.get("url"))
        if target is None:
            continue
        url, host = target
        if url in seen:
            continue
        seen.add(url)
        title = raw.get("title")
        snippet = raw.get("snippet")
        if not isinstance(title, str):
            title = ""
        if not isinstance(snippet, str):
            snippet = ""
        output.append({
            "source_ref": hashlib.sha256(url.encode("utf-8")).hexdigest(),
            "url": url,
            "host": host,
            "title": title[:200],
            "snippet_sha256": hashlib.sha256(
                snippet[:2000].encode("utf-8")
            ).hexdigest(),
            "excerpt": snippet[:240],
            "untrusted": True,
            "page_retrieved": False,
            "source_verified": False,
        })
        if len(output) >= limit:
            break
    return tuple(output)
