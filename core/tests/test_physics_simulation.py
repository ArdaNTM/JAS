"""Features #68/#71: real bounded RK4 integration, no physical actions."""
from __future__ import annotations

import math

import pytest

from aura_core.application.physics_simulation import simulate_mass_spring_damper


BASE = {
    "mass_kg": 1.0,
    "spring_n_per_m": 4.0,
    "damping_n_s_per_m": 0.0,
    "initial_displacement_m": 1.0,
    "initial_velocity_m_s": 0.0,
    "time_step_seconds": 0.005,
    "steps": 400,
}


def test_undamped_oscillator_matches_analytic_cosine_and_conserves_energy():
    result = simulate_mass_spring_damper(**BASE)
    final = result.samples[-1]
    assert final.time_seconds == pytest.approx(2.0)
    assert final.displacement_m == pytest.approx(math.cos(4.0), abs=1e-5)
    assert final.velocity_m_s == pytest.approx(-2.0 * math.sin(4.0), abs=1e-5)
    assert final.mechanical_energy_j == pytest.approx(2.0, abs=1e-6)
    assert not result.physical_validity_verified
    assert not result.hardware_verified
    assert not result.numerical_convergence_verified
    assert not result.tool_execution_performed


def test_damping_lowers_energy_without_activating_hardware():
    parameters = dict(BASE, damping_n_s_per_m=0.4, steps=500)
    result = simulate_mass_spring_damper(**parameters)
    assert result.samples[-1].mechanical_energy_j < result.samples[0].mechanical_energy_j
    assert all(math.isfinite(sample.mechanical_energy_j) for sample in result.samples)


def test_free_motion_when_spring_and_damping_zero():
    parameters = dict(
        BASE, spring_n_per_m=0.0, damping_n_s_per_m=0.0,
        initial_displacement_m=2.0, initial_velocity_m_s=3.0,
        time_step_seconds=0.01, steps=100,
    )
    result = simulate_mass_spring_damper(**parameters)
    assert result.samples[-1].displacement_m == pytest.approx(5.0, abs=1e-8)
    assert result.samples[-1].velocity_m_s == pytest.approx(3.0, abs=1e-8)


def test_decimation_limits_output_and_keeps_last_observation():
    result = simulate_mass_spring_damper(**dict(BASE, steps=1000, output_stride=10))
    assert len(result.samples) == 101
    assert result.samples[-1].time_seconds == pytest.approx(5.0)
    assert result == simulate_mass_spring_damper(**dict(BASE, steps=1000, output_stride=10))


@pytest.mark.parametrize("bad", [
    {"mass_kg": 0}, {"mass_kg": True},
    {"spring_n_per_m": -1}, {"spring_n_per_m": float("inf")},
    {"damping_n_s_per_m": -2}, {"damping_n_s_per_m": float("nan")},
    {"initial_displacement_m": 2e6},
    {"initial_velocity_m_s": float("inf")},
    {"time_step_seconds": 0},
    {"time_step_seconds": True},
    {"steps": True}, {"steps": 0}, {"steps": 20001},
    {"output_stride": False}, {"output_stride": 0},
])
def test_unphysical_and_type_confused_inputs_fail_closed(bad):
    with pytest.raises(ValueError):
        simulate_mass_spring_damper(**dict(BASE, **bad))


def test_numerical_stiffness_duration_and_sample_budgets():
    with pytest.raises(ValueError, match="step too large"):
        simulate_mass_spring_damper(**dict(
            BASE, mass_kg=0.01, spring_n_per_m=10000,
            time_step_seconds=0.005,
        ))
    with pytest.raises(ValueError, match="duration"):
        simulate_mass_spring_damper(**dict(
            BASE, spring_n_per_m=0.0, time_step_seconds=0.1,
            steps=20000, output_stride=100,
        ))
    with pytest.raises(ValueError, match="sample budget"):
        simulate_mass_spring_damper(**dict(
            BASE, spring_n_per_m=0.0, time_step_seconds=0.001,
            steps=10000, output_stride=1,
        ))
