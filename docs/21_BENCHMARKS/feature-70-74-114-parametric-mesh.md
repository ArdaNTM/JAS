# Features #70, #74 and #114 — offline parametric geometry (partial)

`aura_core.application.parametric_mesh` provides a real deterministic
small triangle mesh generator for axis-aligned boxes and polygonal
cylinders with explicit **millimetre** units. It validates closed
oriented edge pairing, non-degenerate triangle normals and positive
signed volume, then emits real binary STL bytes suitable for downstream
inspection *after independent safety and manufacturing review*.

Scope:
- `make_box(width_mm, depth_mm, height_mm)`
- `make_cylinder(radius_mm, height_mm, segments=48)`
- `validate_closed_mesh(mesh)`
- `export_binary_stl(mesh)` (in-memory bytes only, no file or machine IO)

Limits: dimensions 0.1–500 mm; cylinders 12–128 segments, output ≤2,048
triangles. STL serialization uses the standard 80-byte header, 32-bit
triangle count and 50-byte facet records; tests decode these bytes.

**Do not interpret watertightness as printability, structural safety or
CAD validity.** This has no 3D UI, no mesh boolean operations, no holes,
no complex features, no engineering FEA/units conversion, no 3D printer
integration, and no guaranteed printer/material tolerances. STL bytes
contain coordinates but cannot express physical units; the generated
vertex coordinates are documented as millimetres by convention.
No physical tests or Owner/MCP authorization are performed.
`manufacturing_approved`, `physically_validated` and
`hardware_executed` remain false.

Feature #70 (CAD), #74 (prototype design), and #114 (3D modeling) are
**TESTING/PARTIAL** pending actual editable parametric CAD, render,
manufacturing validation and hardware acceptance.

Tests: `cd core && uv run pytest -q tests/test_parametric_mesh.py`,
full Core Assurance and Final Release Lock. No external packages.
