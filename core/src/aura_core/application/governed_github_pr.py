"""Read-only JAS pull request status through the authoritative MCP Gateway.

No direct GitHub HTTP/SDK/token access, writes, branch changes, PR creation or
merge operations are possible here. The owner principal must be authenticated
by trusted composition *before* constructing this facade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest, MCPGatewayResponse

_REPO = "ArdaNTM/JAS"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PROVIDER_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_BASE = re.compile(r"[A-Za-z0-9._/-]{1,128}\Z")


class GitHubReadDenied(PermissionError):
    """The existing PermissionEngine/Gateway did not authorize the read."""


class GitHubReadMalformed(ValueError):
    """The MCP provider supplied invalid or unsafe pull request metadata."""


@dataclass(frozen=True, slots=True)
class PullRequestStatus:
    repository_full_name: str
    number: int
    state: str
    merged: bool
    draft: bool
    title: str
    head_sha: str
    base_ref: str
    provider_id: str
    trust: str = "UNTRUSTED_PROVIDER_METADATA"
    read_only: bool = True


def _identity(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("Invalid authenticated GitHub principal")
    return value


def _result(response: object, requested_number: int) -> PullRequestStatus:
    if not isinstance(response, MCPGatewayResponse):
        raise GitHubReadMalformed("Invalid MCP Gateway response")
    if response.decision is not AuthorizationDecision.ALLOW:
        raise GitHubReadDenied("Explicit read permission required")
    result = response.result
    if (result is None or getattr(result, "is_error", False) is True
            or getattr(result, "isError", False) is True):
        raise GitHubReadMalformed("MCP tool failed or returned no structured metadata")
    if isinstance(result, dict):
        if result.get("isError") is True or result.get("status") == "failed":
            raise GitHubReadMalformed("MCP tool failed")
        payload = result.get("structuredContent", result.get("structured_content", result))
    else:
        payload = getattr(result, "structured_content", None)
        if payload is None:
            payload = getattr(result, "structuredContent", None)
    if not isinstance(payload, dict):
        raise GitHubReadMalformed("MCP PR metadata is not structured")
    if payload.get("repository_full_name") != _REPO or type(payload.get("number")) is not int or payload["number"] != requested_number:
        raise GitHubReadMalformed("MCP PR metadata did not match the requested JAS PR")
    if payload.get("state") not in ("open", "closed"):
        raise GitHubReadMalformed("Invalid PR state")
    if type(payload.get("merged")) is not bool or type(payload.get("draft")) is not bool:
        raise GitHubReadMalformed("Invalid PR decision flags")
    if payload["merged"] and payload["state"] != "closed":
        raise GitHubReadMalformed("Inconsistent merge state")
    title = payload.get("title")
    if (
        not isinstance(title, str) or not 1 <= len(title) <= 200
        or not title.strip()
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in title)
    ):
        raise GitHubReadMalformed("Invalid or unbounded PR title")
    head_sha = payload.get("head_sha")
    if not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha):
        raise GitHubReadMalformed("Invalid commit ID")
    base_ref = payload.get("base_ref")
    if (not isinstance(base_ref, str) or not _BASE.fullmatch(base_ref)
            or base_ref.startswith((".", "-", "/")) or ".." in base_ref):
        raise GitHubReadMalformed("Invalid PR base")
    provider_id = response.provider_id
    if not isinstance(provider_id, str) or not _PROVIDER_ID.fullmatch(provider_id):
        raise GitHubReadMalformed("MCP provider identity missing")
    return PullRequestStatus(
        repository_full_name=_REPO, number=requested_number,
        state=payload["state"], merged=payload["merged"], draft=payload["draft"],
        title=title, head_sha=head_sha, base_ref=base_ref, provider_id=provider_id,
    )


class GovernedJASPullRequestReader:
    """Trusted Core-bound, exact-repo read only; never a GitHub account client."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCPGateway is required")
        self._gateway = gateway
        self._principal_id = _identity(authenticated_principal_id)

    async def read(self, pr_number: int) -> PullRequestStatus:
        if type(pr_number) is not int or not 1 <= pr_number <= 1_000_000:
            raise ValueError("PR number must be a bounded positive integer")
        request = MCPGatewayRequest(
            request_id="github-read-pr:" + str(uuid4()),
            principal_id=self._principal_id,
            capability_id="github.pull_request.read",
            operation_id="github.pull_request.read",
            resource_scope=f"github/ArdaNTM/JAS/pulls/{pr_number}",
            risk_level=RiskLevel.LOW,
            tool_name="get_pull_request",
            arguments={"repository_full_name": _REPO, "pr_number": pr_number},
            task_id=f"github:pr:{pr_number}",
        )
        try:
            response = await self._gateway.invoke(request)
        except Exception as exc:
            raise GitHubReadMalformed("GitHub Gateway read failed") from exc
        return _result(response, pr_number)
