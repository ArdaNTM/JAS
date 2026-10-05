from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ResearchToolSpec:
    search_capability_id: str
    search_operation_id: str
    search_tool_name: str
    fetch_capability_id: str
    fetch_operation_id: str
    fetch_tool_name: str

    def validate(self) -> None:
        values = (
            self.search_capability_id,
            self.search_operation_id,
            self.search_tool_name,
            self.fetch_capability_id,
            self.fetch_operation_id,
            self.fetch_tool_name,
        )

        if not all(
            isinstance(value, str) and value.strip()
            for value in values
        ):
            raise ValueError(
                "All research MCP identifiers are required"
            )
