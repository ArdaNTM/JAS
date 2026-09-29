from pydantic import BaseModel, ConfigDict

from aura_core.config.backend import BackendConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig


class KernelConfig(BaseModel):
    """Validated runtime settings required to start the AURA Kernel."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeConfig
    backend: BackendConfig
    logging: LoggingConfig

    @classmethod
    def from_environment(cls) -> "KernelConfig":
        return cls(
            runtime=RuntimeConfig.from_environment(),
            backend=BackendConfig.from_environment(),
            logging=LoggingConfig.from_environment(),
        )
