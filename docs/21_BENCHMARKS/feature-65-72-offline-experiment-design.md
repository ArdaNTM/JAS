# Features #65 and #72 — offline hypothesis wording and experiment design

AURA now has a small standard-library-only **non-executing** study design
component in `aura_core.application.experiment_design`. It validates
user-provided independent/dependent variables, control and treatment
conditions, and an assumed direction; produces explicit null/alternative
wording; and generates deterministic, balanced **simulated** allocation
labels with a reproducible seed and a plan content fingerprint.

This is *not autonomous scientific discovery*. H0/H1 templates come from
explicit user assumptions, not literature or measured results. Group
assignment uses `random.Random` for reproducibility rather than a
cryptographic random number generator. No actual participant identities
are enrolled, no clinical/ethics approval is obtained and no lab, robot,
sensor, instrument, cloud service, file or MCP Gateway tool is touched.

Safety and limits: no longer than 120 characters per study label,
4..2000 simulated units, unsigned 32-bit seed, no type-confused numeric
parameters, no claim of causal validity, statistical power, blinding or
successful experimentation. Output explicitly has
`laboratory_execution_performed=False`,
`human_subjects_approved=False`,
`scientific_validity_verified=False`, `authorization_checked=False`.

Both feature #65 (hypothesis generation) and #72 (experiment planning)
remain **TESTING/PARTIAL**. Scientific review, power calculations,
instrument calibration, data collection and Owner-authorized external
execution are separate dependencies.

Tests: `cd core && uv run pytest -q tests/test_experiment_design.py`,
full Core Assurance and Final Release Lock. No new runtime dependencies.
