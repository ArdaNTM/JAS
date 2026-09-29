from aura_core.application.service import InferenceService
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.runtime.factory import create_runtime
from aura_core.runtime.transport import JsonTransport


def create_application(
    config: RuntimeConfig,
    backend_config: BackendConfig | None = None,
    transport: JsonTransport | None = None,
) -> InferenceService:
    runtime = create_runtime(
        config.runtime,
        backend_config=backend_config,
        transport=transport,
    )

    return InferenceService(runtime)