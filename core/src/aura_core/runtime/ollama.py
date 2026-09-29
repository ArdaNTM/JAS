from aura_core.config.backend import BackendConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.adapter import AdapterBackend
from aura_core.runtime.transport import (
    HttpJsonTransport,
    JsonTransport,
)


class OllamaInferenceRuntime:
    def __init__(
        self,
        backend_config: BackendConfig,
        transport: JsonTransport | None = None,
    ) -> None:
        self._transport = transport or HttpJsonTransport()

        self._backend = AdapterBackend(
            config=backend_config,
            transport=self._transport,
        )

    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        return self._backend.infer(request)