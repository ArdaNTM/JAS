"""AURA Stage C: SQLite-checkpointed LangGraph driver with Gateway-only execution.

The checkpoint ledger commits each action reservation *before* its external side
effect. Unknown results are never retried. A stopped run cannot be resumed,
including after process restart. No direct provider calls occur in this module.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import stat
import threading
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest

MAX_ACTIONS = 8
TIMEOUT_SECONDS = 120
_ALLOWED = {
    ("BrowserControl", "BrowserControl", "browser_action"),
    ("ScreenControl", "ScreenControl", "screen_control"),
}


class StageCError(RuntimeError):
    pass


def _private_storage(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise PermissionError("Stage C requires an existing absolute private storage directory")
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import require_private_acl
        require_private_acl(path.parent)
        if path.exists():
            require_private_acl(path)
    else:
        info = path.parent.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Stage C directory must be owned by current user, mode 0700")
        if path.exists():
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError("Stage C database must be a private regular file")


class StageCLedger:
    """Transactional record of budgets, approvals, stop state and action identity."""

    def __init__(self, db_path: Path):
        path = Path(db_path)
        _private_storage(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=5)
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA synchronous=FULL")
        if os.name == "nt" and not path.exists():
            raise RuntimeError("Stage C database provisioning failed")
        if os.name == "nt":
            from aura_core.evolution.windows_owner_storage import harden_private_acl
            harden_private_acl(path)
        else:
            os.chmod(path, 0o600)
        self._db.execute("""CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, principal TEXT NOT NULL, scope TEXT NOT NULL,
            goal TEXT NOT NULL, state TEXT NOT NULL, deadline REAL NOT NULL,
            plan TEXT, cursor INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0, approval_id TEXT, active_key TEXT,
            error TEXT NOT NULL DEFAULT ''
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS actions (
            action_key TEXT PRIMARY KEY, run_id TEXT NOT NULL,
            step_no INTEGER NOT NULL, state TEXT NOT NULL,
            UNIQUE(run_id, step_no)
        )""")
        self._db.execute("CREATE TABLE IF NOT EXISTS flags (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
        self._db.execute("INSERT OR IGNORE INTO flags VALUES ('stopped', 0)")
        self._db.commit()

    def _transaction(self, operation):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result = operation(self._db)
                self._db.commit()
                return result
            except BaseException:
                self._db.rollback()
                raise

    def stopped(self) -> bool:
        with self._lock:
            return bool(self._db.execute("SELECT value FROM flags WHERE name='stopped'").fetchone()[0])

    def create(self, principal: str, goal: str, scope: str) -> str:
        run_id = str(uuid4())
        def op(db):
            if db.execute("SELECT value FROM flags WHERE name='stopped'").fetchone()[0]:
                raise StageCError("Emergency kill switch is engaged")
            db.execute("INSERT INTO runs(run_id,principal,scope,goal,state,deadline) VALUES (?,?,?,?,?,?)",
                       (run_id, principal, scope, goal, "draft", time.time() + TIMEOUT_SECONDS))
        self._transaction(op)
        return run_id

    def get(self, run_id: str, principal: str) -> dict:
        with self._lock:
            self._db.row_factory = sqlite3.Row
            try:
                row = self._db.execute("SELECT * FROM runs WHERE run_id=? AND principal=?",
                                       (run_id, principal)).fetchone()
                if row is None:
                    raise KeyError("Stage C run not found")
                return dict(row)
            finally:
                self._db.row_factory = None

    def public(self, run_id: str, principal: str) -> dict:
        row = self.get(run_id, principal)
        # Never expose model-supplied raw arguments, page content or persisted goal.
        return {key: row[key] for key in
                ("run_id", "state", "cursor", "used", "deadline", "approval_id", "error")}

    def set_plan(self, run_id: str, principal: str, steps: list[dict]) -> None:
        def op(db):
            row = db.execute("SELECT state FROM runs WHERE run_id=? AND principal=?",
                             (run_id, principal)).fetchone()
            if row != ("draft",):
                raise StageCError("Plan already created or run disabled")
            db.execute("UPDATE runs SET plan=?,state='ready' WHERE run_id=? AND principal=?",
                       (json.dumps(steps, sort_keys=True), run_id, principal))
        self._transaction(op)

    def reserve(self, run_id: str, principal: str, *, resume: bool = False) -> tuple[dict, str, str | None]:
        def op(db):
            row = db.execute("""SELECT state,deadline,plan,cursor,used,approval_id,active_key
                                FROM runs WHERE run_id=? AND principal=?""",
                             (run_id, principal)).fetchone()
            if row is None or db.execute("SELECT value FROM flags WHERE name='stopped'").fetchone()[0]:
                raise StageCError("Run unavailable or stopped")
            state, deadline, plan, cursor, used, approval_id, active_key = row
            if time.time() >= deadline:
                db.execute("UPDATE runs SET state='expired' WHERE run_id=?", (run_id,))
                raise StageCError("Stage C deadline expired")
            if state == "awaiting_approval" and resume and approval_id and active_key:
                db.execute("UPDATE runs SET state='in_flight' WHERE run_id=?", (run_id,))
                db.execute("UPDATE actions SET state='in_flight' WHERE action_key=?", (active_key,))
                return json.loads(plan)[cursor], active_key, approval_id
            if state != "ready" or resume:
                raise StageCError("Run is not executable; unknown results cannot be replayed")
            steps = json.loads(plan)
            if used >= MAX_ACTIONS or cursor >= len(steps):
                raise StageCError("Action budget exhausted")
            step = steps[cursor]
            key = hashlib.sha256(f"{run_id}:{cursor}:{json.dumps(step, sort_keys=True)}".encode()).hexdigest()
            db.execute("INSERT INTO actions VALUES (?,?,?,'in_flight')",
                       (key, run_id, cursor))
            db.execute("""UPDATE runs SET state='in_flight',used=used+1,active_key=?,approval_id=NULL
                          WHERE run_id=?""", (key, run_id))
            return step, key, None
        return self._transaction(op)

    def complete(self, run_id: str, principal: str, key: str, status: str,
                 *, approval_id: str | None = None, error: str = "") -> None:
        if status not in {"approved_pending", "succeeded", "denied", "needs_review"}:
            raise ValueError("Unexpected action outcome")
        def op(db):
            row = db.execute("SELECT state,active_key,plan,cursor FROM runs WHERE run_id=? AND principal=?",
                             (run_id, principal)).fetchone()
            if row is None or row[0] != "in_flight" or row[1] != key:
                raise StageCError("Stale or mismatched completion")
            if db.execute("SELECT value FROM flags WHERE name='stopped'").fetchone()[0]:
                db.execute("UPDATE runs SET state='stopped' WHERE run_id=?", (run_id,))
                return
            if status == "approved_pending":
                if not approval_id:
                    raise ValueError("Gateway approval id required")
                db.execute("UPDATE runs SET state='awaiting_approval',approval_id=? WHERE run_id=?",
                           (approval_id, run_id))
            elif status == "succeeded":
                next_index = row[3] + 1
                terminal = "succeeded" if next_index == len(json.loads(row[2])) else "ready"
                db.execute("""UPDATE runs SET cursor=?,state=?,approval_id=NULL,active_key=NULL
                              WHERE run_id=?""", (next_index, terminal, run_id))
            else:
                db.execute("UPDATE runs SET state=?,error=?,approval_id=NULL WHERE run_id=?",
                           (status, error[:120], run_id))
            db.execute("UPDATE actions SET state=? WHERE action_key=?", (status, key))
        self._transaction(op)

    def mark_unknown(self, run_id: str, principal: str) -> None:
        def op(db):
            db.execute("""UPDATE runs SET state='needs_review',error='Execution outcome unknown'
                          WHERE run_id=? AND principal=? AND state IN ('draft','ready','in_flight')""",
                       (run_id, principal))
        self._transaction(op)

    def kill(self) -> None:
        def op(db):
            db.execute("UPDATE flags SET value=1 WHERE name='stopped'")
            db.execute("""UPDATE runs SET state='stopped',approval_id=NULL
                          WHERE state IN ('draft','ready','awaiting_approval','in_flight')""")
        self._transaction(op)


class FlowState(TypedDict):
    run_id: str
    principal: str
    resume: bool
    phase: str


class StageCController:
    """LangGraph nodes coordinate checkpoints; the Gateway owns all authorization."""

    def __init__(self, *, ledger: StageCLedger, gateway, planner, browser_sessions=None):
        self.ledger = ledger
        self.gateway = gateway
        self.planner = planner
        self.browser_sessions = browser_sessions
        self._tasks: dict[str, asyncio.Task] = {}
        self._mutex = asyncio.Lock()
        graph = StateGraph(FlowState)
        graph.add_node("plan", self._plan)
        graph.add_node("observe", self._observe)
        graph.add_node("execute", self._execute)
        graph.add_node("verify", self._verify)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "observe")
        graph.add_edge("observe", "execute")
        graph.add_edge("execute", "verify")
        graph.add_edge("verify", END)
        self.graph = graph.compile()

    async def _plan(self, state: FlowState):
        row = self.ledger.get(state["run_id"], state["principal"])
        if row["state"] != "draft":
            return {"phase": row["state"]}
        submissions = await self.planner.propose(
            goal=row["goal"], principal_id=row["principal"], resource_scope=row["scope"],
            iteration=1, feedback=(),
        )
        if len(submissions) != 1:
            raise StageCError("Planner must yield exactly one bounded plan")
        submitted = submissions[0]
        if submitted.task.principal_id != row["principal"] or submitted.task.resource_scope != row["scope"]:
            raise StageCError("Planner principal or scope mismatch")
        steps = []
        for step in submitted.plan.steps:
            binding = (step.capability_id, step.operation_id, step.tool_name)
            if binding not in _ALLOWED or step.risk_level != RiskLevel.HIGH or step.max_attempts != 1:
                raise StageCError("Planner operation, risk or retries not permitted")
            if not isinstance(step.arguments, dict):
                raise StageCError("Invalid operation arguments")
            args = dict(step.arguments)
            if step.capability_id == "BrowserControl":
                args["run_id"] = row["run_id"]
            steps.append({"capability": step.capability_id, "operation": step.operation_id,
                          "tool": step.tool_name, "arguments": args})
        if not 1 <= len(steps) <= MAX_ACTIONS:
            raise StageCError("Stage C action budget exceeded")
        self.ledger.set_plan(row["run_id"], row["principal"], steps)
        return {"phase": "ready"}

    async def _observe(self, state: FlowState):
        # Observations are only outputs of Gateway-approved steps. Never read the
        # screen/page directly inside graph nodes or treat its content as policy.
        row = self.ledger.get(state["run_id"], state["principal"])
        return {"phase": row["state"]}

    async def _execute(self, state: FlowState):
        run_id, principal = state["run_id"], state["principal"]
        row = self.ledger.get(run_id, principal)
        if row["state"] not in {"ready", "awaiting_approval"}:
            return {"phase": row["state"]}
        if row["state"] == "awaiting_approval" and not state["resume"]:
            return {"phase": "awaiting_approval"}
        step, key, approval = self.ledger.reserve(
            run_id, principal, resume=row["state"] == "awaiting_approval"
        )
        if self.ledger.stopped():
            self.ledger.mark_unknown(run_id, principal)
            return {"phase": "stopped"}
        request = MCPGatewayRequest(
            request_id=key, principal_id=principal,
            capability_id=step["capability"], operation_id=step["operation"],
            tool_name=step["tool"], arguments=step["arguments"],
            resource_scope=row["scope"], risk_level=RiskLevel.HIGH,
            task_id=run_id, approval_id=approval,
        )
        try:
            response = await asyncio.wait_for(
                self.gateway.invoke(request),
                timeout=max(0.1, row["deadline"] - time.time()),
            )
        except BaseException:
            self.ledger.mark_unknown(run_id, principal)
            raise
        if response.decision is AuthorizationDecision.REQUIRE_APPROVAL and response.approval_id:
            self.ledger.complete(run_id, principal, key, "approved_pending",
                                 approval_id=response.approval_id)
        elif response.decision is AuthorizationDecision.ALLOW and not (
                isinstance(response.result, dict) and response.result.get("isError") is True):
            self.ledger.complete(run_id, principal, key, "succeeded")
        else:
            self.ledger.complete(run_id, principal, key, "denied",
                                 error="Gateway declined or tool reported error")
        return {"phase": self.ledger.get(run_id, principal)["state"]}

    async def _verify(self, state: FlowState):
        # Durable completion is the authoritative evidence; never trust model
        # claims that an action succeeded.
        row = self.ledger.get(state["run_id"], state["principal"])
        return {"phase": row["state"]}

    async def execute_until_pause(self, run_id: str, principal: str, *, resume=False):
        async with self._mutex:  # one GUI action at a time across all runs
            for index in range(MAX_ACTIONS + 1):
                if self.ledger.stopped():
                    return self.ledger.public(run_id, principal)
                row = self.ledger.get(run_id, principal)
                if row["state"] not in {"draft", "ready", "awaiting_approval"}:
                    return self.ledger.public(run_id, principal)
                if row["state"] == "awaiting_approval" and not resume:
                    return self.ledger.public(run_id, principal)
                try:
                    await self.graph.ainvoke(
                        {"run_id": run_id, "principal": principal, "resume": resume, "phase": ""},
                        config={"recursion_limit": 16},
                    )
                except BaseException:
                    self.ledger.mark_unknown(run_id, principal)
                    raise
                resume = False
            raise StageCError("Step iteration budget unexpectedly exceeded")

    def start(self, run_id: str, principal: str, *, resume=False) -> None:
        previous = self._tasks.get(run_id)
        if previous and not previous.done():
            raise StageCError("Run already active")
        async def worker():
            try:
                await self.execute_until_pause(run_id, principal, resume=resume)
            except asyncio.CancelledError:
                self.ledger.mark_unknown(run_id, principal)
                raise
            except Exception:
                self.ledger.mark_unknown(run_id, principal)
            finally:
                state = self.ledger.get(run_id, principal)["state"]
                if state not in {"awaiting_approval", "ready"} and self.browser_sessions is not None:
                    await self.browser_sessions.close(run_id)
        self._tasks[run_id] = asyncio.create_task(worker(), name=f"stage-c-{run_id}")

    async def kill(self):
        self.ledger.kill()  # committed before cancellation; survives restart
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        if self.browser_sessions is not None:
            await self.browser_sessions.close_all()
