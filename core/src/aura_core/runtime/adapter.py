from typing import Any

from aura_core.config.backend import BackendConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.backend import InferenceBackend
from aura_core.runtime.errors import BackendInvalidResponseError
from aura_core.runtime.transport import JsonTransport


class AdapterBackend(InferenceBackend):
    def __init__(
        self,
        config: BackendConfig,
        transport: JsonTransport,
    ) -> None:
        self._config = config
        self._transport = transport

    def _build_payload(
        self,
        request: InferenceRequest,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                message.model_dump()
                for message in request.messages
            ],
            "stream": False,
        }

        options: dict[str, Any] = {
            "temperature": request.temperature,
        }

        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        payload["options"] = options

        return payload

    def _parse_response(
        self,
        request: InferenceRequest,
        response: dict[str, Any],
    ) -> InferenceResponse:
        message = response.get("message")

        if not isinstance(message, dict):
            raise BackendInvalidResponseError(
                "Inference backend returned an invalid response"
            )

        if "content" not in message:
            raise BackendInvalidResponseError(
                "Inference backend returned an invalid response"
            )

        content = message["content"]

        if not isinstance(content, str):
            raise BackendInvalidResponseError(
                "Inference backend returned an invalid response"
            )

        finish_reason = (
            "stop"
            if response.get("done") is True
            else None
        )

        return InferenceResponse(
            model=request.model,
            content=content,
            finish_reason=finish_reason,
        )

    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        payload = self._build_payload(request)

        response = self._transport.post_json(
            endpoint=f"{self._config.endpoint}/api/chat",
            payload=payload,
            timeout=self._config.timeout,
        )

        return self._parse_response(
            request,
            response,
        )