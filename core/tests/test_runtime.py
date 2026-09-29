from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.contracts.messages import (
    InferenceRequest,
    InferenceResponse,
)
from aura_core.runtime.factory import create_runtime
from aura_core.runtime.mock import MockInferenceRuntime


class StubBackend:
    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        return InferenceResponse(
            model=request.model,
            content="STUB BACKEND PASS",
            finish_reason="stop",
        )


def test_mock_runtime_is_created() -> None:
    runtime = create_runtime("mock")

    assert isinstance(runtime, MockInferenceRuntime)


def test_ollama_runtime_uses_supplied_backend() -> None:
    backend = StubBackend()

    runtime = create_runtime(
        "ollama",
        backend=backend,
    )

    assert runtime is backend


def test_unknown_runtime_is_rejected() -> None:
    config = RuntimeConfig(
        runtime="invalid-runtime",
        model="qwen3:4b-instruct-2507-q4_K_M",
    )

    try:
        create_runtime(config.runtime)
    except ValueError as exc:
        assert str(exc) == "Unknown inference runtime: invalid-runtime"
    else:
        raise AssertionError(
            "Unknown runtime was unexpectedly accepted"
        )