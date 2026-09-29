from unittest.mock import patch

import httpx
import pytest

from aura_core.runtime.errors import BackendUnavailableError
from aura_core.runtime.transport import HttpJsonTransport


ENDPOINT = "http://127.0.0.1:11434/api/chat"

PAYLOAD = {
    "model": "qwen3:4b-instruct-2507-q4_K_M",
    "messages": [
        {
            "role": "user",
            "content": "transport regression test",
        }
    ],
    "stream": False,
}


def test_transport_posts_json_and_returns_response() -> None:
    transport = HttpJsonTransport()

    expected = {
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "message": {
            "role": "assistant",
            "content": "transport pass",
        },
        "done": True,
    }

    response = httpx.Response(
        status_code=200,
        json=expected,
        request=httpx.Request(
            "POST",
            ENDPOINT,
        ),
    )

    with patch(
        "aura_core.runtime.transport.httpx.post",
        return_value=response,
    ) as post:
        result = transport.post_json(
            endpoint=ENDPOINT,
            payload=PAYLOAD,
            timeout=30.0,
        )

    post.assert_called_once_with(
        ENDPOINT,
        json=PAYLOAD,
        timeout=30.0,
    )

    assert result == expected


def test_transport_gets_json_and_returns_response() -> None:
    transport = HttpJsonTransport()

    expected = {
        "models": [
            {
                "name": "qwen3:4b-instruct-2507-q4_K_M",
            }
        ]
    }

    response = httpx.Response(
        status_code=200,
        json=expected,
        request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"),
    )

    with patch(
        "aura_core.runtime.transport.httpx.get",
        return_value=response,
    ) as get:
        result = transport.get_json(
            endpoint="http://127.0.0.1:11434/api/tags",
            timeout=30.0,
        )

    get.assert_called_once_with(
        "http://127.0.0.1:11434/api/tags",
        timeout=30.0,
    )
    assert result == expected


def test_transport_maps_request_error() -> None:
    transport = HttpJsonTransport()

    original_error = httpx.ConnectError(
        "Connection refused"
    )

    with patch(
        "aura_core.runtime.transport.httpx.post",
        side_effect=original_error,
    ):
        with pytest.raises(
            BackendUnavailableError,
            match="Inference backend is unavailable",
        ) as exc_info:
            transport.post_json(
                endpoint=ENDPOINT,
                payload=PAYLOAD,
                timeout=30.0,
            )

    assert exc_info.value.__cause__ is original_error


@pytest.mark.parametrize(
    "status_code",
    [400, 404, 500, 502, 503],
)
def test_transport_propagates_http_status_error(
    status_code: int,
) -> None:
    transport = HttpJsonTransport()

    request = httpx.Request(
        "POST",
        ENDPOINT,
    )

    response = httpx.Response(
        status_code=status_code,
        request=request,
    )

    with patch(
        "aura_core.runtime.transport.httpx.post",
        return_value=response,
    ):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            transport.post_json(
                endpoint=ENDPOINT,
                payload=PAYLOAD,
                timeout=30.0,
            )

    exc = exc_info.value

    assert exc.response is response
    assert exc.response.status_code == status_code
    assert exc.request.url == httpx.URL(ENDPOINT)


def test_transport_does_not_parse_json_after_http_error() -> None:
    transport = HttpJsonTransport()

    request = httpx.Request(
        "POST",
        ENDPOINT,
    )

    response = httpx.Response(
        status_code=500,
        content=b'{"error":"backend failure"}',
        request=request,
    )

    with patch(
        "aura_core.runtime.transport.httpx.post",
        return_value=response,
    ):
        with pytest.raises(httpx.HTTPStatusError):
            transport.post_json(
                endpoint=ENDPOINT,
                payload=PAYLOAD,
                timeout=30.0,
            )
