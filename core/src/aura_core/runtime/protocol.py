from typing import Protocol, runtime_checkable

from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)


@runtime_checkable
class InferenceRuntime(Protocol):
    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        ...