# SWSH Project 14 Rollout Closure Audit

Generated: 2026-05-24T17:03:17Z

## Decision

- final_decision: closed_swsh6_swsh7_rollout_complete_with_non_blocking_cleanup
- db_mutation_performed: false
- execute_rerun_performed: false

## Persisted Run IDs

- swsh6: parent_run_id=0dd7683c-4146-4dcd-a04c-6f686bd91417, simulation_summary_id=8f4f4bcf-3d01-454b-851d-d7d295bd2f96
- swsh7: parent_run_id=91e93106-b677-46de-b398-6728aa7842fb, simulation_summary_id=1c0724b1-cbe4-4cb9-acb6-23348a3a27d3

## Project Closure Matrix (6-13)

- Project 6: closed_runtime_validated_persistence_blocked_on_metric_semantics
- Project 7: closed_metric_semantics_aligned_persistence_ready
- Project 8: closed_controlled_persistence_preflight_ready_for_explicit_execute
- Project 9: implemented and validated double-confirm execute safety (from project sequence state)
- Project 9.1: implemented and validated double-confirm execute safety (from project sequence state)
- Project 9.2: implemented and validated double-confirm execute safety (from project sequence state)
- Project 10: controlled persistence executed
- Project 10.5: closed_controlled_persistence_executed_and_verified
- Project 11: closed_post_persistence_surface_verified
- Project 12.1: closed_backend_surface_smoke_verified
- Project 13: closed_evr_latest_api_smoke_verified

Notes:
- No standalone Project 13 markdown/json closure artifact was found during this audit.
- Project 13 status is supported by route-level test coverage and focused pytest re-run.

## Required Final Status Confirmation

- swsh6 runtime slot_schema: confirmed
  - Evidence: backend/constants/tcg/pokemon/swordAndShieldEra/chillingReign.py defines SIMULATION_ENGINE='slot_schema' and SLOT_SCHEMA_RUNTIME_ENABLED=True.
- swsh7 runtime slot_schema: confirmed
  - Evidence: backend/constants/tcg/pokemon/swordAndShieldEra/evolvingSkies.py defines SIMULATION_ENGINE='slot_schema' and SLOT_SCHEMA_RUNTIME_ENABLED=True.
- metric semantics formula ROI: confirmed
  - Evidence: backend/jobs/evr_runner.py uses roi_formula='(expected_value - cost) / cost'; backend/calculations/packCalcsRefractored/otherCalculations.py computes ROI as net/cost; Project 7 closure artifact reports semantics pass.
- value_to_cost_ratio explicit field: confirmed
  - Evidence: backend/jobs/evr_runner.py and backend/db/services/calculation_run_persistence_service.py require/persist explicit value_to_cost_ratio.
- controlled persistence completed: confirmed
  - Evidence: logs/audits/swsh_project_10_execute_closure_repaired.json final_decision=closed_controlled_persistence_executed_and_verified.
- Project 10.3 persisted rows verified: confirmed
  - Evidence: Project 10.5 repair script and artifact verify calculation_runs + simulation_run_summary rows for Project 10.3 identifiers.
- Project 11 latest/read-surface visibility: confirmed
  - Evidence: logs/audits/swsh_project_11_post_persistence_surface_verification.json latest_read_surface_visibility_status=verified_latest_selected.
- Project 12 backend service surfaces: confirmed
  - Evidence: logs/audits/swsh_project_12_backend_surface_smoke.json final_decision=closed_backend_surface_smoke_verified.
- Project 13 API route contract: confirmed
  - Evidence: backend/tests/unit/api/test_evr_latest_run_route.py plus focused pytest pass.

## Changed-File Inventory

### Production code changes

