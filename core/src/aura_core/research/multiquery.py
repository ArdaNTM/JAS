"""Bounded multi-query research through the *existing* MCP Gateway path.

Results are explicitly untrusted. No network, browser, file or provider call
exists here except MCPResearchSource.search -> MCPGateway.invoke. Gateway
denials abort the whole batch and no partial evidence is returned as complete.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit, urlunsplit

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayResponse
from aura_core.research.mcp_source import MCPResearchSource

_MAX_QUERIES = 3
_MAX_RESULTS = 20
_MAX_URL = 2048


class ResearchDenied(PermissionError):
    """The Gateway denied/deferred at least one research query."""


class ResearchMalformed(ValueError):
    """The tool returned malformed or unsafe evidence, not trusted citations."""


@dataclass(frozen=True, slots=True)
class ResearchFinding:
    query_index: int
    title: str
    url: str
    snippet: str
    source_label: str
    provider_id: str
    trust: str = "UNTRUSTED"


@dataclass(frozen=True, slots=True)
class ResearchBatch:
    queries: tuple[str, ...]
    findings: tuple[ResearchFinding, ...]
    complete: bool
    gateway_routed: bool


def _text(value: object, max_length: int) -> str:
    if not isinstance(value, str) or len(value) > max_length:
        raise ResearchMalformed("research evidence has invalid text")
    # Normalize controls to spaces; never execute source-provided instructions.
    return " ".join(value.split())[:max_length]


def _public_reference_url(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_URL:
        raise ResearchMalformed("research URL is malformed")
    if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ResearchMalformed("research URL contains controls")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ResearchMalformed("research URL is malformed") from exc
    if parts.scheme not in ("http", "https") or not host or not parts.netloc:
        raise ResearchMalformed("research URL must be HTTP(S)")
    if "@" in parts.netloc or port not in (None, 80, 443):
        raise ResearchMalformed("research URL contains credentials or unusual port")
    canonical_host = host.casefold().rstrip(".")
    if canonical_host == "localhost" or canonical_host.endswith((".localhost", ".local", ".internal", ".onion")):
        raise ResearchMalformed("research URL points to local resources")
    try:
        parsed_ip = ipaddress.ip_address(canonical_host)
    except ValueError:
        if "." not in canonical_host or len(canonical_host) > 253:
            raise ResearchMalformed("research URL host is invalid")
        # Reject numeric shorthand that URL clients may interpret as private IPs
        # (e.g. 127.1) rather than an ordinary DNS hostname.
        if all(ch in "0123456789." for ch in canonical_host):
            raise ResearchMalformed("research URL host is ambiguous")
    else:
        if not parsed_ip.is_global:
            raise ResearchMalformed("research URL points to a non-public address")
    # Fragment never changes the retrieved source; keep first-seen URL identity.
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, ""))


def _structured_response(response: object) -> tuple[dict, str]:
    if not isinstance(response, MCPGatewayResponse):
        raise ResearchMalformed("research Gateway response is invalid")
    if response.decision is not AuthorizationDecision.ALLOW:
        raise ResearchDenied("research Gateway did not authorize all queries")
    result = response.result
    if result is None or getattr(result, "is_error", False) is True or getattr(result, "isError", False) is True:
        raise ResearchMalformed("research tool returned failure or no results")
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is None and isinstance(result, dict):
        structured = result
    if not isinstance(structured, dict) or not isinstance(response.provider_id, str) or not response.provider_id:
        raise ResearchMalformed("research results must carry structured provider evidence")
    if "status" in structured and structured["status"] == "failed":
        raise ResearchMalformed("research tool failed")
    return structured, response.provider_id


async def bounded_multiquery_search(
    source: MCPResearchSource,
    *,
    principal_id: str,
    queries: Sequence[str],
    resource_scope: str,
    risk_level: RiskLevel,
    task_id: str,
    max_findings: int = 12,
) -> ResearchBatch:
    """Return only complete bounded evidence after every Gateway ALLOW.

    No fallback to direct HTTP or a second authorization path, even when an
    MCP call fails. The caller is responsible for authenticated principal
    identity and an authorized registered research provider.
    """
    if not isinstance(source, MCPResearchSource):
        raise TypeError("source must be the existing MCPResearchSource")
    if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= _MAX_QUERIES:
        raise ValueError("provide 1..3 explicit research queries")
    if type(max_findings) is not int or not 1 <= max_findings <= _MAX_RESULTS:
        raise ValueError("invalid total findings limit")
    if not isinstance(risk_level, RiskLevel):
        raise ValueError("risk level must be a registered Core RiskLevel")
    for field in (principal_id, resource_scope, task_id):
        if not isinstance(field, str) or not field or len(field) > 128:
            raise ValueError("invalid research principal, scope or task")
        if field != field.strip() or any(ord(c) < 32 or ord(c) == 127 for c in field):
            raise ValueError("invalid research principal, scope or task")
    prepared: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 256 or query != query.strip():
            raise ValueError("research query must be bounded and nonempty")
        if any(ord(c) < 32 or ord(c) == 127 for c in query):
            raise ValueError("research query contains controls")
        dedup_key = query.casefold()
        if dedup_key in seen_queries:
            raise ValueError("duplicate research query")
        seen_queries.add(dedup_key)
        prepared.append(query)

    findings: list[ResearchFinding] = []
    seen_urls: set[str] = set()
    # Serial requests avoid unbounded fan-out and keep original query order.
    for index, query in enumerate(prepared):
        response = await source.search(
            principal_id=principal_id, query=query,
            resource_scope=resource_scope, risk_level=risk_level,
            task_id=f"{task_id}:q{index}",
        )
        structured, provider_id = _structured_response(response)
        items = structured.get("results")
        if not isinstance(items, list) or len(items) > 100:
            raise ResearchMalformed("research result collection is invalid")
        for item in items:
            if not isinstance(item, dict):
                raise ResearchMalformed("research result item is invalid")
            url = _public_reference_url(item.get("url"))
            title = _text(item.get("title", ""), 160)
            snippet = _text(item.get("snippet", ""), 400)
            label = _text(item.get("source", "unverified"), 64)
            if not title or not label:
                raise ResearchMalformed("research result is incomplete")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            findings.append(ResearchFinding(
                query_index=index, title=title, url=url, snippet=snippet,
                source_label=label, provider_id=provider_id,
            ))
            if len(findings) >= max_findings:
                # Still authorize *remaining* query operations even if display
                # quota is met, so complete means every requested search ran.
                break
    return ResearchBatch(
        queries=tuple(prepared), findings=tuple(findings[:max_findings]),
        complete=True, gateway_routed=True,
    )
