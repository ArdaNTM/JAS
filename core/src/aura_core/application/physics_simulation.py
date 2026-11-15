"""Bounded offline 1D mass–spring–damper numerical simulation using RK4.

Only a mathematical model is evaluated. No physical lab, sensor, agent,
tool, external provider or permission path is invoked or verified.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MotionSample:
    time_seconds: float
    displacement_m: float
    velocity_m_s: float
    mechanical_energy_j: float


@dataclass(frozen=True, slots=True)
class PhysicsSimulation:
    model: str
    integrator: str
    steps: int
    time_step_seconds: float
    samples: tuple[MotionSample, ...]
    hardware_verified: bool = False
    physical_validity_verified: bool = False
    numerical_convergence_verified: bool = False
    tool_execution_performed: bool = False


def _bounded(value: float, name: str, *, minimum: float, maximum: float) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"invalid {name}")
    return float(value)


def simulate_mass_spring_damper(
    *,
    mass_kg: float,
    spring_n_per_m: float,
    damping_n_s_per_m: float,
    initial_displacement_m: float,
    initial_velocity_m_s: float,
    time_step_seconds: float,
    steps: int,
    output_stride: int = 1,
) -> PhysicsSimulation:
    """Integrate m*x'' + c*x' + k*x = 0 with a conservative RK4 step budget.

    SI units assumed. The stability guards are conservative numeric
    heuristics; they are NOT an independent convergence/accuracy proof.
    """
    m = _bounded(mass_kg, "mass_kg", minimum=1e-6, maximum=1e9)
    k = _bounded(spring_n_per_m, "spring_n_per_m", minimum=0, maximum=1e9)
    c = _bounded(damping_n_s_per_m, "damping_n_s_per_m", minimum=0, maximum=1e9)
    x = _bounded(
        initial_displacement_m, "initial_displacement_m",
        minimum=-1e6, maximum=1e6,
    )
    v = _bounded(
        initial_velocity_m_s, "initial_velocity_m_s",
        minimum=-1e6, maximum=1e6,
    )
    dt = _bounded(
        time_step_seconds, "time_step_seconds", minimum=1e-7, maximum=0.5,
    )
    if type(steps) is not int or not 1 <= steps <= 20000:
        raise ValueError("steps must be 1..20000")
    if type(output_stride) is not int or not 1 <= output_stride <= 20000:
        raise ValueError("output_stride must be 1..20000")
    if steps * dt > 1000:
        raise ValueError("total simulation duration exceeds budget")
    if 1 + steps // output_stride + (1 if steps % output_stride else 0) > 2001:
        raise ValueError("output sample budget exceeded")
    if dt * math.sqrt(k / m) > 0.5 or dt * c / m > 0.5:
        raise ValueError("simulation step too large for model stiffness/damping")

    def derivative(position: float, velocity: float) -> tuple[float, float]:
        return velocity, -(k * position + c * velocity) / m

    def record(index: int) -> MotionSample:
        energy = 0.5 * m * v * v + 0.5 * k * x * x
        if not all(math.isfinite(z) for z in (x, v, energy)):
            raise ValueError("numerical overflow during simulation")
        if abs(x) > 1e12 or abs(v) > 1e12:
            raise ValueError("numerical state exceeds safe bound")
        return MotionSample(
            time_seconds=round(index * dt, 12),
            displacement_m=x,
            velocity_m_s=v,
            mechanical_energy_j=energy,
        )

    output: list[MotionSample] = [record(0)]
    for index in range(1, steps + 1):
        k1x, k1v = derivative(x, v)
        k2x, k2v = derivative(
            x + 0.5 * dt * k1x, v + 0.5 * dt * k1v,
        )
        k3x, k3v = derivative(
            x + 0.5 * dt * k2x, v + 0.5 * dt * k2v,
        )
        k4x, k4v = derivative(
            x + dt * k3x, v + dt * k3v,
        )
        x += dt * (k1x + 2 * k2x + 2 * k3x + k4x) / 6
        v += dt * (k1v + 2 * k2v + 2 * k3v + k4v) / 6
        if index % output_stride == 0 or index == steps:
            output.append(record(index))
    return PhysicsSimulation(
        model="1d.mass_spring_damper",
        integrator="RK4",
        steps=steps,
        time_step_seconds=dt,
        samples=tuple(output),
    )
