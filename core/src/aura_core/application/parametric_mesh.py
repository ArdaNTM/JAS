"""Deterministic offline box/cylinder triangle meshes and binary STL bytes.

These are mathematical prototyping aids, not certified CAD, structural
engineering validation, machine commands or printing authorization.
"""
from __future__ import annotations

import math
import struct
from collections import defaultdict
from dataclasses import dataclass

Vec3 = tuple[float, float, float]
Face = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class PrototypeMesh:
    vertices_mm: tuple[Vec3, ...]
    triangles: tuple[Face, ...]
    approximate_volume_mm3: float
    untrusted_geometry: bool = True
    physically_validated: bool = False
    manufacturing_approved: bool = False
    hardware_executed: bool = False
    authorization_checked: bool = False


def _length(number: float, label: str) -> float:
    if (
        type(number) not in (float, int)
        or not math.isfinite(number)
        or not 0.1 <= number <= 500
    ):
        raise ValueError(f"invalid {label} (millimetres)")
    return float(number)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def validate_closed_mesh(mesh: PrototypeMesh) -> bool:
    """Check nondegenerate triangular geometry and oriented edge pairing."""
    if type(mesh) is not PrototypeMesh:
        raise ValueError("PrototypeMesh required")
    vertices, triangles = mesh.vertices_mm, mesh.triangles
    if (
        not 4 <= len(vertices) <= 600
        or not 4 <= len(triangles) <= 2048
        or any(
            type(point) is not tuple
            or len(point) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)
            for point in vertices
        )
    ):
        return False
    edges: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face in triangles:
        if type(face) is not tuple or len(face) != 3:
            return False
        if any(type(index) is not int or not 0 <= index < len(vertices) for index in face):
            return False
        if len(set(face)) != 3:
            return False
        a, b, c = (vertices[index] for index in face)
        normal = _cross(_sub(b, a), _sub(c, a))
        if not math.isfinite(sum(value * value for value in normal)):
            return False
        if sum(value * value for value in normal) <= 1e-12:
            return False
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            key = (min(start, end), max(start, end))
            edges[key].append(1 if start < end else -1)
    return all(len(signs) == 2 and sum(signs) == 0 for signs in edges.values())


def _assemble(vertices: list[Vec3], faces: list[Face]) -> PrototypeMesh:
    mesh = PrototypeMesh(tuple(vertices), tuple(faces), 0.0)
    if not validate_closed_mesh(mesh):
        raise ValueError("generated triangle surface is not closed and oriented")
    signed = 0.0
    for i, j, k in mesh.triangles:
        a, b, c = mesh.vertices_mm[i], mesh.vertices_mm[j], mesh.vertices_mm[k]
        cross = _cross(b, c)
        signed += (a[0] * cross[0] + a[1] * cross[1] + a[2] * cross[2]) / 6
    if not math.isfinite(signed) or signed <= 0:
        raise ValueError("invalid signed prototype mesh volume")
    return PrototypeMesh(mesh.vertices_mm, mesh.triangles, signed)


def make_box(*, width_mm: float, depth_mm: float, height_mm: float) -> PrototypeMesh:
    """Generate a closed outward-oriented rectangle prism in millimetres."""
    w = _length(width_mm, "width")
    d = _length(depth_mm, "depth")
    h = _length(height_mm, "height")
    vertices = [
        (0.0, 0.0, 0.0), (w, 0.0, 0.0), (w, d, 0.0), (0.0, d, 0.0),
        (0.0, 0.0, h), (w, 0.0, h), (w, d, h), (0.0, d, h),
    ]
    faces = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
        (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5),
    ]
    return _assemble(vertices, faces)


def make_cylinder(
    *, radius_mm: float, height_mm: float, segments: int = 48
) -> PrototypeMesh:
    """Generate a watertight inscribed polygonal cylinder approximation."""
    radius = _length(radius_mm, "radius")
    height = _length(height_mm, "height")
    if type(segments) is not int or not 12 <= segments <= 128:
        raise ValueError("segments must be 12..128")
    ring = [
        (radius * math.cos(2 * math.pi * i / segments),
         radius * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]
    vertices = (
        [(x, y, 0.0) for x, y in ring]
        + [(x, y, height) for x, y in ring]
        + [(0.0, 0.0, 0.0), (0.0, 0.0, height)]
    )
    bottom_center, top_center = 2 * segments, 2 * segments + 1
    faces: list[Face] = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.extend([
            (bottom_center, j, i),
            (top_center, segments + i, segments + j),
            (i, j, segments + j),
            (i, segments + j, segments + i),
        ])
    return _assemble(vertices, faces)


def export_binary_stl(mesh: PrototypeMesh) -> bytes:
    """Serialize closed triangles to STL bytes without writing to disk."""
    if not validate_closed_mesh(mesh):
        raise ValueError("STL requires a bounded closed oriented mesh")
    if (
        mesh.physically_validated or mesh.manufacturing_approved
        or mesh.hardware_executed or mesh.authorization_checked
    ):
        raise ValueError("unverifiable safety/authorization flags on geometry")
    output = bytearray(b"AURA UNTRUSTED OFFLINE PROTOTYPE STL".ljust(80, b"\0"))
    output += struct.pack("<I", len(mesh.triangles))
    for i, j, k in mesh.triangles:
        a, b, c = (mesh.vertices_mm[index] for index in (i, j, k))
        normal = _cross(_sub(b, a), _sub(c, a))
        norm = math.sqrt(sum(value * value for value in normal))
        unit = tuple(value / norm for value in normal)
        values = (*unit, *a, *b, *c)
        if not all(math.isfinite(value) and abs(value) < 1e9 for value in values):
            raise ValueError("STL float values exceed bounds")
        output += struct.pack("<12fH", *values, 0)
    return bytes(output)
