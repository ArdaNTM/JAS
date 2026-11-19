from __future__ import annotations

import asyncio

import pytest

from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.mcp.screen_control_provider import ScreenControlMCPProvider


class FakeInputDriver:
    def __init__(self):
        self.calls = []

    async def click(self, x, y):
        self.calls.append(("click", x, y))

    async def type_text(self, text):
        self.calls.append(("type", text))

    async def press_key(self, key):
        self.calls.append(("key", key))


class FakeVision:
    def __init__(self):
        self.captures = 0
        self.prompts = []

    async def capture(self):
        self.captures += 1
        return b"image-bytes"

    async def describe(self, image, *, prompt):
        self.prompts.append(prompt)
        return "Untrusted screen description"


def dispatch_grant(*, approved=True, capability="ScreenControl", tool="screen_control", risk="high"):
    return DispatchGrant(
        principal_id="local-owner",
        capability_id=capability,
        tool_name=tool,
        approval_consumed=approved,
        risk_level=risk,
    )


def invoke(provider, args, grant=None):
    token = enter_dispatch(grant) if grant is not None else None
    try:
        return asyncio.run(provider.call_tool("screen_control", args))
    finally:
        if token is not None:
            leave_dispatch(token)


@pytest.mark.parametrize("grant", [
    None,
    dispatch_grant(approved=False),
    dispatch_grant(capability="OtherCapability"),
    dispatch_grant(tool="other_tool"),
    dispatch_grant(risk="low"),
])
def test_gui_actions_fail_closed_without_consumed_high_risk_approval(grant):
    driver = FakeInputDriver()
    provider = ScreenControlMCPProvider(input_driver=driver)
    with pytest.raises(PermissionError):
        invoke(provider, {"action": "click", "x": 10, "y": 20}, grant)
    assert driver.calls == []


def test_approved_click_type_and_key_reach_only_injected_driver():
    driver = FakeInputDriver()
    provider = ScreenControlMCPProvider(input_driver=driver)
    grant = dispatch_grant()
    assert invoke(provider, {"action": "click", "x": 100, "y": 200}, grant) == {
        "executed": True, "action": "click"
    }
    invoke(provider, {"action": "type", "text": "hello"}, grant)
    invoke(provider, {"action": "key", "key": "enter"}, grant)
    assert driver.calls == [
        ("click", 100, 200), ("type", "hello"), ("key", "enter")
    ]


@pytest.mark.parametrize("args", [
    {"action": "click", "x": -1, "y": 10},
    {"action": "click", "x": True, "y": 10},
    {"action": "type", "text": ""},
    {"action": "type", "text": "x" * 1001},
    {"action": "key", "key": ""},
    {"action": "launch", "target": "cmd.exe"},
])
def test_invalid_or_unbounded_actions_never_reach_driver(args):
    driver = FakeInputDriver()
    provider = ScreenControlMCPProvider(input_driver=driver)
    with pytest.raises((ValueError, KeyError)):
        invoke(provider, args, dispatch_grant())
    assert driver.calls == []


def test_observation_is_also_approval_gated_and_marked_untrusted():
    vision = FakeVision()
    provider = ScreenControlMCPProvider(vision=vision)
    with pytest.raises(PermissionError):
        invoke(provider, {"action": "observe"})
    result = invoke(provider, {"action": "observe"}, dispatch_grant())
    assert result == {"description": "Untrusted screen description", "untrusted": True}
    assert vision.captures == 1
    assert vision.prompts == ["Describe the current screen"]


def test_provider_tool_schema_is_closed_and_bounded():
    provider = ScreenControlMCPProvider(input_driver=FakeInputDriver())
    tool, = asyncio.run(provider.list_tools())
    assert tool.name == "screen_control"
    assert tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["action"]["enum"] == [
        "observe", "click", "type", "key"
    ]
    assert tool.input_schema["properties"]["text"]["maxLength"] == 1000
