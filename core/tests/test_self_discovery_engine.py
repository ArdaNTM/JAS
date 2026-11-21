"""Positive/negative public GitHub discovery and Gateway boundary regressions."""
import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

from aura_core.evolution.self_discovery import (
    LICENSES, SelfDiscoveryEngine, eligible_public_repo,
)
from aura_core.kernel.permissions import AuthorizationDecision


def repository(license_id="MIT"):
    return {"full_name": "example/offline-mcp",
            "html_url": "https://github.com/example/offline-mcp",
            "license": {"spdx_id": license_id}, "private": False,
            "fork": False, "archived": False,
            "description": "Offline MCP server for local assistants"}


README = "Local Ollama MCP server can run offline with no API key. " * 5


class FakeGateway:
    def __init__(self, approved=True):
        self.approved = approved
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        assert request.capability_id == "internet.fetch"
        assert request.operation_id == "internet.fetch"
        assert request.resource_scope == "public-web"
        assert request.principal_id == "local_owner"
        assert request.arguments["url"].startswith("https://api.github.com/")
        if not self.approved:
            return SimpleNamespace(decision=AuthorizationDecision.DENY, result=None)
        url = request.arguments["url"]
        if "/readme" in url:
            content = {"encoding": "base64",
                       "content": base64.b64encode(README.encode()).decode()}
        else:
            content = {"items": [repository(), repository("GPL-3.0")]}
        return SimpleNamespace(
            decision=AuthorizationDecision.ALLOW,
            result={"url": url, "status_code": 200, "content": json.dumps(content)}
        )


def test_license_and_no_paid_api_are_both_required():
    for license_id in LICENSES:
        assert eligible_public_repo(repository(license_id), README)
    for bad in ("GPL-3.0", "AGPL-3.0", "NOASSERTION", "Other"):
        assert not eligible_public_repo(repository(bad), README)
    assert not eligible_public_repo(repository(), "Requires OPENAI_API_KEY and paid subscription. Ollama offline." * 2)
    assert not eligible_public_repo(repository(), "Use commercial cloud only API." * 3)
    assert not eligible_public_repo(repository(), "This is a hosted product." * 5)
    assert not eligible_public_repo({**repository(), "private": True}, README)
    assert not eligible_public_repo({**repository(), "fork": True}, README)
    assert not eligible_public_repo({**repository(), "html_url": "https://evil.invalid"}, README)


def test_gateway_only_and_durable_deduplicated_queue(tmp_path):
    path = tmp_path / "state" / "discovery.sqlite3"
    fake = FakeGateway()
    engine = SelfDiscoveryEngine(gateway=fake, database_path=path)
    result = asyncio.run(engine.run_once())
    assert result["count"] == result["added"] == 1
    assert result["items"][0]["license_id"] == "MIT"
    assert result["items"][0]["status"] == "awaiting_owner_review"
    assert result["execution_performed"] is False
    assert len(fake.calls) == 2
    later = SelfDiscoveryEngine(gateway=fake, database_path=path)
    assert later.status()["count"] == 1
    assert asyncio.run(later.run_once())["note"] == "cooldown"
    assert len(fake.calls) == 2


def test_gateway_denial_never_adds_proposals(tmp_path):
    fake = FakeGateway(approved=False)
    engine = SelfDiscoveryEngine(gateway=fake, database_path=tmp_path / "blocked.db")
    result = asyncio.run(engine.run_once())
    assert result["count"] == 0
    assert result["note"] == "gateway_or_github_unavailable"
    assert len(fake.calls) == 1


def test_bad_database_path_is_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="absolute"):
        SelfDiscoveryEngine(gateway=FakeGateway(), database_path=Path("relative.db"))
    link = tmp_path / "link.sqlite3"
    try:
        link.symlink_to(tmp_path / "absent.db")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation requires elevated privileges on this host")
    with pytest.raises(ValueError, match="symlink"):
        SelfDiscoveryEngine(gateway=FakeGateway(), database_path=link)
