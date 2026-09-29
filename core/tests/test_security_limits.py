from aura_core.security.limits import ExecutionLimiter


def test_execution_limiter_enforces_a_fixed_window() -> None:
    limiter = ExecutionLimiter(2, 60)
    assert limiter.acquire("agent:one").remaining == 1
    assert limiter.acquire("agent:one").remaining == 0
    assert limiter.acquire("agent:one").allowed is False
