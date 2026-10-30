"""CodeAct Docker provider; requires a consumed high-risk Gateway approval."""
import json
from typing import Any
from aura_core.application.sandbox_contract import SandboxJob, SandboxPolicy
from aura_core.application.sandbox_runner import DockerPythonRunner
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.dispatch_context import current_dispatch

class CodeActSandboxMCPProvider:
    provider_id = "aura.codeact-sandbox"
    requires_approval = True
    def __init__(self, *, policy=None, runner=None):
        self.policy = policy or SandboxPolicy()
        self.runner = runner or DockerPythonRunner(policy=self.policy, authorizer=self._authorize)

    @staticmethod
    def _authorize(job):
        grant = current_dispatch()
        return bool(grant and grant.approval_consumed and grant.risk_level in {"high","critical"}
            and grant.principal_id == job.principal_id and grant.tool_name == "codeact_execute")

    async def list_tools(self):
        return (MCPTool("codeact_execute", "Execute Python in isolated Docker after high-risk approval", {
            "type":"object","properties":{"job_id":{"type":"string","minLength":1,"maxLength":200},
            "source":{"type":"string","minLength":1,"maxLength":64000},"input":{"type":"object"}},
            "required":["job_id","source"],"additionalProperties":False}),)

    async def call_tool(self, name, arguments=None):
        args = arguments or {}
        grant = current_dispatch()
        if name != "codeact_execute" or grant is None:
            raise PermissionError("CodeAct must be dispatched by MCP Gateway")
        job = SandboxJob(job_id=args["job_id"], principal_id=grant.principal_id, runner="docker",
            source=args["source"], input_json=json.dumps(args.get("input",{}),separators=(",",":")),
            authorization_id="gateway-consumed-approval" if grant.approval_consumed else "")
        if not self._authorize(job):
            raise PermissionError("CodeAct requires consumed high-risk ApprovalStore authorization")
        result = self.runner.run(job)
        return {"job_id":result.job_id,"status":result.status,"return_code":result.return_code,
            "stdout":result.stdout,"stderr":result.stderr,"elapsed_seconds":result.elapsed_seconds,
            "isolation":result.isolation}
