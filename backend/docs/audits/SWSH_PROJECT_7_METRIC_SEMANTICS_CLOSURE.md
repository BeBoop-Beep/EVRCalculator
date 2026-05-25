# SWSH Project 7 Metric Semantics Closure

Final decision: closed_metric_semantics_aligned_persistence_ready

## Outcome

- Production job code changed: yes
- Intended/persisted payload semantics changed: yes
- Exact ROI formula used: (expected_value - cost) / cost
- Explicit value/cost ratio field retained: value_to_cost_ratio
- Alias retained for clarity in audit output: legacy_value_cost_ratio
- roi now means formula ROI: yes
- Probability-to-beat-pack-cost semantic consistency: pass
- Dry-run zero writes: pass (actual_writes_performed_total = 0)
- Strict DB input: pass
- Scope remained swsh6/swsh7 only: yes
- SV/Mega remained unchanged: yes
- Other SWSH remained unchanged: yes
- Critical warning flags triggered: no
- Persistence readiness status: ready

## What Changed

1. backend/jobs/evr_runner.py
- Cost-comparison payload now exposes explicit semantics fields:
  - expected_value
  - cost
  - value_to_cost_ratio
  - roi
  - roi_formula
  - metric_semantics_version
- roi now uses formula ROI.
- value_to_cost_ratio preserves the legacy ratio explicitly.

2. backend/calculations/packCalcsRefractored/otherCalculations.py
- opening_pack_roi switched to formula ROI.
- value_to_cost_ratio added explicitly.
- opening_pack_roi_formula and metric_semantics_version added.

3. backend/db/services/calculation_run_persistence_service.py
- Persistence contract hardened.
- Comparison payloads now require explicit semantics fields before mapping/persisting.
- Pack summary payload now requires explicit semantics fields.

4. backend/scripts/audit_swsh_production_job_dry_run.py
- Dry-run now validates both:
  - roi consistency with formula ROI
  - value_to_cost_ratio consistency with expected_value/cost
- Output contract now carries explicit semantics fields and version.
- Critical warning flags include value_to_cost_ratio semantic mismatch.

## Dry-Run Evidence

Command executed:
- python -m backend.scripts.audit_swsh_production_job_dry_run --strict-db-input --pack-count 100000 --dry-run

Observed from logs/audits/swsh_production_job_dry_run.json:
- safety_assertions.passed: true
- actual_writes_performed_total: 0
- strict_db_input_passed (both sets): true
- selected_simulation_engine (both sets): slot_schema
- monte_carlo_v2_bypassed (both sets): true
- production_probability_equals_draft (both sets): true
- roi_consistency_passed (both sets): true
- value_to_cost_ratio_consistency_passed (both sets): true
- probability_to_beat_pack_cost_consistency_passed (both sets): true
- no critical warning flags triggered

Set-level semantics snapshot:
- swsh6: roi=-0.6882188949771689, value_to_cost_ratio=0.3117811050228311
- swsh7: roi=-0.8495661556912342, value_to_cost_ratio=0.1504338443087658

## Test Validation

Focused and guardrail tests were run and passed, including:

- backend/tests/unit/scripts/test_audit_swsh_production_job_dry_run.py
- backend/tests/unit/scripts/test_audit_swsh_production_runtime_smoke.py
- backend/tests/unit/scripts/test_audit_swsh_draft_empirical_outputs.py
- backend/tests/unit/scripts/test_audit_swsh_slot_schema_readiness.py
- backend/tests/unit/simulations/test_swsh_draft_empirical_probability_validation.py
- backend/tests/unit/simulations/test_slot_schema_simulation_math_validation.py
- backend/tests/unit/simulations/test_chilling_reign_bucket_classification.py
- backend/tests/unit/simulations/test_evolving_skies_bucket_classification.py
- backend/tests/unit/simulations/test_evr_simulator_routing.py
- backend/tests/unit/simulations/test_sv_mega_v2_regression_wall.py

Note:
- The requested bucket-classification paths under backend/tests/unit/tcg/pokemon/swordAndShieldEra/ are not present in this workspace; equivalent existing tests under backend/tests/unit/simulations/ were executed instead.

## Persistence Decision

This prompt does not run real persistence and does not mutate the DB.

Given explicit metric naming, formula-ROI alignment, hardened persistence input contract, zero-write dry-run, strict DB input pass, and all guardrails passing, Project 7 closes as:

closed_metric_semantics_aligned_persistence_ready
