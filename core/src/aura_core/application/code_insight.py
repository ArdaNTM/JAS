"""Read-only Python source architecture inspection and API documentation.

The caller must acquire source through an authenticated, governed capability.
AST parsing is offline: it never imports, evaluates or executes source code.
Observations are untrusted and cannot authorize actions or certify safety.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass

_MODULE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,9}\Z", re.ASCII)
_RISK_NAMES = frozenset({"eval", "exec", "compile", "__import__"})
_RISK_ATTRIBUTES = frozenset({
    "os.system", "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_output", "socket.socket", "requests.get",
    "requests.post", "urllib.urlopen",
})


@dataclass(frozen=True, slots=True)
class PythonSymbol:
    qualified_name: str
    kind: str
    line: int
    signature: str


@dataclass(frozen=True, slots=True)
class StaticCallFinding:
    review_category: str
    line: int
    untrusted: bool = True
    permission_granted: bool = False


@dataclass(frozen=True, slots=True)
class PythonModuleReport:
    module_id: str
    source_sha256: str
    imports: tuple[str, ...]
    symbols: tuple[PythonSymbol, ...]
    call_findings: tuple[StaticCallFinding, ...]
    untrusted: bool = True
    code_executed: bool = False
    authorization_checked: bool = False
    security_verified: bool = False


def _signature(name: str, args: ast.arguments, is_async: bool) -> str:
    names = [arg.arg for arg in args.posonlyargs]
    if args.posonlyargs:
        names.append("/")
    names.extend(arg.arg for arg in args.args)
    if args.vararg:
        names.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        names.append("*")
    names.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    signature = f"{'async ' if is_async else ''}{name}({', '.join(names)})"
    return signature[:300]


def inspect_python_source(
    source: str, *, module_id: str,
    max_symbols: int = 400, max_ast_nodes: int = 50000,
) -> PythonModuleReport:
    """Analyze a bounded source string without loading or running the module."""
    if type(source) is not str or not source or "\x00" in source:
        raise ValueError("nonempty valid source text required")
    try:
        raw = source.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid Unicode source") from exc
    if len(raw) > 262144 or source.count("\n") > 15000:
        raise ValueError("Python source budget exceeded")
    if type(module_id) is not str or not _MODULE.fullmatch(module_id):
        raise ValueError("invalid module identifier")
    if type(max_symbols) is not int or not 1 <= max_symbols <= 400:
        raise ValueError("invalid symbol budget")
    if type(max_ast_nodes) is not int or not 100 <= max_ast_nodes <= 50000:
        raise ValueError("invalid AST node budget")
    try:
        module = ast.parse(source, filename="<untrusted>", type_comments=True)
    except (SyntaxError, RecursionError, ValueError, MemoryError) as exc:
        raise ValueError("Python source could not be parsed") from exc

    imports: set[str] = set()
    risks: list[StaticCallFinding] = []
    visited = 0
    for node in ast.walk(module):
        visited += 1
        if visited > max_ast_nodes:
            raise ValueError("AST node budget exceeded")
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Call):
            function = node.func
            label = ""
            if isinstance(function, ast.Name) and function.id in _RISK_NAMES:
                label = function.id
            elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                candidate = f"{function.value.id}.{function.attr}"
                if candidate in _RISK_ATTRIBUTES:
                    label = candidate
            if label and len(risks) < 100:
                risks.append(StaticCallFinding(label, node.lineno))
        if len(imports) > 300:
            raise ValueError("too many imported modules")

    symbols: list[PythonSymbol] = []

    def add(name: str, kind: str, line: int, signature: str) -> None:
        if len(symbols) >= max_symbols:
            raise ValueError("public API symbol budget exceeded")
        symbols.append(PythonSymbol(name, kind, line, signature))

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                add(node.name, "function", node.lineno,
                    _signature(node.name, node.args, isinstance(node, ast.AsyncFunctionDef)))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            add(node.name, "class", node.lineno, f"class {node.name}")
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not member.name.startswith("_") or member.name == "__init__":
                        qualified = f"{node.name}.{member.name}"
                        add(qualified, "method", member.lineno,
                            _signature(qualified, member.args,
                                       isinstance(member, ast.AsyncFunctionDef)))
    risks.sort(key=lambda item: (item.line, item.review_category))
    return PythonModuleReport(
        module_id=module_id,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        imports=tuple(sorted(imports)),
        symbols=tuple(symbols),
        call_findings=tuple(risks),
    )


def render_python_api_markdown(report: PythonModuleReport) -> str:
    """Produce local Markdown API documentation without embedding source bodies."""
    if type(report) is not PythonModuleReport:
        raise ValueError("PythonModuleReport required")
    lines = [
        f"# Module \`{report.module_id}\`",
        "",
        "> Automatically derived, untrusted static observations. "
        "No code execution or security validation occurred.",
        "",
        "## Imports",
    ]
    lines.extend(f"- \`{module}\`" for module in report.imports)
    lines.extend(["", "## Public API"])
    lines.extend(
        f"- \`{symbol.signature}\` — {symbol.kind}, line {symbol.line}"
        for symbol in report.symbols
    )
    lines.extend(["", "## Calls requiring review"])
    lines.extend(
        f"- \`{item.review_category}\` at line {item.line} "
        "(heuristic; not a security verdict)"
        for item in report.call_findings
    )
    return "\n".join(lines) + "\n"
