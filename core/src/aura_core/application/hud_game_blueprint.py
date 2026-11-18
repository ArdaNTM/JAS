"""Pack 4 deterministic local game-prototype blueprint.

Pure data construction; no filesystem, network, shell, LLM, ScreenRead,
or MCP tool authority. The existing HUD/Three.js frontend renders it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GameObject:
    object_id: str
    shape: str
    x: float
    y: float
    z: float
    radius: float

    def as_json(self) -> dict[str, object]:
        return {"id":self.object_id,"shape":self.shape,
                "position":[self.x,self.y,self.z],"radius":self.radius}


@dataclass(frozen=True, slots=True)
class GameBlueprint:
    version: int
    seed: int
    arena: tuple[float, float]
    targets: tuple[GameObject, ...]
    digest: str

    def as_json(self) -> dict[str, object]:
        return {"version":self.version,"seed":self.seed,
                "arena":list(self.arena),
                "targets":[t.as_json() for t in self.targets],
                "digest":self.digest}


def generate_local_game(seed: int, target_count: int = 6) -> GameBlueprint:
    """Use deterministic xorshift32 placement with finite bounded geometry."""
    if type(seed) is not int or not 1 <= seed <= 2**31-1:
        raise ValueError("seed must be a bounded positive integer")
    if type(target_count) is not int or not 1 <= target_count <= 24:
        raise ValueError("target count must be 1..24")
    state = seed

    def rand() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        return state / 0xFFFFFFFF

    objects = []
    for i in range(target_count):
        x = round((rand() - 0.5) * 7.5, 4)
        y = round(0.6 + rand() * 2.0, 4)
        z = round((rand() - 0.5) * 5.0, 4)
        radius = round(0.2 + rand() * 0.25, 4)
        objects.append(GameObject(f"target-{i+1}", "sphere", x, y, z, radius))
    canonical = {"version":1, "seed":seed, "arena":[10.0, 7.0],
                 "targets":[v.as_json() for v in objects]}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True,
                          separators=(",", ":")).encode()).hexdigest()
    return GameBlueprint(1, seed, (10.0,7.0), tuple(objects), digest)


def verify_local_game(blueprint: GameBlueprint) -> bool:
    """Accept only the precise deterministic blueprint; never eval project data."""
    if not isinstance(blueprint, GameBlueprint):
        return False
    try:
        expected = generate_local_game(blueprint.seed, len(blueprint.targets))
        return expected == blueprint
    except (ValueError, TypeError):
        return False