- backend/calculations/packCalcsRefractored/initializeCalculations.py
- backend/calculations/packCalcsRefractored/otherCalculations.py
- backend/constants/tcg/pokemon/sharedBaseConfig.py
- backend/constants/tcg/pokemon/sunAndMoonEra/baseConfig.py
- backend/constants/tcg/pokemon/swordAndShieldEra/baseConfig.py
- backend/constants/tcg/pokemon/swordAndShieldEra/chillingReign.py
- backend/constants/tcg/pokemon/swordAndShieldEra/evolvingSkies.py
- backend/db/services/calculation_run_persistence_service.py
- backend/db/services/calculation_run_query_service.py
- backend/db/services/evr_input_repository.py
- backend/db/services/evr_input_transformer.py
- backend/jobs/evr_runner.py
- backend/simulations/evrSimulator.py
- backend/simulations/slotSchemaContract.py
- backend/simulations/slotSchemaOutcomeResolver.py
- backend/simulations/slotSchemaSimulator.py

### Audit scripts

- backend/scripts/audit_chilling_reign_supabase_labels.py
- backend/scripts/audit_swsh_backend_surface_smoke.py
- backend/scripts/audit_swsh_controlled_persistence_preflight.py
- backend/scripts/audit_swsh_draft_empirical_outputs.py
- backend/scripts/audit_swsh_post_persistence_surface_verification.py
- backend/scripts/audit_swsh_production_job_dry_run.py
- backend/scripts/audit_swsh_production_runtime_smoke.py
- backend/scripts/audit_swsh_slot_schema_readiness.py

### Repair scripts

- backend/scripts/repair_swsh_controlled_persistence_execute_closure.py

### Tests

- backend/tests/unit/api/test_evr_latest_run_route.py
- backend/tests/unit/db/repositories/test_calculation_runs_repository.py
- backend/tests/unit/db/services/test_calculation_run_persistence_service.py
- backend/tests/unit/db/services/test_calculation_run_query_service.py
- backend/tests/unit/jobs/test_evr_runner_output_metrics.py
- backend/tests/unit/scripts/test_audit_swsh_backend_surface_smoke.py
- backend/tests/unit/scripts/test_audit_swsh_controlled_persistence_preflight.py
- backend/tests/unit/scripts/test_audit_swsh_draft_empirical_outputs.py
- backend/tests/unit/scripts/test_audit_swsh_post_persistence_surface_verification.py
- backend/tests/unit/scripts/test_audit_swsh_production_job_dry_run.py
- backend/tests/unit/scripts/test_audit_swsh_production_runtime_smoke.py
- backend/tests/unit/scripts/test_audit_swsh_slot_schema_readiness.py
- backend/tests/unit/scripts/test_repair_swsh_controlled_persistence_execute_closure.py
- backend/tests/unit/simulations/test_chilling_reign_bucket_classification.py
- backend/tests/unit/simulations/test_chilling_reign_bucket_normalization.py
- backend/tests/unit/simulations/test_evolving_skies_bucket_classification.py
- backend/tests/unit/simulations/test_evolving_skies_slot_schema_audit.py
- backend/tests/unit/simulations/test_evr_simulator_routing.py
- backend/tests/unit/simulations/test_pre_sv_base_pack_structure_configs.py
- backend/tests/unit/simulations/test_slot_schema_contract.py
- backend/tests/unit/simulations/test_slot_schema_outcome_resolver.py
- backend/tests/unit/simulations/test_slot_schema_pilot_runtime.py
- backend/tests/unit/simulations/test_slot_schema_simulation_math_validation.py
- backend/tests/unit/simulations/test_slot_schema_simulator.py
- backend/tests/unit/simulations/test_sv_mega_v2_regression_wall.py
- backend/tests/unit/simulations/test_swsh_draft_empirical_probability_validation.py

### Generated artifacts/logs/docs

