from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchMCPConfig:
    provider_id: str
    service_name: str
    service_version: str

    capability_id: str
    search_operation_id: str
    search_tool_name: str

    fetch_capability_id: str
    fetch_operation_id: str
    fetch_tool_name: str

    transport: str
    endpoint: str | None
    command: str | None
    args: tuple[str, ...]

    @classmethod
    def from_env(
        cls,
    ) -> "ResearchMCPConfig":
        transport = os.getenv(
            "AURA_RESEARCH_MCP_TRANSPORT",
            "",
        ).strip().lower()

        if transport not in {
            "http",
            "stdio",
        }:
            raise RuntimeError(
                "AURA_RESEARCH_MCP_TRANSPORT must be "
                "'http' or 'stdio'"
            )

        endpoint = os.getenv(
            "AURA_RESEARCH_MCP_ENDPOINT",
            "",
        ).strip() or None

        command = os.getenv(
            "AURA_RESEARCH_MCP_COMMAND",
            "",
        ).strip() or None

        raw_args = os.getenv(
            "AURA_RESEARCH_MCP_ARGS",
            "",
        ).strip()

        args = (
            tuple(
                item
                for item in raw_args.split("|")
                if item
            )
            if raw_args
            else ()
        )

        if transport == "http" and not endpoint:
            raise RuntimeError(
                "AURA_RESEARCH_MCP_ENDPOINT is required "
                "for HTTP MCP research provider"
            )

        if transport == "stdio" and not command:
            raise RuntimeError(
                "AURA_RESEARCH_MCP_COMMAND is required "
                "for stdio MCP research provider"
            )

        required = {
            "AURA_RESEARCH_MCP_PROVIDER_ID":
                os.getenv(
                    "AURA_RESEARCH_MCP_PROVIDER_ID",
                    "",
                ),
            "AURA_RESEARCH_MCP_CAPABILITY_ID":
                os.getenv(
                    "AURA_RESEARCH_MCP_CAPABILITY_ID",
                    "",
                ),
            "AURA_RESEARCH_MCP_SEARCH_OPERATION_ID":
                os.getenv(
                    "AURA_RESEARCH_MCP_SEARCH_OPERATION_ID",
                    "",
                ),
            "AURA_RESEARCH_MCP_SEARCH_TOOL":
                os.getenv(
                    "AURA_RESEARCH_MCP_SEARCH_TOOL",
                    "",
                ),
            "AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID":
                os.getenv(
                    "AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID",
                    "",
                ),
            "AURA_RESEARCH_MCP_FETCH_OPERATION_ID":
                os.getenv(
                    "AURA_RESEARCH_MCP_FETCH_OPERATION_ID",
                    "",
                ),
            "AURA_RESEARCH_MCP_FETCH_TOOL":
                os.getenv(
                    "AURA_RESEARCH_MCP_FETCH_TOOL",
                    "",
                ),
        }

        missing = [
            key
            for key, value in required.items()
            if not value.strip()
        ]

        if missing:
            raise RuntimeError(
                "Research MCP configuration missing: "
                + ", ".join(missing)
            )

        return cls(
            provider_id=required[
                "AURA_RESEARCH_MCP_PROVIDER_ID"
            ],
            service_name=os.getenv(
                "AURA_RESEARCH_MCP_SERVICE_NAME",
                "research-mcp",
            ),
            service_version=os.getenv(
                "AURA_RESEARCH_MCP_SERVICE_VERSION",
                "1.0.0",
            ),
            capability_id=required[
                "AURA_RESEARCH_MCP_CAPABILITY_ID"
            ],
            search_operation_id=required[
                "AURA_RESEARCH_MCP_SEARCH_OPERATION_ID"
            ],
            search_tool_name=required[
                "AURA_RESEARCH_MCP_SEARCH_TOOL"
            ],
            fetch_capability_id=required[
                "AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID"
            ],
            fetch_operation_id=required[
                "AURA_RESEARCH_MCP_FETCH_OPERATION_ID"
            ],
            fetch_tool_name=required[
                "AURA_RESEARCH_MCP_FETCH_TOOL"
            ],
            transport=transport,
            endpoint=endpoint,
            command=command,
            args=args,
        )
