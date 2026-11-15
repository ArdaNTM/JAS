"""Offline Python source red-flag review and explicit contract-test generation.

Never imports or runs inspected modules, executes generated tests, edits
repositories, invokes MCP tools or claims a bug/fix is independently verified.
Generated tests MUST be reviewed and run only through an authorized sandbox.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,7}\Z", re.ASCII)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class StaticCodeFinding:
    line: int
    category: str
    untrusted: bool = True
    bug_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class CodeReview:
    source_sha256: str
    findings: tuple[StaticCodeFinding, ...]
    code_executed: bool = False
    bug_confirmed: bool = False
    authorization_checked: bool = False


@dataclass(frozen=True, slots=True)
class ContractCase:
    function_name: str
    arguments: tuple[Any, ...]
    keyword_arguments: dict[str, Any]
    expected: Any


@dataclass(frozen=True, slots=True)
class GeneratedContracts:
    module_name: str
    code: str
    case_count: int
    source_sha256: str
    executed: bool = False
    tests_passed: bool = False
    sandbox_authorization_checked: bool = False


def review_static_python(source: str) -> CodeReview:
    """Report limited AST patterns without executing/importing source."""
    if type(source) is not str or not source or "\x00" in source:
        raise ValueError("nonempty source code required")
    try:
        binary = source.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid Python source Unicode") from exc
    if len(binary) > 131072 or source.count("\n") > 6000:
        raise ValueError("Python source exceeds budget")
    try:
        root = ast.parse(source, type_comments=True)
    except (SyntaxError, RecursionError, MemoryError, ValueError) as exc:
        raise ValueError("unable to parse Python source") from exc
    findings: list[StaticCodeFinding] = []
    count = 0
    for node in ast.walk(root):
        count += 1
        if count > 25000:
            raise ValueError("Python AST node budget exceeded")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = [*node.args.defaults, *node.args.kw_defaults]
            if any(isinstance(value, (ast.List, ast.Dict, ast.Set)) for value in defaults):
                findings.append(StaticCodeFinding(node.lineno, "mutable_default"))
            terminated = False
            for statement in node.body:
                if terminated:
                    findings.append(StaticCodeFinding(statement.lineno, "unreachable_after_exit"))
                    break
                if isinstance(statement, (ast.Return, ast.Raise)):
                    terminated = True
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(StaticCodeFinding(node.lineno, "bare_except"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"eval", "exec"}
        ):
            findings.append(StaticCodeFinding(node.lineno, "dynamic_code_call"))
        if len(findings) > 128:
            raise ValueError("static review finding budget exceeded")
    findings.sort(key=lambda item: (item.line, item.category))
    return CodeReview(
        source_sha256=hashlib.sha256(binary).hexdigest(),
        findings=tuple(findings),
    )


def _json_safe(value: object, *, budget: list[int], depth: int = 0) -> None:
    budget[0] += 1
    if budget[0] > 400 or depth > 8:
        raise ValueError("test contract JSON complexity budget exceeded")
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        if len(value) > 2048:
            raise ValueError("test string too large")
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid test Unicode") from exc
        return
    if type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("invalid numeric test value")
        return
    if type(value) in (list, tuple):
        if len(value) > 32:
            raise ValueError("test list too large")
        for item in value:
            _json_safe(item, budget=budget, depth=depth + 1)
        return
    if type(value) is dict:
        if len(value) > 32:
            raise ValueError("test object too large")
        for key, item in value.items():
            if type(key) is not str or not _NAME.fullmatch(key):
                raise ValueError("invalid test JSON object key")
            _json_safe(item, budget=budget, depth=depth + 1)
        return
    raise ValueError("unsupported test contract value")


def generate_pytest_contracts(
    *, module_name: str, cases: tuple[ContractCase, ...],
) -> GeneratedContracts:
    """Generate runnable pytest for EXPLICIT user-supplied input/output cases.

    Generation itself never imports the destination module or runs a test.
    """
    if (
        type(module_name) is not str or not _MODULE.fullmatch(module_name)
        or any(part.startswith("__") for part in module_name.split("."))
    ):
        raise ValueError("invalid destination module name")
    if type(cases) is not tuple or not 1 <= len(cases) <= 40:
        raise ValueError("1..40 explicit contract cases required")
    encoded: list[tuple[str, str, str, str]] = []
    budget = [0]
    for case in cases:
        if type(case) is not ContractCase:
            raise ValueError("ContractCase required")
        function = case.function_name
        if type(function) is not str or not _NAME.fullmatch(function) or function.startswith("__"):
            raise ValueError("invalid target function name")
        if type(case.arguments) is not tuple or len(case.arguments) > 16:
            raise ValueError("contract args must be a tuple <=16")
        if type(case.keyword_arguments) is not dict or len(case.keyword_arguments) > 16:
            raise ValueError("contract kwargs must be a dict <=16")
        _json_safe(case.arguments, budget=budget)
        _json_safe(case.keyword_arguments, budget=budget)
        _json_safe(case.expected, budget=budget)
        try:
            args_json = json.dumps(case.arguments, ensure_ascii=True, allow_nan=False)
            kwargs_json = json.dumps(case.keyword_arguments, ensure_ascii=True, allow_nan=False)
            expected_json = json.dumps(case.expected, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError, RecursionError, OverflowError) as exc:
            raise ValueError("unserializable test contract") from exc
        encoded.append((function, args_json, kwargs_json, expected_json))
    params = ",\n".join(
        "    (" + ", ".join(repr(value) for value in row) + "),"
        for row in encoded
    )
    code = (
        "import importlib\nimport json\nimport pytest\n\n"
        '@pytest.mark.parametrize("function_name,args_json,kwargs_json,expected_json", [\n'
        + params + '\n])\n'
        "def test_generated_contract(function_name, args_json, kwargs_json, expected_json):\n"
        f"    subject = importlib.import_module({module_name!r})\n"
        "    function = getattr(subject, function_name)\n"
        "    assert callable(function)\n"
        "    observed = function(*json.loads(args_json), **json.loads(kwargs_json))\n"
        "    assert observed == json.loads(expected_json)\n"
    )
    if len(code.encode("utf-8")) > 40000:
        raise ValueError("generated pytest suite too large")
    ast.parse(code)
    return GeneratedContracts(
        module_name=module_name, code=code, case_count=len(cases),
        source_sha256=hashlib.sha256(code.encode("utf-8")).hexdigest(),
    )
