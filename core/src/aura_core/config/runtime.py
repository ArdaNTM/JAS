import os

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime: str = Field(default="mock", min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        runtime = os.getenv("AURA_RUNTIME", "mock")

        model = os.getenv("AURA_MODEL")
        if not model:
            raise RuntimeError("AURA_MODEL environment variable is required")

        temperature = float(os.getenv("AURA_TEMPERATURE", "0.7"))

        max_tokens_raw = os.getenv("AURA_MAX_TOKENS")
        max_tokens = int(max_tokens_raw) if max_tokens_raw else None

        return cls(
            runtime=runtime,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )