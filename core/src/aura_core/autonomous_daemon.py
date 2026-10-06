from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class DaemonState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DaemonLimits:
    health_interval_seconds: float = 30.0
    evolution_interval_seconds: float = 300.0
    shutdown_timeout_seconds: float = 30.0
    max_consecutive_failures: int = 3
    max_cycle_runtime_seconds: float = 300.0
    max_component_failures: int = 3

    def validate(self) -> None:
        if self.health_interval_seconds <= 0:
            raise ValueError(
                "health_interval_seconds must be positive"
            )

        if self.evolution_interval_seconds <= 0:
            raise ValueError(
                "evolution_interval_seconds must be positive"
            )

        if self.shutdown_timeout_seconds <= 0:
            raise ValueError(
                "shutdown_timeout_seconds must be positive"
            )

        if self.max_consecutive_failures < 1:
            raise ValueError(
                "max_consecutive_failures must be >= 1"
            )

        if self.max_component_failures < 1:
            raise ValueError(
                "max_component_failures must be >= 1"
            )

        if self.max_cycle_runtime_seconds <= 0:
            raise ValueError(
                "max_cycle_runtime_seconds must be positive"
            )


@dataclass(slots=True)
class ComponentStatus:
    name: str
    running: bool = False
    failures: int = 0
    last_error: str | None = None
    last_started_at: float | None = None
    last_stopped_at: float | None = None


@dataclass(slots=True)
class DaemonSnapshot:
    state: DaemonState
    started_at: float | None
    cycles: int
    successful_cycles: int
    failed_cycles: int
    consecutive_failures: int
    last_cycle_at: float | None
    last_error: str | None
    components: dict[str, ComponentStatus] = field(
        default_factory=dict
    )


LifecycleHook = Callable[
    [],
    Awaitable[Any] | Any,
]

CycleHook = Callable[
    [],
    Awaitable[Any] | Any,
]

HealthHook = Callable[
    [],
    Awaitable[bool] | bool,
]


class AutonomousAuraDaemon:
    """
    Long-lived supervisory root for AURA autonomy.

    Safety invariants:

    1. The daemon never bypasses MCPGateway.
    2. The daemon never modifies PermissionEngine policy.
    3. The daemon never mutates Kernel registries directly.
    4. Learning components are dependencies, not authorities.
    5. A failed autonomous cycle does not automatically restart the
       entire process.
    6. Repeated failures transition the daemon to DEGRADED.
    7. Shutdown first stops new autonomous work, then drains children.
    8. All shutdown waits are bounded.
    """

    def __init__(
        self,
        *,
        kernel: Any | None = None,
        scheduler: Any | None = None,
        tool_learner: Any | None = None,
        self_improvement: Any | None = None,
        event_bus: Any | None = None,
        limits: DaemonLimits | None = None,
        evolution_hook: CycleHook | None = None,
        health_hook: HealthHook | None = None,
    ) -> None:
        self.kernel = kernel
        self.scheduler = scheduler
        self.tool_learner = tool_learner
        self.self_improvement = (
            self_improvement
        )
        self.event_bus = event_bus

        self.limits = (
            limits or DaemonLimits()
        )
        self.limits.validate()

        self.evolution_hook = evolution_hook
        self.health_hook = health_hook

        self.state = DaemonState.CREATED

        self._stop = asyncio.Event()
        self._wake = asyncio.Event()

        self._supervisor_task: (
            asyncio.Task[None] | None
        ) = None
        self._health_task: (
            asyncio.Task[None] | None
        ) = None
        self._evolution_task: (
            asyncio.Task[None] | None
        ) = None

        self._cycle_lock = asyncio.Lock()

        self._started_at: float | None = None
        self._last_cycle_at: float | None = None
        self._last_error: str | None = None

        self._cycles = 0
        self._successful_cycles = 0
        self._failed_cycles = 0
        self._consecutive_failures = 0

        self._components: dict[
            str,
            ComponentStatus,
        ] = {}

        self._register_components()

    def _register_components(self) -> None:
        components = {
            "kernel": self.kernel,
            "scheduler": self.scheduler,
            "tool_learner": self.tool_learner,
            "self_improvement": (
                self.self_improvement
            ),
            "event_bus": self.event_bus,
        }

        self._components = {
            name: ComponentStatus(name=name)
            for name, component in components.items()
            if component is not None
        }

    @staticmethod
    async def _invoke(
        component: Any,
        method_name: str,
    ) -> Any:
        method = getattr(
            component,
            method_name,
            None,
        )

        if method is None:
            return None

        result = method()

        if inspect.isawaitable(result):
            return await result

        return result

    @staticmethod
    def _is_running(
        component: Any,
    ) -> bool:
        running = getattr(
            component,
            "running",
            None,
        )

        if isinstance(running, bool):
            return running

        state = getattr(
            component,
            "state",
            None,
        )

        if state is None:
            return True

        value = getattr(
            state,
            "value",
            state,
        )

        return str(value).lower() in {
            "running",
            "started",
            "active",
        }

    async def _start_component(
        self,
        name: str,
        component: Any,
    ) -> None:
        status = self._components[name]

        try:
            await self._invoke(
                component,
                "start",
            )

            status.running = self._is_running(
                component
            )
            status.failures = 0
            status.last_error = None
            status.last_started_at = (
                time.monotonic()
            )

        except Exception as exc:
            status.running = False
            status.failures += 1
            status.last_error = (
                f"{type(exc).__name__}: {exc}"
            )
            raise

    async def _stop_component(
        self,
        name: str,
        component: Any,
    ) -> None:
        status = self._components[name]

        try:
            await self._invoke(
                component,
                "stop",
            )
        finally:
            status.running = False
            status.last_stopped_at = (
                time.monotonic()
            )

    async def start(self) -> None:
        if self.state in {
            DaemonState.STARTING,
            DaemonState.RUNNING,
        }:
            return

        if self.state is DaemonState.DRAINING:
            raise RuntimeError(
                "Cannot start daemon while draining"
            )

        self.state = DaemonState.STARTING
        self._stop.clear()
        self._wake.clear()

        self._started_at = time.monotonic()
        self._last_error = None
        self._consecutive_failures = 0

        try:
            if self.scheduler is not None:
                await self._start_component(
                    "scheduler",
                    self.scheduler,
                )

            self._supervisor_task = (
                asyncio.create_task(
                    self._supervisor_loop(),
                    name="aura-daemon-supervisor",
                )
            )

            self._health_task = (
                asyncio.create_task(
                    self._health_loop(),
                    name="aura-daemon-health",
                )
            )

            self._evolution_task = (
                asyncio.create_task(
                    self._evolution_loop(),
                    name="aura-daemon-evolution",
                )
            )

            self.state = DaemonState.RUNNING

            logger.info(
                "Autonomous AURA daemon started"
            )

        except Exception as exc:
            self.state = DaemonState.FAILED
            self._last_error = (
                f"{type(exc).__name__}: {exc}"
            )

            await self._cancel_background_tasks()

            raise

    async def stop(self) -> None:
        if self.state is DaemonState.STOPPED:
            return

        self.state = DaemonState.DRAINING
        self._stop.set()
        self._wake.set()

        logger.info(
            "Autonomous AURA daemon entering graceful drain"
        )

        await self._cancel_background_tasks()

        if self.scheduler is not None:
            try:
                await asyncio.wait_for(
                    self._stop_component(
                        "scheduler",
                        self.scheduler,
                    ),
                    timeout=(
                        self.limits.shutdown_timeout_seconds
                    ),
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Scheduler shutdown timed out"
                )

        self.state = DaemonState.STOPPED

        logger.info(
            "Autonomous AURA daemon stopped"
        )

    async def _cancel_background_tasks(
        self,
    ) -> None:
        tasks = [
            task
            for task in (
                self._supervisor_task,
                self._health_task,
                self._evolution_task,
            )
            if task is not None
        ]

        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._supervisor_task = None
        self._health_task = None
        self._evolution_task = None

    async def _evolution_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=(
                        self.limits.evolution_interval_seconds
                    ),
                )

                self._wake.clear()

            except asyncio.TimeoutError:
                pass

            if self._stop.is_set():
                break

            await self.run_evolution_cycle()

    async def run_evolution_cycle(self) -> bool:
        if self._stop.is_set():
            return False

        if self.state not in {
            DaemonState.RUNNING,
            DaemonState.DEGRADED,
        }:
            return False

        if self._cycle_lock.locked():
            return False

        async with self._cycle_lock:
            started = time.monotonic()
            self._cycles += 1

            try:
                if self.evolution_hook is not None:
                    await asyncio.wait_for(
                        self._invoke_hook(
                            self.evolution_hook
                        ),
                        timeout=(
                            self.limits.max_cycle_runtime_seconds
                        ),
                    )

                self._successful_cycles += 1
                self._consecutive_failures = 0

                if self.state is DaemonState.DEGRADED:
                    self.state = DaemonState.RUNNING

                self._last_cycle_at = (
                    time.monotonic()
                )

                return True

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._failed_cycles += 1
                self._consecutive_failures += 1
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                self._last_cycle_at = (
                    time.monotonic()
                )

                if (
                    self._consecutive_failures
                    >= self.limits.max_consecutive_failures
                ):
                    self.state = (
                        DaemonState.DEGRADED
                    )

                logger.exception(
                    "Autonomous evolution cycle failed"
                )

                return False

            finally:
                elapsed = (
                    time.monotonic()
                    - started
                )

                logger.debug(
                    "Autonomous evolution cycle finished "
                    "in %.3fs",
                    elapsed,
                )

    async def _invoke_hook(
        self,
        hook: Callable,
    ) -> Any:
        result = hook()

        if inspect.isawaitable(result):
            return await result

        return result

    async def _health_loop(self) -> None:
        while not self._stop.is_set():
            try:
                healthy = await self.check_health()

                if not healthy:
                    self.state = (
                        DaemonState.DEGRADED
                    )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                self.state = (
                    DaemonState.DEGRADED
                )

                logger.exception(
                    "Autonomous AURA health check failed"
                )

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=(
                        self.limits.health_interval_seconds
                    ),
                )
            except asyncio.TimeoutError:
                pass

    async def check_health(self) -> bool:
        if self._stop.is_set():
            return False

        if self.health_hook is not None:
            result = self.health_hook()

            if inspect.isawaitable(result):
                result = await result

            if not bool(result):
                return False

        if (
            self.scheduler is not None
            and not self._is_running(
                self.scheduler
            )
        ):
            return False

        return True

    async def _supervisor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                pass

            if self._stop.is_set():
                break

            if (
                self._consecutive_failures
                >= self.limits.max_consecutive_failures
            ):
                self.state = (
                    DaemonState.DEGRADED
                )

    def snapshot(self) -> DaemonSnapshot:
        return DaemonSnapshot(
            state=self.state,
            started_at=self._started_at,
            cycles=self._cycles,
            successful_cycles=(
                self._successful_cycles
            ),
            failed_cycles=self._failed_cycles,
            consecutive_failures=(
                self._consecutive_failures
            ),
            last_cycle_at=self._last_cycle_at,
            last_error=self._last_error,
            components={
                name: ComponentStatus(
                    name=status.name,
                    running=status.running,
                    failures=status.failures,
                    last_error=status.last_error,
                    last_started_at=(
                        status.last_started_at
                    ),
                    last_stopped_at=(
                        status.last_stopped_at
                    ),
                )
                for name, status
                in self._components.items()
            },
        )
