from typing import Any

import logging

from fastapi.testclient import TestClient
from uuid import UUID

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.runtime.errors import BackendUnavailableError


MODEL = "qwen3:4b-instruct-2507-q4_K_M"


class StubTransport:
    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
        get_response: dict[str, Any] | None = None,
        get_error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.get_response = get_response
        self.get_error = get_error
        self.calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def get_json(
        self,
        endpoint: str,
        timeout: float,
    ) -> dict[str, Any]:
        self.get_calls.append(
            {
                "endpoint": endpoint,
                "timeout": timeout,
            }
        )

        if self.get_error is not None:
            raise self.get_error

        if self.get_response is None:
            raise AssertionError("StubTransport has no GET response")

        return self.get_response

    def post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "timeout": timeout,
            }
        )

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("StubTransport has no response")

        return self.response


def make_config() -> RuntimeConfig:
    return RuntimeConfig(
        runtime="ollama",
        model=MODEL,
        temperature=0.7,
        max_tokens=32,
    )


def make_backend_config() -> BackendConfig:
    return BackendConfig(
        endpoint="http://127.0.0.1:11434",
        timeout=30.0,
    )


def make_success_transport() -> StubTransport:
    return StubTransport(
        response={
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": "API CONTRACT PASS",
            },
            "done": True,
        }
    )


def make_client(
    transport: StubTransport,
) -> TestClient:
    app = create_api(
        make_config(),
        backend_config=make_backend_config(),
        transport=transport,
    )

    return TestClient(app)


def test_health_endpoint_reports_core_is_alive() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert transport.calls == []


def test_live_endpoint_reports_core_is_alive() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert transport.calls == []


def test_metrics_endpoint_reports_completed_requests() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    health_response = client.get("/health")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["requests_total"] == 1
    assert metrics["requests_success_total"] == 1
    assert metrics["requests_failure_total"] == 0
    assert metrics["latency_ms_total"] >= 0.0
    assert metrics["latency_ms_average"] >= 0.0


def test_metrics_endpoint_counts_failed_requests() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    invalid_response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [],
        },
    )
    metrics_response = client.get("/metrics")

    assert invalid_response.status_code == 422
    metrics = metrics_response.json()
    assert metrics["requests_total"] == 1
    assert metrics["requests_success_total"] == 0
    assert metrics["requests_failure_total"] == 1


def test_ready_endpoint_reports_ready_model() -> None:
    transport = StubTransport(
        get_response={
            "models": [
                {
                    "name": MODEL,
                }
            ]
        }
    )
    client = make_client(transport)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert transport.calls == []
    assert transport.get_calls == [
        {
            "endpoint": "http://127.0.0.1:11434/api/tags",
            "timeout": 30.0,
        }
    ]


def test_ready_endpoint_returns_503_when_model_is_missing() -> None:
    transport = StubTransport(get_response={"models": []})
    client = make_client(transport)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Configured model is unavailable",
    }


def test_ready_endpoint_returns_503_when_backend_is_unavailable() -> None:
    transport = StubTransport(
        get_error=BackendUnavailableError(
            "Inference backend is unavailable"
        )
    )
    client = make_client(transport)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Inference backend is unavailable",
    }


def test_ready_endpoint_returns_502_for_invalid_model_listing() -> None:
    transport = StubTransport(get_response={"models": "invalid"})
    client = make_client(transport)

    response = client.get("/ready")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Inference backend returned an invalid response",
    }


def test_api_logs_completed_request(caplog) -> None:
    transport = make_success_transport()
    client = make_client(transport)

    with caplog.at_level(logging.INFO, logger="aura_core.http"):
        response = client.get("/health")

    assert response.status_code == 200
    record = next(
        record
        for record in caplog.records
        if record.name == "aura_core.http"
    )
    assert record.event == "http_request_completed"
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert isinstance(record.latency_ms, float)
    assert record.latency_ms >= 0.0
    assert record.request_id == response.headers["X-Request-ID"]


def test_api_generates_request_id() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.get("/health")

    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])


def test_api_preserves_supplied_request_id() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.get(
        "/health",
        headers={"X-Request-ID": "aura-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "aura-request-123"


def test_inference_endpoint_returns_inference_response() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "contract test",
                }
            ],
            "temperature": 0.0,
            "max_tokens": 32,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "model": MODEL,
        "content": "API CONTRACT PASS",
        "finish_reason": "stop",
    }

    assert len(transport.calls) == 1

    call = transport.calls[0]

    assert call["endpoint"] == (
        "http://127.0.0.1:11434/api/chat"
    )

    assert call["payload"] == {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "contract test",
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 32,
        },
    }

    assert call["timeout"] == 30.0


def test_inference_endpoint_rejects_empty_messages() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [],
        },
    )

    assert response.status_code == 422
    assert transport.calls == []


def test_inference_endpoint_rejects_empty_model() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": "",
            "messages": [
                {
                    "role": "user",
                    "content": "contract test",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert transport.calls == []


def test_inference_endpoint_rejects_invalid_temperature() -> None:
    transport = make_success_transport()
    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "contract test",
                }
            ],
            "temperature": 3.0,
        },
    )

    assert response.status_code == 422
    assert transport.calls == []


def test_backend_unavailable_maps_to_503() -> None:
    transport = StubTransport(
        error=BackendUnavailableError(
            "Inference backend is unavailable"
        )
    )

    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "backend failure test",
                }
            ],
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Inference backend is unavailable",
    }

    assert len(transport.calls) == 1


def test_backend_invalid_response_maps_to_502() -> None:
    transport = StubTransport(
        response={
            "model": MODEL,
            "message": {
                "role": "assistant",
            },
            "done": True,
        }
    )

    client = make_client(transport)

    response = client.post(
        "/v1/inference",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "invalid response test",
                }
            ],
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Inference backend returned an invalid response",
    }

    assert len(transport.calls) == 1
