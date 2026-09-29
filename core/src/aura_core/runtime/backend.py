from typing import Protocol, runtime_checkable

from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)


@runtime_checkable
class InferenceBackend(Protocol):
    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        ...