"""Bounded multi-query public research through the existing MCP Gateway.

The adapter never performs HTTP/network fetches, grants permissions, invokes
providers directly, or treats third-party pages as instructions. It only
composes already-registered MCPResearchSource.search() operations, each of
which crosses the Gateway authorization boundary independently.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.research.mcp_source import MCPResearchSource

_MAX_QUERIES = 4
_MAX_RESULTS = 12
_MAX_QUERY_CHARS = 256
_MAX_URL_CHARS = 2048
_MAX_TITLE_CHARS = 300
_MAX_SNIPPET_CHARS = 1200
_MAX_PROVIDER_RESULTS = 10
_INVALID = re.compile(r"[\x00-\x1f\x7f]")


class ResearchAuthorizationError(PermissionError):
    """At least one query was not ALLOWed by the authoritative Gateway."""


class ResearchResponseError(RuntimeError):
    """Gateway/provider output failed the bounded evidence contract."""


@dataclass(frozen=True, slots=True)
class EvidenceHit:
    query_index: int
    rank: int
    url: str
    url_sha256: str
    title: str
    snippet: str
    backend: str
    provider_id: str


@dataclass(frozen=True, slots=True)
class MultiQueryEvidence:
    queries: tuple[str, ...]
    results: tuple[EvidenceHit, ...]
    searched_count: int
    truncated: bool


def _identifier(value: str, name: str, maximum: int = 128) -> str:
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value != value.strip() or _INVALID.search(value)):
        raise ValueError(f"invalid {name}")
    return value


def _query(value: str) -> str:
    if not isinstance(value, str) or len(value) > _MAX_QUERY_CHARS or _INVALID.search(value):
        raise ValueError("invalid research query")
    result = " ".join(value.split())
    if not result:
        raise ValueError("research query is empty")
    return result


def _text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or _INVALID.search(value):
        raise ResearchResponseError(f"invalid {name} in provider evidence")
    return value


def _public_link(value: object) -> str:
    """Reject clearly unsafe *reported* references; this is not a fetch/SSRF gate.

    The actual MCP fetch tool must separately validate DNS, redirects, IP ranges,
    transport and response limits at time of use.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_URL_CHARS:
        raise ResearchResponseError("invalid result URL")
    if _INVALID.search(value) or value != value.strip():
        raise ResearchResponseError("invalid result URL")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port  # invalid ports raise ValueError
    except ValueError as exc:
        raise ResearchResponseError("malformed result URL") from exc
    if (parsed.scheme not in ("http", "https") or not host
            or parsed.username is not None or parsed.password is not None
            or port == 0 or host.endswith(".local") or host.casefold() == "localhost"):
        raise ResearchResponseError("unsupported result URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Reject non-FQDNs and weird single-label hostnames; DNS is untrusted.
        if "." not in host or host.startswith(".") or host.endswith("."):
            raise ResearchResponseError("invalid public hostname")
    else:
        if not address.is_global:
            raise ResearchResponseError("nonpublic result URL")
    if "\\" in value:
        raise ResearchResponseError("ambiguous result URL")
    return value


def _provider_payload(result: object) -> dict[str, Any]:
    if result is None or getattr(result, "is_error", False) or getattr(result, "isError", False):
        raise ResearchResponseError("research MCP provider returned an error")
    if isinstance(result, dict):
        if result.get("isError") is True or result.get("status") == "failed":
            raise ResearchResponseError("research MCP tool returned a failure")
        payload = result.get("structuredContent", result.get("structured_content", result))
    else:
        payload = getattr(result, "structured_content", None)
        if payload is None:
            payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, dict):
        raise ResearchResponseError("missing structured research evidence")
    return payload


class MultiQueryResearch:
    """Sequential fail-closed multi-query workflow using existing MCP Gateway."""

    def __init__(self, source: MCPResearchSource) -> None:
        if not isinstance(source, MCPResearchSource):
            raise TypeError("source must be MCPResearchSource")
        self._source = source

    async def search(
        self,
        queries: list[str] | tuple[str, ...],
        *,
        principal_id: str,
        resource_scope: str,
        risk_level: RiskLevel,
        task_id: str,
    ) -> MultiQueryEvidence:
        _identifier(principal_id, "principal_id")
        _identifier(resource_scope, "resource_scope", 256)
        _identifier(task_id, "task_id")
        if not isinstance(risk_level, RiskLevel):
            raise ValueError("risk_level must be a RiskLevel")
        if not isinstance(queries, (tuple, list)) or not 1 <= len(queries) <= _MAX_QUERIES:
            raise ValueError("must supply 1..4 bounded queries")
        normalized = tuple(_query(item) for item in queries)
        if len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("duplicate queries are not allowed")

        hits: list[EvidenceHit] = []
        seen_urls: set[str] = set()
        truncated = False
        searched_count = 0
        for query_index, query in enumerate(normalized, start=1):
            # No direct provider or HTTP calls. Every individual search uses
            # distinct task/request IDs for independent Gateway audit events.
            try:
                response = await self._source.search(
                    principal_id=principal_id,
                    query=query,
                    resource_scope=resource_scope,
                    risk_level=risk_level,
                    task_id=f"{task_id}:query:{query_index}",
                )
            except Exception as exc:
                raise ResearchResponseError("research Gateway invocation failed") from exc
            if getattr(response, "decision", None) is not AuthorizationDecision.ALLOW:
                raise ResearchAuthorizationError("research query was not authorized")
            provider_id = _text(getattr(response, "provider_id", None), "provider", 128)
            if not provider_id:
                raise ResearchResponseError("research provider identity missing")
            payload = _provider_payload(getattr(response, "result", None))
            backend = _text(payload.get("backend", ""), "research backend", 64)
            raw_results = payload.get("results")
            if not isinstance(raw_results, list) or len(raw_results) > _MAX_PROVIDER_RESULTS:
                raise ResearchResponseError("invalid bounded research result count")
            searched_count += 1
            for item in raw_results:
                if not isinstance(item, dict):
                    raise ResearchResponseError("research result must be an object")
                url = _public_link(item.get("url"))
                title = _text(item.get("title"), "result title", _MAX_TITLE_CHARS)
                snippet = _text(item.get("snippet"), "result snippet", _MAX_SNIPPET_CHARS)
                if not title.strip():
                    raise ResearchResponseError("result title cannot be empty")
                rank = item.get("rank")
                if type(rank) is not int or not 1 <= rank <= _MAX_PROVIDER_RESULTS:
                    raise ResearchResponseError("invalid result rank")
                # Deduplicate only metadata. URLs must not be fetched here;
                # a URL digest is an identifier, NOT a content authenticity proof.
                dedupe_key = url.split("#", 1)[0]
                if dedupe_key in seen_urls:
                    continue
                seen_urls.add(dedupe_key)
                if len(hits) >= _MAX_RESULTS:
                    truncated = True
                    continue
                hits.append(EvidenceHit(
                    query_index=query_index, rank=rank, url=url,
                    url_sha256=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                    title=title, snippet=snippet, backend=backend,
                    provider_id=provider_id,
                ))
        return MultiQueryEvidence(normalized, tuple(hits), searched_count, truncated)
