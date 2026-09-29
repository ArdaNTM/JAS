from aura_core.config.backend import BackendConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.backend import InferenceBackend


class MockInferenceBackend:
    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        return InferenceResponse(
            model=request.model,
            content="AURA MOCK BACKEND PASS",
            finish_reason="stop",
        )


class MockInferenceRuntime:
    def __init__(
        self,
        backend: InferenceBackend | None = None,
        backend_config: BackendConfig | None = None,
    ) -> None:
        self._backend = backend or MockInferenceBackend()
        self._backend_config = backend_config

    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        return self._backend.infer(request)