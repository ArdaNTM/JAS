"""Text-only InferenceService synthesis through the existing MCP Gateway."""
from __future__ import annotations

import asyncio

from aura_core.contracts.messages import InferenceRequest
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool

CAPABILITY = "assistant.synthesize"
TOOL = "synthesize"


class LocalSynthesisMCPProvider:
    """Local model synthesis, not a general tool or OS execution capability."""

    def __init__(self, *, inference_service, model: str):
        if inference_service is None or not model:
            raise ValueError("Real InferenceService and model are required")
        self.service = inference_service
        self.model = model

    async def list_tools(self):
        return (MCPTool(
            name=TOOL,
            description="Synthesize or summarize given text with the existing local InferenceService",
            input_schema={
                "type": "object",
                "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 4000}},
                "required": ["prompt"],
                "additionalProperties": False,
            },
        ),)

    async def call_tool(self, name: str, arguments: dict | None = None):
        grant = current_dispatch()
        if (grant is None or grant.capability_id != CAPABILITY
                or grant.tool_name != TOOL or grant.principal_id != "local_owner"):
            raise PermissionError("Synthesis requires authorized MCPGateway dispatch")
        if name != TOOL or not isinstance(arguments, dict) or set(arguments) != {"prompt"}:
            raise ValueError("Invalid synthesis arguments")
        prompt = arguments["prompt"]
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise ValueError("Synthesis prompt must be bounded nonempty text")
        inference = InferenceRequest(
            messages=[
                {"role": "system", "content": (
                    "You are AURA's local text synthesis service. Answer accurately "
                    "from the supplied user text. No tool execution or external actions."
                )},
                {"role": "user", "content": prompt.strip()},
            ],
            model=self.model,
            max_tokens=1024,
        )
        # Reuse actual composed local inference; never issue an unauthorized MCP
        # call, spawn subprocesses, interpret output as code, or bypass Gateway.
        result = await asyncio.to_thread(self.service.infer, inference)
        content = result.content
        if not isinstance(content, str) or not content.strip() or len(content) > 16000:
            raise ValueError("Local synthesis did not produce bounded text")
        return {"content": content, "model": result.model,
                "tool_execution_performed": False}
