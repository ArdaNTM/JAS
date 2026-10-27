import asyncio
import time
from dataclasses import replace

import pytest

from aura_core.enterprise.runtime_controls import (
    BudgetExceeded, CircuitBreaker, CircuitOpenError, CircuitState,
    ExecutionBudget, HashChainAuditLedger,
)


def test_execution_budget_enforces_step_and_call_limits():
    budget = ExecutionBudget(max_steps=1, max_tool_calls=1)
    budget.consume_step()
    with pytest.raises(BudgetExceeded):
        budget.consume_step()
    budget.consume_tool_call()
    with pytest.raises(BudgetExceeded):
        budget.consume_tool_call()


def test_execution_budget_deadline_and_cancellation():
    expired = ExecutionBudget(deadline_monotonic=time.monotonic() - 1)
    with pytest.raises(BudgetExceeded):
        expired.check()
    with pytest.raises(asyncio.CancelledError):
        ExecutionBudget().check(cancelled=True)


def test_execution_budget_rejects_negative_limits():
    with pytest.raises(ValueError):
        ExecutionBudget(max_steps=-1)


def test_audit_ledger_is_hash_chained_and_excludes_arbitrary_payloads():
    ledger = HashChainAuditLedger()
    first = ledger.append(
        principal_id="local-user", action="filesystem.read",
        resource_scope="test-data", outcome="denied", reason_code="policy_denied",
    )
    second = ledger.append(
        principal_id="local-user", action="filesystem.read",
        resource_scope="test-data", outcome="allowed", reason_code="policy_allowed",
    )
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.record_hash
    assert ledger.verify()
    assert "arguments" not in first.__dataclass_fields__


def test_audit_ledger_rejects_empty_or_control_character_metadata():
    ledger = HashChainAuditLedger()
    with pytest.raises(ValueError):
        ledger.append(
            principal_id=" ", action="tool.call", resource_scope="local",
            outcome="denied", reason_code="invalid",
        )
    with pytest.raises(ValueError):
        ledger.append(
            principal_id="user\nsecret", action="tool.call", resource_scope="local",
            outcome="denied", reason_code="invalid",
        )


def test_audit_ledger_detects_record_tampering():
    ledger = HashChainAuditLedger()
    record = ledger.append(
        principal_id="local-user", action="tool.call", resource_scope="local",
        outcome="allowed", reason_code="policy_allowed",
    )
    ledger._records[0] = replace(record, outcome="denied")
    assert not ledger.verify()


def test_circuit_breaker_opens_after_threshold_and_rejects_calls():
    async def scenario():
        breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)

        async def fail():
            raise RuntimeError("provider failure")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(fail)
        assert breaker.state is CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await breaker.call(lambda: asyncio.sleep(0, result="should not run"))

    asyncio.run(scenario())


def test_circuit_breaker_closes_after_success():
    async def scenario():
        breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0)

        async def fail():
            raise RuntimeError("provider failure")

        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        assert breaker.state is CircuitState.OPEN
        result = await breaker.call(lambda: asyncio.sleep(0, result="ok"))
        assert result == "ok"
        assert breaker.state is CircuitState.CLOSED

    asyncio.run(scenario())


def test_circuit_breaker_does_not_count_cancellation_as_provider_failure():
    async def scenario():
        breaker = CircuitBreaker(failure_threshold=1)

        async def cancel():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await breaker.call(cancel)
        assert breaker.state is CircuitState.CLOSED

    asyncio.run(scenario())


def test_circuit_breaker_validates_configuration():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(timeout_seconds=0)



def test_circuit_breaker_late_success_cannot_close_circuit_opened_by_concurrent_failure():
    async def scenario():
        breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_success():
            started.set()
            await release.wait()
            return "late success"

        async def fail():
            raise RuntimeError("provider failure")

        slow_task = asyncio.create_task(breaker.call(slow_success))
        await started.wait()
        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        assert breaker.state is CircuitState.OPEN
        release.set()
        assert await slow_task == "late success"
        assert breaker.state is CircuitState.OPEN

    asyncio.run(scenario())