- backend/docs/CHILLING_REIGN_OUTCOME_POOL_MAPPING_AUDIT.md
- backend/docs/CHILLING_REIGN_SUPABASE_LABEL_AUDIT.md
- backend/docs/EVOLVING_SKIES_SLOT_SCHEMA_PILOT_AUDIT.md
- backend/docs/audits/CHILLING_REIGN_BUCKET_CLASSIFICATION_LEDGER.md
- backend/docs/audits/EVOLVING_SKIES_BUCKET_CLASSIFICATION_LEDGER.md
- backend/docs/audits/SWSH_CONTROLLED_PERSISTENCE_PREFLIGHT.md
- backend/docs/audits/SWSH_DRAFT_EMPIRICAL_OUTPUT_INSPECTION.md
- backend/docs/audits/SWSH_PRODUCTION_JOB_DRY_RUN.md
- backend/docs/audits/SWSH_PRODUCTION_RUNTIME_SMOKE.md
- backend/docs/audits/SWSH_PROJECT_6_CLOSURE.md
- backend/docs/audits/SWSH_PROJECT_7_METRIC_SEMANTICS_CLOSURE.md
- backend/docs/audits/SWSH_PROJECT_8_CONTROLLED_PERSISTENCE_GATE_CLOSURE.md
- backend/docs/audits/SWSH_PROJECT_10_EXECUTE_CLOSURE_REPAIRED.md
- backend/docs/audits/SWSH_PROJECT_11_POST_PERSISTENCE_SURFACE_VERIFICATION.md
- backend/docs/audits/SWSH_PROJECT_12_BACKEND_SURFACE_SMOKE.md
- backend/docs/audits/SWSH_SLOT_SCHEMA_READINESS_MATRIX.md
- logs/audits/chilling_reign_supabase_label_audit_swsh6.json
- logs/audits/swsh_controlled_persistence_preflight.json
- logs/audits/swsh_draft_empirical_output_inspection.json
- logs/audits/swsh_production_job_dry_run.json
- logs/audits/swsh_production_runtime_smoke.json
- logs/audits/swsh_project_6_closure.json
- logs/audits/swsh_project_7_metric_semantics_closure.json
- logs/audits/swsh_project_8_controlled_persistence_gate_closure.json
- logs/audits/swsh_project_10_execute_closure_repaired.json
- logs/audits/swsh_project_11_post_persistence_surface_verification.json
- logs/audits/swsh_project_12_backend_surface_smoke.json
- logs/audits/swsh_slot_schema_readiness_matrix.json

### Unrelated/pre-existing changes detectable

- logs/run_simulations.log
- logs/task_scheduler_debug.log

## Production Change Summary

- Slot-schema runtime for swsh6/swsh7 is intentionally enabled and enforced through the slot contract path.
- Formula ROI semantics are now explicit and aligned, with value_to_cost_ratio retained as a separately named metric.
- Persistence input contract enforces semantic field presence before writes.
- Latest-run read service supports robust set target resolution and normalized snapshot output.

## Remaining Blockers

- None.

## Non-Blocking Cleanup Recommendations

1. Route-test naming hygiene: rename SWSH6_SET_UUID in backend/tests/unit/api/test_evr_latest_run_route.py to reflect run-id-shaped fixture semantics.
2. Artifact naming hygiene: optionally separate Project 8 preflight artifact naming from Project 10 execute/closure naming for cleaner chronology.
3. Repair tooling lifecycle: decide whether repair_swsh_controlled_persistence_execute_closure.py remains permanent or is archived as one-off tooling after governance sign-off.
4. Historical duplicate records governance: keep Project 10.1/10.3 partial/successful duplicates as audit history unless a separate approved DB-governance prompt authorizes cleanup.
5. Documentation parity: optionally add a dedicated Project 13 closure markdown/json artifact for symmetry with Projects 6-12.

## Tests/Smokes Run In Project 14 Audit

- Command:
  - d:/EVRCalculator/backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_calculation_run_query_service.py backend/tests/unit/scripts/test_audit_swsh_backend_surface_smoke.py backend/tests/unit/api/test_evr_latest_run_route.py -q
- Result:
  - 18 passed, 0 failed, 2 warnings

## Next Recommended Phase

- project_15_non_blocking_rollout_hygiene_documentation_and_governance_followups
