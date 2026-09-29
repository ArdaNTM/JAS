import os

from pydantic import BaseModel, ConfigDict, Field


class BackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(default="http://127.0.0.1:11434", min_length=1)
    timeout: float = Field(default=120.0, gt=0.0)

    @classmethod
    def from_environment(cls) -> "BackendConfig":
        endpoint = os.getenv(
            "AURA_BACKEND_ENDPOINT",
            "http://127.0.0.1:11434",
        )

        timeout = float(
            os.getenv(
                "AURA_BACKEND_TIMEOUT",
                "120.0",
            )
        )

        return cls(
            endpoint=endpoint,
            timeout=timeout,
        )