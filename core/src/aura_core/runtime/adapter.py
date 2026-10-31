from typing import Any
import os

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

        # Opt-in interactive profile: reduce excessive Qwen3 thinking and
        # bound generation. The user's explicit max_tokens always wins.
        if os.getenv("AURA_OLLAMA_FAST_RESPONSE", "0").strip().lower() in {"1", "true", "yes"}:
            if request.max_tokens is None:
                # Bounded independently from untrusted model/user input.
                options["num_predict"] = max(
                    128, min(2048, int(os.getenv("AURA_OLLAMA_FAST_MAX_TOKENS", "1024")))
                )
            payload["think"] = False
            payload["keep_alive"] = "10m"

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
        if isinstance(content, str):
            import re
            content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip(), flags=re.IGNORECASE)
            content = re.sub(r"\n?```\s*$", "", content.strip())

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

    def infer_stream(self, request: InferenceRequest):
        """Optional incremental model response; no capability/tool execution."""
        stream_method = getattr(self._transport, "post_stream_json", None)
        if not callable(stream_method):
            # Preserve provider-agnostic compatibility for injected test runtimes.
            completed = self.infer(request)
            yield {"delta": completed.content}
            yield {"done": True, "finish_reason": completed.finish_reason}
            return

        payload = self._build_payload(request)
        payload["stream"] = True
        finished = False
        for event in stream_method(
            endpoint=f"{self._config.endpoint}/api/chat",
            payload=payload,
            timeout=self._config.timeout,
        ):
            if event.get("error"):
                raise BackendInvalidResponseError("Inference stream returned an error")
            message = event.get("message")
            if isinstance(message, dict):
                fragment = message.get("content", "")
                if not isinstance(fragment, str):
                    raise BackendInvalidResponseError("Inference stream contains invalid content")
                if fragment:
                    yield {"delta": fragment}
            if event.get("done") is True:
                finished = True
                yield {
                    "done": True,
                    "finish_reason": event.get("done_reason", "stop"),
                }
                break
        if not finished:
            raise BackendInvalidResponseError("Inference stream ended before completion")
