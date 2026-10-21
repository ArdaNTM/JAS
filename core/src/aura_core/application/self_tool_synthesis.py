"""Proposal-first candidate tool synthesis; no automatic code execution or registration."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_ALLOWED_IMPORTS = {"math", "json", "re", "statistics"}


@dataclass(frozen=True, slots=True)
class ToolCandidate:
    tool_name: str
    description: str
    source_code: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.source_code.encode("utf-8")).hexdigest()

    def manifest(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "source_sha256": self.digest,
            "status": "proposal_only",
            "execution_enabled": False,
            "registration_enabled": False,
        }


class CandidateToolValidator:
    """Static validator for proposal artifacts, not a claim of a secure Python sandbox.

    Arbitrary Python cannot be safely sandboxed by AST checks alone. Consequently
    this validator never executes the submitted source. A platform-specific,
    OS-isolated runner and explicit human approval are required before deployment.
    """
    _FORBIDDEN_NAMES = {
        "eval", "exec", "compile", "open", "input", "globals", "locals",
        "vars", "getattr", "setattr", "delattr", "__import__", "breakpoint",
    }

    def validate(self, candidate: ToolCandidate) -> dict[str, Any]:
        errors: list[str] = []
        if not _TOOL_NAME.fullmatch(candidate.tool_name):
            errors.append("tool_name must be a lowercase identifier (3..64 chars)")
        if not candidate.description.strip() or len(candidate.description) > 500:
            errors.append("description must contain 1..500 characters")
        if len(candidate.source_code) > 24000:
            errors.append("source_code exceeds 24000 characters")
        if not isinstance(candidate.input_schema, dict) or not isinstance(candidate.output_schema, dict):
            errors.append("input_schema and output_schema must be objects")
        try:
            tree = ast.parse(candidate.source_code, mode="exec")
            if len(list(ast.walk(tree))) > 1500:
                errors.append("source contains too many syntax nodes")
            for node in ast.walk(tree):
                if isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    errors.append(f"unsupported construct: {type(node).__name__}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] not in _ALLOWED_IMPORTS:
                            errors.append(f"import not allow-listed: {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if not node.module or node.module.split(".")[0] not in _ALLOWED_IMPORTS:
                        errors.append("from-import is not allow-listed")
                if isinstance(node, ast.Name) and node.id in self._FORBIDDEN_NAMES:
                    errors.append(f"forbidden name: {node.id}")
                if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                    errors.append("private/dunder attribute access is forbidden")
                if isinstance(node, (ast.While, ast.Try, ast.With, ast.AsyncWith)):
                    errors.append(f"unsupported construct: {type(node).__name__}")
        except SyntaxError as exc:
            errors.append(f"syntax error at line {exc.lineno}: {exc.msg}")
        required = {"run"}
        if "tree" in locals():
            functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            if not required.issubset(functions):
                errors.append("candidate must define a top-level run(data) function")
        return {
            "valid": not errors,
            "errors": sorted(set(errors)),
            "source_sha256": candidate.digest,
            "status": "proposal_only",
            "static_validation_only": True,
            "sandbox_execution": "not_performed",
            "registration": "requires human approval, OS sandbox, and Capability Registry integration",
        }

    def create_proposal(self, candidate: ToolCandidate) -> dict[str, Any]:
        validation = self.validate(candidate)
        return {"manifest": candidate.manifest(), "validation": validation}
