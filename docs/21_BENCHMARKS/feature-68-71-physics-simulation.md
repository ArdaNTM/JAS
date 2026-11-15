# Features #68 and #71 — bounded offline physics / engineering simulation

This PR implements an actual standard-library-only 1D mass–spring–damper
differential-equation integrator:
`m * x'' + c * x' + k * x = 0`. It uses explicit fourth-order Runge–Kutta
(RK4) with bounded step count, conservative stiffness/damping checks, and
bounded output sampling. Tests compare an undamped oscillator against
the analytic cosine solution, verify damped energy loss and a free
particle's linear trajectory.

The result is an **approximate numeric simulation**, not a physical world
measurement, finite-element solver or certified engineering simulator.
Unit conventions are SI: kg, newtons/metre, N·s/m, metres, seconds.

Safety limits: positive finite mass, nonnegative finite stiffness/damping,
bounded initial state, 1..20,000 steps, ≤1,000 simulated seconds,
≤2,001 output samples, finite energy/state and per-step frequency/damping
guardrails. These heuristic guards do not prove stability/convergence.
No hardware, external libraries, network, robots, actuators, sensors,
MCP capabilities or Owner permissions are accessed or inferred.
Every result marks hardware/physical validity/convergence as unverified.

Features #68 (physics simulation) and #71 (engineering simulation) are
PARTIAL; real geometry, calibrated parameters, uncertainty bounds,
independent convergence studies and validated engineering tools remain.
Do not use this toy-model solver for safety-critical design decisions.

Tests: `cd core && uv run pytest -q tests/test_physics_simulation.py`,
all Core Assurance and Final Release Lock required.
