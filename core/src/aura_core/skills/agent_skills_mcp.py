"""Declarative AgentSkills-to-MCP adapter. Never executes imported skill code."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4
from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
@dataclass(frozen=True, slots=True)
class AgentSkillManifest:
    name: str
    description: str
    capability_id: str
    operation_id: str
    tool_name: str
    resource_scope: str
    risk_level: str = "low"
    source: str = "local"
    version: str = "1.0.0"

class AgentSkillsParser:
    """Strict scalar-frontmatter parser for the gateway-binding subset."""
    REQUIRED = {"name", "description", "capability_id", "operation_id", "tool_name", "resource_scope"}
    ALLOWED = REQUIRED | {"risk_level", "version"}
    @classmethod
    def parse(cls, markdown: str, *, source: str = "local") -> AgentSkillManifest:
        if not isinstance(markdown, str) or len(markdown) > 65536:
            raise ValueError("SKILL.md must be text no larger than 64 KiB")
        lines = markdown.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("SKILL.md must start with frontmatter")
        try: end = lines.index("---", 1)
        except ValueError as exc: raise ValueError("Unterminated frontmatter") from exc
        fields = {}
        for line in lines[1:end]:
            if not line.strip() or line.lstrip().startswith("#"): continue
            if ":" not in line: raise ValueError("Only scalar key: value fields are supported")
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in fields:
                raise ValueError("Invalid or duplicate frontmatter key")
            fields[key] = value
        if cls.REQUIRED - fields.keys(): raise ValueError("Missing required gateway binding fields")
        if fields.keys() - cls.ALLOWED: raise ValueError("Unsupported frontmatter fields")
        if not _NAME.fullmatch(fields["name"]): raise ValueError("Skill name must be kebab-case")
        if len(fields["description"]) > 1024: raise ValueError("Description too long")
        risk = fields.get("risk_level", "low")
        if risk not in {"low", "medium", "high", "critical"}: raise ValueError("Invalid risk level")
        return AgentSkillManifest(**{k: fields[k] for k in cls.REQUIRED},
            risk_level=risk, source=source, version=fields.get("version", "1.0.0"))

class AgentSkillsMCPRegistry:
    """Stores untrusted declarations; invocation is delegated to MCPGateway."""
    def __init__(self, *, max_skills: int = 500):
        if max_skills < 1: raise ValueError("max_skills must be positive")
        self.max_skills, self._items = max_skills, {}
    def register_markdown(self, markdown: str, *, source: str = "local") -> AgentSkillManifest:
        manifest = AgentSkillsParser.parse(markdown, source=source)
        if manifest.name not in self._items and len(self._items) >= self.max_skills:
            raise ValueError("Skill registry capacity reached")
        self._items[manifest.name] = manifest
        return manifest
    def catalog(self) -> tuple[AgentSkillManifest, ...]:
        return tuple(self._items[k] for k in sorted(self._items))
    def to_gateway_request(self, name: str, *, principal_id: str,
                           arguments: dict[str, Any] | None = None,
                           session_id: str | None = None,
                           task_id: str | None = None) -> MCPGatewayRequest:
        item = self._items.get(name)
        if item is None: raise KeyError(name)
        # No adapter-side authorization: Gateway + PermissionEngine decide.
        return MCPGatewayRequest(request_id=str(uuid4()), principal_id=principal_id,
            capability_id=item.capability_id, operation_id=item.operation_id,
            resource_scope=item.resource_scope, risk_level=RiskLevel(item.risk_level),
            tool_name=item.tool_name, arguments=arguments or {},
            session_id=session_id, task_id=task_id)
