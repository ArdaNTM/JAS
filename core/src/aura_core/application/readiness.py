from typing import Any

from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.runtime.errors import (
    BackendInvalidResponseError,
    BackendUnavailableError,
)
from aura_core.runtime.transport import JsonTransport


class ReadinessService:
    def __init__(
        self,
        config: RuntimeConfig,
        backend_config: BackendConfig,
        transport: JsonTransport,
    ) -> None:
        self._config = config
        self._backend_config = backend_config
        self._transport = transport

    def check(self) -> None:
        if self._config.runtime == "mock":
            return

        response = self._transport.get_json(
            endpoint=f"{self._backend_config.endpoint}/api/tags",
            timeout=self._backend_config.timeout,
        )
        models = response.get("models")

        if not isinstance(models, list):
            raise BackendInvalidResponseError(
                "Inference backend returned an invalid response"
            )

        model_names = {
            model["name"]
            for model in models
            if isinstance(model, dict)
            and isinstance(model.get("name"), str)
        }

        if self._config.model not in model_names:
            raise BackendUnavailableError(
                "Configured model is unavailable"
            )
