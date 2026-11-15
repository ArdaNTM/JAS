# Features #66 and #69 — bounded scientific evidence triage (partial)

This PR adds two **working offline, read-only** scientific screening slices
under `aura_core.research.scientific_triage`:

1. `screen_studies` performs explicit *literal title/abstract term*
   and year eligibility checks on 1–100 caller-supplied DOI-labelled
   `StudyMetadata` records. It flags exclusions with fixed reason codes
   and SHA-256 fingerprints and produces deterministic DOI ordering.
   It never fetches sources or performs actual full-text/quality appraisal.
2. `compare_material_ranges` compares *caller-asserted* non-overlapping
   numeric ranges for a single explicitly named material property/unit,
   requiring DOI references from supplied study metadata. It reports
   separated/overlapping range relationships without choosing a material.

Inputs are all **untrusted scientific claims**: DOI shape validation does not
verify publisher authenticity, numbers, methods, independent experiments or
physical safety. The module has no public web fetch, network, hardware,
laboratory, citations database connector, tool invocation or Owner policy
authority. Source text never becomes a model instruction or a control-plane
decision. Tests cover real deterministic filtering/comparisons, source
provenance, duplicate/invalid DOIs, Unicode, malformed ranges, NaN/Infinity,
units confusion and unsafe identifiers.

Limits: 100 studies, 400k total metadata bytes, 8 required literal terms,
≤20 material ranges per comparison, strictly named SI-derived property units.
No statistical meta-analysis, uncertainty calibration, actual literature
search or experimental data provenance has been validated.

Feature #66 (literature review) and #69 (materials research) stay
TESTING/PARTIAL pending authorized bibliographic retrieval, full-text
literature appraisal, calibrated materials and human scientific acceptance.

Run `cd core && uv run pytest -q tests/test_scientific_evidence_triage.py`
plus full Core Assurance and Final Release Lock. No new dependencies.
