from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.protocol import InferenceRuntime


class InferenceService:
    def __init__(self, runtime: InferenceRuntime) -> None:
        self._runtime = runtime

    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        return self._runtime.infer(request)