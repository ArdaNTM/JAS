from aura_core.config.backend import BackendConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.adapter import AdapterBackend
from aura_core.runtime.errors import BackendInvalidResponseError
from aura_core.runtime.mock_transport import MockJsonTransport


MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def build_request(
    max_tokens: int | None = 32,
) -> InferenceRequest:
    return InferenceRequest(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are AURA.",
            },
            {
                "role": "user",
                "content": "adapter regression test",
            },
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )


def build_backend(
    transport: MockJsonTransport,
) -> AdapterBackend:
    config = BackendConfig(
        endpoint="http://127.0.0.1:11434",
        timeout=45.0,
    )

    return AdapterBackend(
        config=config,
        transport=transport,
    )


def test_adapter_builds_ollama_payload(monkeypatch) -> None:
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": "payload test",
            },
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request(max_tokens=32)

    backend.infer(request)

    assert transport.last_endpoint == (
        "http://127.0.0.1:11434/api/chat"
    )

    assert transport.last_timeout == 45.0

    assert transport.last_payload == {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are AURA.",
            },
            {
                "role": "user",
                "content": "adapter regression test",
            },
        ],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.0,
            "num_predict": 32,
        },
    }


def test_adapter_omits_num_predict_when_max_tokens_is_none(monkeypatch) -> None:
    # The opt-in fast profile is not global. The ordinary adapter still
    # omits num_predict when no explicit generation limit is provided.
    monkeypatch.delenv("AURA_OLLAMA_FAST_RESPONSE", raising=False)
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": "no max tokens",
            },
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request(max_tokens=None)

    backend.infer(request)

    assert transport.last_payload is not None

    assert transport.last_payload["options"] == {
        "temperature": 0.0,
    }


def test_adapter_parses_completed_response() -> None:
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": "AURA ADAPTER RESPONSE PASS",
            },
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request()

    response = backend.infer(request)

    assert isinstance(response, InferenceResponse)
    assert response.model == MODEL
    assert response.content == "AURA ADAPTER RESPONSE PASS"
    assert response.finish_reason == "stop"


def test_adapter_parses_partial_response() -> None:
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": "partial",
            },
            "done": False,
        }
    )

    backend = build_backend(transport)
    request = build_request()

    response = backend.infer(request)

    assert response.content == "partial"
    assert response.finish_reason is None


def test_adapter_rejects_missing_message() -> None:
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request()

    try:
        backend.infer(request)
    except BackendInvalidResponseError as exc:
        assert str(exc) == (
            "Inference backend returned an invalid response"
        )
    else:
        raise AssertionError(
            "Missing message was unexpectedly accepted"
        )


def test_adapter_rejects_missing_content() -> None:
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
            },
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request()

    try:
        backend.infer(request)
    except BackendInvalidResponseError as exc:
        assert str(exc) == (
            "Inference backend returned an invalid response"
        )
    else:
        raise AssertionError(
            "Missing content was unexpectedly accepted"
        )


def test_adapter_rejects_non_string_content() -> None:
    transport = MockJsonTransport(
        {
            "model": MODEL,
            "message": {
                "role": "assistant",
                "content": 123,
            },
            "done": True,
        }
    )

    backend = build_backend(transport)
    request = build_request()

    try:
        backend.infer(request)
    except BackendInvalidResponseError as exc:
        assert str(exc) == (
            "Inference backend returned an invalid response"
        )
    else:
        raise AssertionError(
            "Non-string content was unexpectedly accepted"
        )

def test_adapter_fast_profile_uses_default_num_predict_when_max_tokens_missing(monkeypatch):
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    monkeypatch.setenv("AURA_OLLAMA_FAST_MAX_TOKENS", "1024")
    transport = MockJsonTransport({
        "model": MODEL,
        "message": {"role": "assistant", "content": "fast profile"},
        "done": True,
    })
    build_backend(transport).infer(build_request(max_tokens=None))
    assert transport.last_payload is not None
    assert transport.last_payload["think"] is False
    assert transport.last_payload["keep_alive"] == "10m"
    assert transport.last_payload["options"] == {
        "temperature": 0.0, "num_predict": 1024,
    }
