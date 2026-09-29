from aura_core.config.backend import BackendConfig
from aura_core.runtime.backend import InferenceBackend
from aura_core.runtime.protocol import InferenceRuntime
from aura_core.runtime.transport import JsonTransport


def create_runtime(
    name: str,
    backend: InferenceBackend | None = None,
    backend_config: BackendConfig | None = None,
    transport: JsonTransport | None = None,
) -> InferenceRuntime:
    if name == "mock":
        from aura_core.runtime.mock import MockInferenceRuntime

        return MockInferenceRuntime(
            backend=backend,
            backend_config=backend_config,
        )

    if name == "ollama":
        if backend is not None:
            return backend

        if backend_config is None:
            backend_config = BackendConfig.from_environment()

        from aura_core.runtime.ollama import OllamaInferenceRuntime

        return OllamaInferenceRuntime(
            backend_config=backend_config,
            transport=transport,
        )

    raise ValueError(f"Unknown inference runtime: {name}")