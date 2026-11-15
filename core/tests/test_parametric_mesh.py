"""Parametric geometry and actual binary STL regression/security checks."""
from __future__ import annotations

import math
import struct
from dataclasses import replace

import pytest

from aura_core.application.parametric_mesh import (
    export_binary_stl, make_box, make_cylinder, validate_closed_mesh,
)


def test_real_box_mesh_is_closed_and_volume_matches_dimensions():
    mesh = make_box(width_mm=20, depth_mm=10, height_mm=5)
    assert len(mesh.vertices_mm) == 8
    assert len(mesh.triangles) == 12
    assert validate_closed_mesh(mesh)
    assert mesh.approximate_volume_mm3 == pytest.approx(1000.0, abs=1e-9)
    assert not mesh.physically_validated
    assert not mesh.manufacturing_approved
    assert not mesh.hardware_executed
    assert not mesh.authorization_checked


def test_cylinder_manifold_and_analytic_volume_approximation():
    mesh = make_cylinder(radius_mm=3, height_mm=4, segments=64)
    assert len(mesh.triangles) == 256
    assert validate_closed_mesh(mesh)
    analytical = math.pi * 3**2 * 4
    assert mesh.approximate_volume_mm3 == pytest.approx(analytical, rel=0.002)
    assert mesh == make_cylinder(radius_mm=3, height_mm=4, segments=64)


def test_binary_stl_structure_and_repeatable_bytes():
    mesh = make_box(width_mm=10, depth_mm=10, height_mm=10)
    data = export_binary_stl(mesh)
    assert len(data) == 84 + 50 * 12
    assert struct.unpack_from("<I", data, 80)[0] == 12
    first = struct.unpack_from("<12fH", data, 84)
    assert first[2] == pytest.approx(-1.0)
    assert first[-1] == 0
    assert data == export_binary_stl(mesh)
    assert b"UNTRUSTED" in data[:80]


def test_truncated_or_reoriented_surface_is_rejected():
    mesh = make_box(width_mm=1, depth_mm=2, height_mm=3)
    incomplete = replace(mesh, triangles=mesh.triangles[:-1])
    assert not validate_closed_mesh(incomplete)
    with pytest.raises(ValueError, match="closed"):
        export_binary_stl(incomplete)
    first = mesh.triangles[0]
    inverted = replace(mesh, triangles=((first[0], first[2], first[1]),) + mesh.triangles[1:])
    assert not validate_closed_mesh(inverted)


@pytest.mark.parametrize("parameters", [
    {"width_mm": True}, {"height_mm": float("nan")},
    {"depth_mm": float("inf")}, {"width_mm": -1},
    {"width_mm": 0.001}, {"depth_mm": 501},
])
def test_invalid_box_parameters_are_rejected(parameters):
    values = dict(width_mm=10, depth_mm=10, height_mm=10)
    with pytest.raises(ValueError):
        make_box(**dict(values, **parameters))


@pytest.mark.parametrize("segments", [True, 11, 129, 12.5])
def test_segment_count_validation(segments):
    with pytest.raises(ValueError):
        make_cylinder(radius_mm=2, height_mm=4, segments=segments)


def test_forged_hardware_or_approval_claims_rejected():
    mesh = make_box(width_mm=10, depth_mm=10, height_mm=10)
    with pytest.raises(ValueError, match="unverifiable"):
        export_binary_stl(replace(mesh, manufacturing_approved=True))
    with pytest.raises(ValueError):
        validate_closed_mesh({"not": "mesh"})
