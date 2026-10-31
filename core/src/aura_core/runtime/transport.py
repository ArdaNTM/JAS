from time import sleep
import json
from typing import Any, Protocol, runtime_checkable

import httpx

from aura_core.runtime.errors import BackendUnavailableError


@runtime_checkable
class JsonTransport(Protocol):
    def get_json(
        self,
        endpoint: str,
        timeout: float,
    ) -> dict[str, Any]:
        ...

    def post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        ...


class HttpJsonTransport:
    def get_json(
        self,
        endpoint: str,
        timeout: float,
    ) -> dict[str, Any]:
        try:
            response = httpx.get(
                endpoint,
                timeout=timeout,
            )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise BackendUnavailableError(
                "Inference backend is unavailable"
            ) from exc

        return response.json()

    def post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        # Inference calls do not execute tools, but a retry can still consume
        # GPU resources. Retry only when connection/transport setup fails;
        # never replay a request after a read timeout or HTTP status error,
        # because generation may still be running on the backend.
        for attempt in range(2):
            try:
                response = httpx.post(
                    endpoint,
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
                if attempt == 0:
                    sleep(0.3)
                    continue
                raise BackendUnavailableError(
                    "Inference backend is unavailable (transient connection failed twice)"
                ) from exc
            except httpx.ReadTimeout as exc:
                raise BackendUnavailableError(
                    "Inference backend is unavailable (model response timed out; "
                    "review AURA_BACKEND_TIMEOUT and Ollama model resources)"
                ) from exc
            except httpx.RequestError as exc:
                raise BackendUnavailableError(
                    "Inference backend is unavailable"
                ) from exc
        raise AssertionError("Inference transport retry loop exhausted")

    def post_stream_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: float,
    ):
        """Yield bounded NDJSON from Ollama without buffering the full answer.

        Streaming is not retried after the first byte; a replay may duplicate
        GPU inference. This method is transport-only, never tool dispatch.
        """
        total_bytes = 0
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0))) as client:
                with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.strip():
                            continue
                        size = len(line.encode("utf-8"))
                        total_bytes += size
                        if size > 65536 or total_bytes > 1048576:
                            raise ValueError("Inference stream exceeded response budget")
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError("Inference stream emitted a non-object event")
                        yield event
                        if event.get("done") is True:
                            return
                    raise ValueError("Inference stream closed without terminal completion")
        except httpx.RequestError as exc:
            raise BackendUnavailableError("Inference streaming backend is unavailable") from exc
