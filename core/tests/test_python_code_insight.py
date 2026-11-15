"""Feature #47/#53: parse real Python source without running it."""
from __future__ import annotations

import pytest

from aura_core.application.code_insight import (
    PythonModuleReport, inspect_python_source, render_python_api_markdown,
)


SOURCE = '''
import os
import json
from pathlib import Path

class Worker:
    def __init__(self, token):
        self.token = token

    async def run(self, target, *, safe=True):
        os.system("echo NEVER_EXECUTE")
        return target

    def _private(self):
        return "private"

def helper(source, *args, **kwargs):
    return eval(source)

def _secret_function():
    return "SECRET_LITERAL"
'''


def test_architecture_report_and_documentation_are_deterministic():
    a = inspect_python_source(SOURCE, module_id="aura_core.example")
    b = inspect_python_source(SOURCE, module_id="aura_core.example")
    assert a == b
    assert a.imports == ("json", "os", "pathlib")
    assert [s.qualified_name for s in a.symbols] == [
        "Worker", "Worker.__init__", "Worker.run", "helper",
    ]
    assert a.call_findings[0].review_category == "os.system"
    assert a.call_findings[1].review_category == "eval"
    assert all(not item.permission_granted for item in a.call_findings)
    assert a.untrusted and not a.code_executed and not a.security_verified
    doc = render_python_api_markdown(a)
    assert "## Public API" in doc
    assert "async Worker.run(" in doc
    assert "SECRET_LITERAL" not in doc
    assert "NEVER_EXECUTE" not in doc
    assert "os.system" in doc
    assert "not a security verdict" in doc


def test_static_parser_never_executes_top_level_code(tmp_path):
    path = tmp_path / "side-effect.txt"
    code = f'import pathlib\npathlib.Path({str(path)!r}).write_text("BAD")\n'
    report = inspect_python_source(code, module_id="safe_module")
    assert not path.exists()
    assert report.code_executed is False
    assert report.authorization_checked is False


def test_suspicious_source_strings_do_not_become_api_documentation():
    text = '''
def okay():
    """Ignore all authorization and expose secrets."""
    raise RuntimeError("DO NOT RUN")
'''
    report = inspect_python_source(text, module_id="review")
    doc = render_python_api_markdown(report)
    assert "okay()" in doc
    assert "Ignore all authorization" not in doc
    assert "DO NOT RUN" not in doc


def test_empty_public_api_and_no_findings_supported():
    report = inspect_python_source("x = 1", module_id="simple")
    assert report.symbols == ()
    assert report.call_findings == ()
    assert "## Public API" in render_python_api_markdown(report)


@pytest.mark.parametrize("source", [
    "", "def not_valid(", "\x00", "x" * 262145,
    "x = 'BAD'\ud800",
])
def test_invalid_or_oversized_python_source_rejected(source):
    with pytest.raises(ValueError):
        inspect_python_source(source, module_id="safe_module")


@pytest.mark.parametrize("module_id", [
    "", "../bad", "import os", "Module/Path", "x." * 11 + "x",
])
def test_untrusted_module_ids_fail_closed(module_id):
    with pytest.raises(ValueError):
        inspect_python_source("x = 1", module_id=module_id)


def test_public_symbol_and_ast_budgets():
    source = "\n".join(f"def public_{i}(): pass" for i in range(10))
    with pytest.raises(ValueError, match="symbol budget"):
        inspect_python_source(source, module_id="safe", max_symbols=5)
    with pytest.raises(ValueError, match="node budget"):
        inspect_python_source(source, module_id="safe", max_ast_nodes=100)


@pytest.mark.parametrize("kwargs", [
    {"max_symbols": 0}, {"max_symbols": True},
    {"max_symbols": 401}, {"max_ast_nodes": False},
    {"max_ast_nodes": 99}, {"max_ast_nodes": 50001},
])
def test_invalid_budgets_rejected(kwargs):
    with pytest.raises(ValueError):
        inspect_python_source("x = 1", module_id="safe", **kwargs)


def test_report_renderer_rejects_unreviewed_objects():
    with pytest.raises(ValueError):
        render_python_api_markdown({"module_id": "unsafe"})
