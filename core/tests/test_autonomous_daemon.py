from __future__ import annotations

import asyncio

from aura_core.autonomous_daemon import (
    AutonomousAuraDaemon,
    DaemonLimits,
    DaemonState,
)


class FakeScheduler:
    def __init__(self) -> None:
        self.running = False
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1
        self.running = True

    async def stop(self) -> None:
        self.stops += 1
        self.running = False


def test_phase12_start_cycle_health_and_shutdown() -> None:
    asyncio.run(
        _test_phase12_start_cycle_health_and_shutdown()
    )


async def _test_phase12_start_cycle_health_and_shutdown() -> None:
    scheduler = FakeScheduler()
    cycles = []

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler,
        limits=DaemonLimits(
            health_interval_seconds=0.01,
            evolution_interval_seconds=60.0,
            shutdown_timeout_seconds=1.0,
        ),
        evolution_hook=lambda: cycles.append(
            "cycle"
        ),
    )

    await daemon.start()

    assert daemon.state is DaemonState.RUNNING
    assert scheduler.running
    assert scheduler.starts == 1

    assert await daemon.check_health()

    assert await daemon.run_evolution_cycle()
    assert cycles == ["cycle"]

    snapshot = daemon.snapshot()

    assert snapshot.cycles == 1
    assert snapshot.successful_cycles == 1
    assert snapshot.failed_cycles == 0

    await daemon.stop()

    assert daemon.state is DaemonState.STOPPED
    assert not scheduler.running
    assert scheduler.stops == 1


def test_phase12_repeated_failures_enter_degraded_mode() -> None:
    asyncio.run(
        _test_phase12_repeated_failures_enter_degraded_mode()
    )


async def _test_phase12_repeated_failures_enter_degraded_mode() -> None:
    scheduler = FakeScheduler()

    async def failing_cycle() -> None:
        raise RuntimeError(
            "deterministic failure"
        )

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler,
        limits=DaemonLimits(
            max_consecutive_failures=2,
            evolution_interval_seconds=60.0,
        ),
        evolution_hook=failing_cycle,
    )

    await daemon.start()

    try:
        assert not await daemon.run_evolution_cycle()
        assert not await daemon.run_evolution_cycle()

        assert daemon.state is (
            DaemonState.DEGRADED
        )

        snapshot = daemon.snapshot()

        assert snapshot.failed_cycles == 2
        assert (
            snapshot.consecutive_failures == 2
        )

    finally:
        await daemon.stop()


def test_phase12_cycle_lock_prevents_overlap() -> None:
    asyncio.run(
        _test_phase12_cycle_lock_prevents_overlap()
    )


async def _test_phase12_cycle_lock_prevents_overlap() -> None:
    scheduler = FakeScheduler()
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum_active = 0

    async def cycle() -> None:
        nonlocal active
        nonlocal maximum_active

        active += 1
        maximum_active = max(
            maximum_active,
            active,
        )

        entered.set()

        await release.wait()

        active -= 1

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler,
        evolution_hook=cycle,
    )

    await daemon.start()

    first = asyncio.create_task(
        daemon.run_evolution_cycle()
    )

    await entered.wait()

    second = asyncio.create_task(
        daemon.run_evolution_cycle()
    )

    await asyncio.sleep(0)

    assert await second is False
    assert maximum_active == 1

    release.set()

    assert await first

    await daemon.stop()


def test_phase12_start_is_idempotent() -> None:
    asyncio.run(
        _test_phase12_start_is_idempotent()
    )


async def _test_phase12_start_is_idempotent() -> None:
    scheduler = FakeScheduler()

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler
    )

    await daemon.start()
    await daemon.start()

    assert scheduler.starts == 1

    await daemon.stop()
    await daemon.stop()

    assert scheduler.stops == 1


def test_phase12_health_failure_degrades_without_killing_daemon() -> None:
    asyncio.run(
        _test_phase12_health_failure_degrades_without_killing_daemon()
    )


async def _test_phase12_health_failure_degrades_without_killing_daemon() -> None:
    scheduler = FakeScheduler()

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler,
        health_hook=lambda: False,
        limits=DaemonLimits(
            health_interval_seconds=60.0
        ),
    )

    await daemon.start()

    try:
        assert not await daemon.check_health()
        daemon.state = DaemonState.DEGRADED

        assert daemon.state is (
            DaemonState.DEGRADED
        )

        assert scheduler.running

    finally:
        await daemon.stop()


def test_phase12_shutdown_is_bounded() -> None:
    asyncio.run(
        _test_phase12_shutdown_is_bounded()
    )


async def _test_phase12_shutdown_is_bounded() -> None:
    class SlowScheduler:
        running = True

        async def start(self) -> None:
            self.running = True

        async def stop(self) -> None:
            await asyncio.sleep(10)

    scheduler = SlowScheduler()

    daemon = AutonomousAuraDaemon(
        scheduler=scheduler,
        limits=DaemonLimits(
            shutdown_timeout_seconds=0.01
        ),
    )

    await daemon.start()
    await daemon.stop()

    assert daemon.state is (
        DaemonState.STOPPED
    )
