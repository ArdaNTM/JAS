"""Read-only bounded monitor geometry projection for a trusted desktop adapter.

This does not enumerate displays, capture pixels, position overlays, execute OS
commands, or provide an Owner identity. The trusted Electron/native shell must
first supply ephemeral display IDs and validated metadata with local consent.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass

from aura_core.kernel.events import EventBus, KernelEvent

_DISPLAY_ID = re.compile(r"[A-Za-z0-9_.:-]{1,48}\Z")
_MAX_DISPLAYS = 8
_MAX_COORD = 100_000
_MAX_DIM = 16_384


@dataclass(frozen=True, slots=True)
class DisplayGeometry:
    display_id: str
    x: int
    y: int
    width: int
    height: int
    scale_factor: float
    primary: bool


@dataclass(frozen=True, slots=True)
class DisplayTopology:
    displays: tuple[DisplayGeometry, ...]
    bounds: tuple[int, int, int, int]
    digest: str
    source_trust: str = "TRUSTED_SHELL_METADATA_ONLY"


def validate_display_topology(
    displays: tuple[DisplayGeometry, ...] | list[DisplayGeometry],
) -> DisplayTopology:
    """Canonical read-only topology; reject poisoned geometry before HUD use."""
    if not isinstance(displays, (tuple, list)) or not 1 <= len(displays) <= _MAX_DISPLAYS:
        raise ValueError("Expected 1..8 monitor geometry entries")
    seen: set[str] = set()
    normalized: list[DisplayGeometry] = []
    primary_count = 0
    for d in displays:
        if not isinstance(d, DisplayGeometry) or not isinstance(d.display_id, str) or not _DISPLAY_ID.fullmatch(d.display_id):
            raise ValueError("Invalid ephemeral monitor display ID")
        if d.display_id in seen:
            raise ValueError("Duplicate monitor display ID")
        seen.add(d.display_id)
        if any(type(v) is not int for v in (d.x, d.y, d.width, d.height)):
            raise ValueError("Monitor coordinates must be finite integer pixels")
        if (
            not -_MAX_COORD <= d.x <= _MAX_COORD
            or not -_MAX_COORD <= d.y <= _MAX_COORD
            or not 1 <= d.width <= _MAX_DIM
            or not 1 <= d.height <= _MAX_DIM
        ):
            raise ValueError("Monitor geometry exceeds safe bounds")
        if (
            d.x + d.width > _MAX_COORD + _MAX_DIM
            or d.y + d.height > _MAX_COORD + _MAX_DIM
        ):
            raise ValueError("Monitor extent exceeds safe bounds")
        if type(d.scale_factor) not in (int, float):
            raise ValueError("Monitor scale must be a finite number")
        try:
            scale = float(d.scale_factor)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Invalid monitor scale") from exc
        if not math.isfinite(scale) or not 0.5 <= scale <= 4.0:
            raise ValueError("Monitor scale is out of bounds")
        if type(d.primary) is not bool:
            raise ValueError("Monitor primary flag must be boolean")
        primary_count += int(d.primary)
        normalized.append(DisplayGeometry(
            display_id=d.display_id, x=d.x, y=d.y,
            width=d.width, height=d.height,
            scale_factor=scale, primary=d.primary,
        ))
    if primary_count != 1:
        raise ValueError("Exactly one primary monitor is required")
    normalized.sort(key=lambda item: item.display_id)
    bounds = (
        min(d.x for d in normalized), min(d.y for d in normalized),
        max(d.x + d.width for d in normalized),
        max(d.y + d.height for d in normalized),
    )
    # Digest detects metadata changes; it is not a device identity or
    # cryptographically authenticated display/EDID certificate.
    payload = [
        [d.display_id, d.x, d.y, d.width, d.height, d.scale_factor, d.primary]
        for d in normalized
    ]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return DisplayTopology(tuple(normalized), bounds, digest)


class MonitorTopologyObserver:
    """One-session, opt-in EventBus-only view of trusted shell metadata."""

    def __init__(self, events: EventBus) -> None:
        if not isinstance(events, EventBus):
            raise TypeError("Existing Core EventBus required")
        self._events = events
        self._lock = threading.RLock()
        self._session_id: str | None = None
        self._generation = 0
        self._last_digest: str | None = None

    def start(self, *, session_id: str, confirmed_local_shell: bool) -> None:
        if (not isinstance(session_id, str) or not 1 <= len(session_id) <= 128
                or session_id != session_id.strip()
                or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in session_id)):
            raise ValueError("Invalid authenticated shell session")
        if confirmed_local_shell is not True:
            raise PermissionError("Explicit local desktop session required")
        with self._lock:
            if self._session_id is not None and self._session_id != session_id:
                raise PermissionError("Another shell session owns monitor topology")
            self._session_id = session_id
            self._generation += 1
            self._last_digest = None

    def stop(self, *, session_id: str) -> None:
        with self._lock:
            if session_id != self._session_id or self._session_id is None:
                raise PermissionError("Wrong monitor topology session")
            self._session_id = None
            self._generation += 1
            self._last_digest = None

    def observe(
        self,
        displays: tuple[DisplayGeometry, ...] | list[DisplayGeometry],
        *,
        session_id: str,
    ) -> DisplayTopology:
        with self._lock:
            if session_id != self._session_id or self._session_id is None:
                raise PermissionError("Monitor observation is not authorized")
            generation = self._generation
        topology = validate_display_topology(displays)
        with self._lock:
            if session_id != self._session_id or generation != self._generation:
                raise PermissionError("Monitor session was revoked")
            if topology.digest != self._last_digest:
                self._last_digest = topology.digest
                # Do not broadcast EDID/serials, screenshots or raw display IDs.
                self._events.publish(KernelEvent(
                    event_type="DisplayTopologyChanged",
                    source_component="aura.monitor_topology",
                    session_id=session_id,
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "display_count": len(topology.displays),
                        "bounds": topology.bounds,
                        "metadata_only": True,
                    },
                ))
            return topology
