# Features #47 and #53 — offline Python architecture and API documentation

AURA extends its existing application layer with `code_insight.py`, a
**static AST-only** analyzer. It receives Python text already obtained
through authorized repository/file access and extracts module imports,
public functions, classes/methods, and fixed-category calls worth security
review. `render_python_api_markdown(report)` produces deterministic
human-readable API documentation, **without embedding executable source
bodies, docstrings, secrets, runtime config, or tool credentials**.

Security:
- Only `ast.parse` is used; no `importlib`, `eval`, `exec`, shell,
  network request, model call, or automatic repository write occurs.
- 256-KiB source limit, up to 50k AST nodes, 400 public API symbols, 300
  imported module identities, 100 heuristic findings.
- All results are untrusted, non-authoritative observations. The
  heuristic detects known direct call syntax only, not aliases,
  reflection, dynamic imports, actual network access or full security risk.
- Source must be read by an authenticated, PermissionEngine/Gateway-authorized
  upstream caller; this code creates no new privileged tool or permission.
- The Markdown renderer is a local view, not a documentation publishing system.

Features #47 and #53 are **partial** until authenticated repository
integration, human code review, richer diagrams, versioned documentation
publishing and end-to-end acceptance exist.

Test: `cd core && uv run pytest -q tests/test_python_code_insight.py`
plus full Core Assurance and Final Release Lock.
