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
    def infer_stream(self, request: InferenceRequest):
        """Use the active inference runtime's incremental capability when supported."""
        stream = getattr(self._runtime, "infer_stream", None)
        if callable(stream):
            yield from stream(request)
        else:
            result = self._runtime.infer(request)
            yield {"delta": result.content}
            yield {"done": True, "finish_reason": result.finish_reason}
