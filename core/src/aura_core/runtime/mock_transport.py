from typing import Any

from aura_core.runtime.transport import JsonTransport


class MockJsonTransport:
    def __init__(
        self,
        response: dict[str, Any],
    ) -> None:
        self._response = response
        self.last_endpoint: str | None = None
        self.last_payload: dict[str, Any] | None = None
        self.last_timeout: float | None = None

    def post_json(
        self,
        endpoint: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        self.last_endpoint = endpoint
        self.last_payload = payload
        self.last_timeout = timeout

        return self._response