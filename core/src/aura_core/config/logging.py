import os
from typing import Literal

from pydantic import BaseModel, ConfigDict


LogLevel = Literal[
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
]


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: LogLevel = "INFO"

    @classmethod
    def from_environment(cls) -> "LoggingConfig":
        return cls(
            level=os.getenv("AURA_LOG_LEVEL", "INFO").upper(),
        )
