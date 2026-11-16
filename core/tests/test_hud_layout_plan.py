"""Safe multi-monitor HUD geometry preview with negative origin and overlap checks."""
from dataclasses import FrozenInstanceError, replace

import pytest

from aura_core.application.monitor_topology import (
    DisplayGeometry, DisplayTopology, validate_display_topology,
)
from aura_core.application.hud_layout_plan import (
    HUDLayoutUnavailable, HUDPanelRequest, plan_hud_layout,
)


def _displays():
    return [
        DisplayGeometry("primary", 0, 0, 2560, 1440, 1.25, True),
        DisplayGeometry("left", -1920, 0, 1920, 1080, 1.0, False),
    ]


def _topology():
    return validate_display_topology(_displays())


def test_selects_explicit_negative_origin_monitor_and_primary_defaults():
    plan = plan_hud_layout(_topology(), [
        HUDPanelRequest("assistant", 240, 120, "top-right", "left"),
        HUDPanelRequest("status", 240, 120, "bottom-right"),
    ])
    assert plan.preview_only is True
    assert plan.topology_digest == _topology().digest
    left, primary = plan.placements
    assert (left.display_id, left.x, left.y, left.width, left.height) == (
        "left", -264, 24, 240, 120,
    )
    assert (primary.display_id, primary.width, primary.height) == ("primary", 300, 150)
    assert primary.x == 2560 - 24 - 300
    assert primary.y == 1440 - 24 - 150
    assert all(x.authority == "LAYOUT_PREVIEW_ONLY" for x in plan.placements)


def test_same_anchor_stacks_deterministically_without_overlap():
    displays = list(reversed(_displays()))
    topology = validate_display_topology(displays)
    a, b = plan_hud_layout(topology, [
        HUDPanelRequest("a", 150, 70, "top-left", "left"),
        HUDPanelRequest("b", 150, 70, "top-left", "left"),
    ]).placements
    assert b.y == a.y + a.height + 12
    assert a.x == b.x
    assert a.y == 24
    assert b.y + b.height < 1080


@pytest.mark.parametrize("panels", [
    [],
    [HUDPanelRequest("a", 120, 100)] * 2,
    [HUDPanelRequest("../private", 120, 100)],
    [HUDPanelRequest("a", 0, 100)],
    [HUDPanelRequest("a", 721, 100)],
    [HUDPanelRequest("a", 120, 481)],
    [HUDPanelRequest("a", True, 100)],
    [HUDPanelRequest("a", 120, True)],
    [HUDPanelRequest("a", 120, 100, "center")],
    [HUDPanelRequest("a", 120, 100, "top-right", "unregistered")],
    [HUDPanelRequest("x" * 65, 120, 100)],
    [HUDPanelRequest(str(n), 100, 100) for n in range(13)],
])
def test_malformed_panel_requests_fail_closed(panels):
    with pytest.raises(HUDLayoutUnavailable):
        plan_hud_layout(_topology(), panels)


def test_cross_anchor_overlap_is_rejected_instead_of_occluding_panels():
    topology = validate_display_topology([
        DisplayGeometry("small", 0, 0, 500, 350, 1.0, True),
    ])
    with pytest.raises(HUDLayoutUnavailable, match="overlap"):
        plan_hud_layout(topology, [
            HUDPanelRequest("a", 300, 100, "top-left"),
            HUDPanelRequest("b", 300, 100, "top-right"),
        ])


def test_oversized_scaled_panel_cannot_escape_monitor_bounds():
    topology = validate_display_topology([
        DisplayGeometry("tight", 0, 0, 360, 350, 3.0, True),
    ])
    with pytest.raises(HUDLayoutUnavailable, match="fit"):
        plan_hud_layout(topology, [HUDPanelRequest("big", 200, 150)])


def test_forged_topology_digest_or_bounding_box_is_denied():
    topology = _topology()
    with pytest.raises(HUDLayoutUnavailable, match="inconsistent"):
        plan_hud_layout(replace(topology, digest="fake"), [HUDPanelRequest("panel", 160, 100)])
    with pytest.raises(HUDLayoutUnavailable, match="inconsistent"):
        plan_hud_layout(replace(topology, bounds=(0, 0, 10, 10)), [HUDPanelRequest("panel", 160, 100)])


def test_geometry_exceeds_vertical_stack_is_rejected():
    topology = validate_display_topology([
        DisplayGeometry("small", 0, 0, 500, 360, 1.0, True),
    ])
    with pytest.raises(HUDLayoutUnavailable, match="exceeds"):
        plan_hud_layout(topology, [
            HUDPanelRequest("a", 180, 150, "top-left"),
            HUDPanelRequest("b", 180, 150, "top-left"),
            HUDPanelRequest("c", 180, 150, "top-left"),
        ])


def test_preview_is_immutable_and_has_no_screenshot_or_os_execution_fields():
    plan = plan_hud_layout(_topology(), [HUDPanelRequest("panel", 120, 80)])
    with pytest.raises(FrozenInstanceError):
        plan.preview_only = False
    assert not hasattr(plan, "execute")
    assert not hasattr(plan, "screenshot")
    assert not hasattr(plan.placements[0], "tool_name")


@pytest.mark.parametrize("kwargs", [
    {"margin_px": True}, {"margin_px": 7}, {"margin_px": 129},
    {"gap_px": -1}, {"gap_px": True}, {"gap_px": 65},
])
def test_invalid_spacing_rejected(kwargs):
    with pytest.raises(HUDLayoutUnavailable):
        plan_hud_layout(_topology(), [HUDPanelRequest("a", 120, 80)], **kwargs)


def test_directly_supplied_unvalidated_topology_rejected():
    with pytest.raises(TypeError):
        plan_hud_layout(object(), [HUDPanelRequest("a", 120, 80)])
