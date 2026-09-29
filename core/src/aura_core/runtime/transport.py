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
        try:
            response = httpx.post(
                endpoint,
                json=payload,
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            raise BackendUnavailableError(
                "Inference backend is unavailable"
            ) from exc

        response.raise_for_status()

        return response.json()
