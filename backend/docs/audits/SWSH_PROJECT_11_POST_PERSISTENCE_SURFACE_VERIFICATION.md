# SWSH Project 11 Post-Persistence Surface Verification

Generated: 2026-05-24T05:21:06.959800+00:00

## Decision

- final_decision: closed_post_persistence_surface_verified
- db_mutation_performed: False
- execute_rerun_performed: False
- source_project_10_closure_artifact: logs/audits/swsh_project_10_execute_closure_repaired.json

## Verified IDs

- swsh6: parent_run_id=0dd7683c-4146-4dcd-a04c-6f686bd91417 simulation_summary_id=8f4f4bcf-3d01-454b-851d-d7d295bd2f96
- swsh7: parent_run_id=91e93106-b677-46de-b398-6728aa7842fb simulation_summary_id=1c0724b1-cbe4-4cb9-acb6-23348a3a27d3

## Per-Set Verification

### swsh6

- calculation_runs_exists: True
- target_identity_ok: True
- calculation_config_link_exists: True
- simulation_run_summary_exists: True
- summary_belongs_to_expected_run: True
- latest_selected_by_all_primary_surfaces: True
- table_counts_by_run: {"calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 233, "simulation_percentiles": 7, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_state_counts": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- read_surface_visibility: {"calculation_runs_latest_lookup": {"row_found": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417", "selects_verified_run": true}, "explore_rip_statistics_latest": {"missing_required_fields": [], "row_found": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417", "selects_verified_run": true}, "set_pack_score_rankings_latest": {"row_found_for_verified_run": true}, "simulation_latest_by_target": {"row_found": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417", "selects_verified_run": true}, "target_resolution": {"requested_set_key": "swsh6", "resolution_source": "pokemon_api_set_id", "resolved_target_id": "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890"}}
- downstream_readiness: {"derived_metrics_present": true, "formula_roi_present": true, "metric_semantics_version_present": true, "metric_semantics_version_value": "derived_intelligence_v1", "percentile_rows_present": true, "probability_to_beat_pack_cost_present": true, "pull_summaries_present": true, "threshold_bins_present": true, "value_distribution_bins_present": true, "value_to_cost_ratio_present": true}
- warnings: None
- blockers: None
- read_surface_gap_blockers: None

### swsh7

- calculation_runs_exists: True
- target_identity_ok: True
- calculation_config_link_exists: True
- simulation_run_summary_exists: True
- summary_belongs_to_expected_run: True
- latest_selected_by_all_primary_surfaces: True
- table_counts_by_run: {"calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 237, "simulation_percentiles": 7, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_state_counts": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- read_surface_visibility: {"calculation_runs_latest_lookup": {"row_found": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb", "selects_verified_run": true}, "explore_rip_statistics_latest": {"missing_required_fields": [], "row_found": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb", "selects_verified_run": true}, "set_pack_score_rankings_latest": {"row_found_for_verified_run": true}, "simulation_latest_by_target": {"row_found": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb", "selects_verified_run": true}, "target_resolution": {"requested_set_key": "swsh7", "resolution_source": "pokemon_api_set_id", "resolved_target_id": "93212749-ce0e-498e-975e-7d947a3448ce"}}
- downstream_readiness: {"derived_metrics_present": true, "formula_roi_present": true, "metric_semantics_version_present": true, "metric_semantics_version_value": "derived_intelligence_v1", "percentile_rows_present": true, "probability_to_beat_pack_cost_present": true, "pull_summaries_present": true, "threshold_bins_present": true, "value_distribution_bins_present": true, "value_to_cost_ratio_present": true}
- warnings: None
- blockers: None
- read_surface_gap_blockers: None

## Aggregated Status

- latest_read_surface_visibility_status: verified_latest_selected
- newly_persisted_runs_selected_as_latest: True
- downstream_readiness_status: ready
- no_unexpected_extra_write_table_categories_required_for_current_read_surfaces: True

## Blockers

- None

## Next Recommended Step

- No DB action required; proceed with normal downstream read/API validation in environment-specific smoke checks.
