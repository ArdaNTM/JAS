"""Fail-closed multi-monitor HUD placement *plans* over approved geometry metadata.

Never opens an overlay/window, reads pixels, injects input or dispatches tools.
The trusted desktop shell must independently authenticate its monitor metadata
and authorize actual HUD/window actions at their existing permission boundary.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from aura_core.application.monitor_topology import (
    DisplayTopology, DisplayGeometry, validate_display_topology,
)

_PANEL_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_ANCHORS = frozenset({"top-left", "top-right", "bottom-left", "bottom-right"})


class HUDLayoutUnavailable(ValueError):
    """The requested panel arrangement does not fit approved display geometry."""


@dataclass(frozen=True, slots=True)
class HUDPanelRequest:
    panel_id: str
    width: int
    height: int
    anchor: str = "top-right"
    display_id: str | None = None


@dataclass(frozen=True, slots=True)
class HUDPanelPlacement:
    panel_id: str
    display_id: str
    x: int
    y: int
    width: int
    height: int
    anchor: str
    authority: str = "LAYOUT_PREVIEW_ONLY"


@dataclass(frozen=True, slots=True)
class HUDLayoutPlan:
    placements: tuple[HUDPanelPlacement, ...]
    topology_digest: str
    preview_only: bool = True


def plan_hud_layout(
    topology: DisplayTopology,
    panels: list[HUDPanelRequest] | tuple[HUDPanelRequest, ...],
    *,
    margin_px: int = 24,
    gap_px: int = 12,
) -> HUDLayoutPlan:
    """Lay out 1..12 nonoverlapping panels; no OS execution or implicit grant."""
    if not isinstance(topology, DisplayTopology):
        raise TypeError("Validated Core DisplayTopology is required")
    # A caller could directly instantiate the dataclass with forged bounds or
    # digest. Revalidate it instead of treating a type annotation as proof.
    trusted = validate_display_topology(topology.displays)
    if trusted.bounds != topology.bounds or trusted.digest != topology.digest:
        raise HUDLayoutUnavailable("Display topology metadata is inconsistent")
    if not isinstance(panels, (list, tuple)) or not 1 <= len(panels) <= 12:
        raise HUDLayoutUnavailable("Expected 1..12 explicit HUD panels")
    if (type(margin_px) is not int or type(gap_px) is not int
            or not 8 <= margin_px <= 128 or not 0 <= gap_px <= 64):
        raise HUDLayoutUnavailable("Unsafe HUD spacing")

    displays = {d.display_id: d for d in trusted.displays}
    primary = next(d for d in trusted.displays if d.primary)
    seen_ids: set[str] = set()
    stacks: dict[tuple[str, str], int] = {}
    placements: list[HUDPanelPlacement] = []

    for panel in panels:
        if not isinstance(panel, HUDPanelRequest):
            raise HUDLayoutUnavailable("Invalid panel request")
        if not isinstance(panel.panel_id, str) or not _PANEL_ID.fullmatch(panel.panel_id):
            raise HUDLayoutUnavailable("Invalid panel identifier")
        if panel.panel_id in seen_ids:
            raise HUDLayoutUnavailable("Duplicate panel identifier")
        seen_ids.add(panel.panel_id)
        if (type(panel.width) is not int or type(panel.height) is not int
                or not 80 <= panel.width <= 720
                or not 50 <= panel.height <= 480):
            raise HUDLayoutUnavailable("Invalid bounded panel dimensions")
        if not isinstance(panel.anchor, str) or panel.anchor not in _ANCHORS:
            raise HUDLayoutUnavailable("Unsupported HUD anchor")
        if panel.display_id is not None and (
            not isinstance(panel.display_id, str) or panel.display_id not in displays
        ):
            raise HUDLayoutUnavailable("Unknown selected monitor")
        d = displays[panel.display_id] if panel.display_id is not None else primary
        # Each display supplies its trusted scale factor. Floor/ceil avoids
        # fractional pixels or crossing display edges on scaled monitors.
        width = math.ceil(panel.width * d.scale_factor)
        height = math.ceil(panel.height * d.scale_factor)
        if width + 2 * margin_px > d.width or height + 2 * margin_px > d.height:
            raise HUDLayoutUnavailable("HUD panel does not fit display")
        stack = (d.display_id, panel.anchor)
        used = stacks.get(stack, 0)
        x = d.x + margin_px if panel.anchor.endswith("left") else d.x + d.width - margin_px - width
        y = d.y + margin_px + used if panel.anchor.startswith("top") else d.y + d.height - margin_px - height - used
        if (x < d.x + margin_px or y < d.y + margin_px
                or x + width > d.x + d.width - margin_px
                or y + height > d.y + d.height - margin_px):
            raise HUDLayoutUnavailable("HUD stack exceeds selected monitor")
        proposal = HUDPanelPlacement(
            panel_id=panel.panel_id, display_id=d.display_id,
            x=x, y=y, width=width, height=height, anchor=panel.anchor,
        )
        for previous in placements:
            if previous.display_id != d.display_id:
                continue
            if (
                proposal.x < previous.x + previous.width
                and previous.x < proposal.x + proposal.width
                and proposal.y < previous.y + previous.height
                and previous.y < proposal.y + proposal.height
            ):
                raise HUDLayoutUnavailable("HUD placement would overlap another panel")
        placements.append(proposal)
        stacks[stack] = used + height + gap_px
    return HUDLayoutPlan(tuple(placements), topology_digest=trusted.digest)
