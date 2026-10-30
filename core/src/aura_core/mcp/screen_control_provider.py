"""Approval-only ScreenControl MCP provider with injected desktop drivers."""
from __future__ import annotations

from typing import Any
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool


class ScreenControlMCPProvider:
    provider_id = "aura.screen-control"
    requires_approval = True

    def __init__(self, *, vision: Any = None, input_driver: Any = None):
        # No implicit desktop driver: deployment must explicitly inject and
        # configure an environment-specific adapter.
        self.vision = vision
        self.input_driver = input_driver

    async def list_tools(self):
        return (MCPTool("screen_control", "Observe pixels or execute one approved GUI action",
            {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["observe", "click", "type", "key"]},
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "text": {"type": "string", "maxLength": 1000},
                "key": {"type": "string", "maxLength": 50}},
             "required": ["action"], "additionalProperties": False}),)

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        if (grant is None or name != "screen_control" or
                grant.tool_name != name or grant.capability_id != "ScreenControl" or
                not grant.approval_consumed or grant.risk_level not in {"high", "critical"}):
            raise PermissionError("ScreenControl requires consumed interactive Gateway approval")
        args = arguments or {}
        action = args["action"]
        if action == "observe":
            if self.vision is None:
                raise RuntimeError("Screen vision adapter not configured")
            image = await self.vision.capture()
            return {"description": await self.vision.describe(image, prompt="Describe the current screen"),
                    "untrusted": True}
        if self.input_driver is None:
            raise RuntimeError("Screen input driver not configured")
        if action == "click":
            x, y = args.get("x"), args.get("y")
            if type(x) is not int or type(y) is not int or not (0 <= x <= 10000 and 0 <= y <= 10000):
                raise ValueError("Invalid screen coordinates")
            await self.input_driver.click(x, y)
        elif action == "type":
            if not isinstance(args.get("text"), str) or not args["text"]:
                raise ValueError("Text required")
            await self.input_driver.type_text(args["text"])
        elif action == "key":
            if not isinstance(args.get("key"), str) or not args["key"]:
                raise ValueError("Key required")
            await self.input_driver.press_key(args["key"])
        else:
            raise ValueError("Unsupported screen action")
        return {"executed": True, "action": action}
