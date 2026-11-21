"""AURA can explain real registered tools without claiming they are authorized."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.capabilities import ProviderType


class SpyTransport:
    payload = None

    def post_json(self, endpoint, payload, timeout):
        return {"message": {"content": "Merhaba"}, "done": True}

    def post_stream_json(self, endpoint, payload, timeout):
        self.payload = payload
        yield {"message": {"content": "Yeteneklerim bunlar."}, "done": False}
        yield {"done": True, "done_reason": "stop"}


def test_capability_question_injects_live_tools_but_no_permission_grant():
    transport = SpyTransport()
    app = create_api(config=RuntimeConfig(runtime="ollama", model="test"), transport=transport)
    cap = SimpleNamespace(
        definition=SimpleNamespace(
            provider_type=ProviderType.MCP,
            tool_name="read_test_data",
            capability_id="filesystem.read_test_data", provider_id="test.fs",
        ), available=True, healthy=True,
    )
    provider = SimpleNamespace(available=True, healthy=True)
    app.state.kernel = SimpleNamespace(
        capability_registry=SimpleNamespace(records=lambda: (cap,)),
        provider_registry=SimpleNamespace(get=lambda provider_id: provider),
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    response = TestClient(app).post(
        "/api/assistant/respond/stream",
        json={"message": "Neler yapabilirsin?"},
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    assert response.status_code == 200
    assert any(item.get("done") for item in map(json.loads, response.text.splitlines()))
    content = transport.payload["messages"][0]["content"]
    assert "filesystem.read_test_data" in content
    assert "117 bounded-v1 entries are documentation" in content
    assert "PermissionEngine and MCPGateway" in content
