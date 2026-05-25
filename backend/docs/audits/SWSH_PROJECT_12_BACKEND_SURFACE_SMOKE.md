# SWSH Project 12 Backend Surface Smoke

Generated: 2026-05-24T06:45:41.608129+00:00

## Decision

- final_decision: closed_backend_surface_smoke_verified
- db_mutation_performed: False
- execute_rerun_performed: False

## Verified Run IDs

- swsh6: parent_run_id=0dd7683c-4146-4dcd-a04c-6f686bd91417 simulation_summary_id=8f4f4bcf-3d01-454b-851d-d7d295bd2f96
- swsh7: parent_run_id=91e93106-b677-46de-b398-6728aa7842fb simulation_summary_id=1c0724b1-cbe4-4cb9-acb6-23348a3a27d3

## Backend Surfaces Checked

- /explore/page -> get_explore_page_payload
- /explore/rip-statistics/targets -> get_rip_statistics_targets_payload
- /evr/runs/latest -> get_latest_evr_run_snapshot
- latest views: explore_rip_statistics_latest, simulation_latest_by_target, set_pack_score_rankings_latest

## Table Read Coverage

- {"explore_rip_statistics_latest": true, "set_pack_score_rankings_latest": true, "simulation_derived_metrics": true, "simulation_latest_by_target": true, "simulation_percentiles": true, "simulation_pull_summary": true, "simulation_run_summary": true, "simulation_value_distribution_bins": true, "simulation_value_threshold_bins": true}

## Per-Set Status

### swsh6

- latest_run_id_checks: {"explore_rip_statistics_latest": {"matches_expected": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417"}, "latest_snapshot_service": {"matches_expected": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417", "service_error": null}, "simulation_latest_by_target": {"matches_expected": true, "selected_run_id": "0dd7683c-4146-4dcd-a04c-6f686bd91417"}}
- critical_field_status: {"missing_or_null_critical_fields": [], "missing_or_null_rip_fields": [], "summary_source": "latest_snapshot"}
- payload_counts: {"distribution_bins": 50, "percentiles": 7, "pull_summary": 14, "threshold_bins": 18}
- serialization_status: {"explore_latest_row": true, "explore_payload": true, "latest_snapshot": true, "rip_target_row": true, "simulation_latest_row": true}
- slot_schema_compatibility_status: compatible
- warnings: None
- blockers: None
- read_path_gap_blockers: None

### swsh7

- latest_run_id_checks: {"explore_rip_statistics_latest": {"matches_expected": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb"}, "latest_snapshot_service": {"matches_expected": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb", "service_error": null}, "simulation_latest_by_target": {"matches_expected": true, "selected_run_id": "91e93106-b677-46de-b398-6728aa7842fb"}}
- critical_field_status: {"missing_or_null_critical_fields": [], "missing_or_null_rip_fields": [], "summary_source": "latest_snapshot"}
- payload_counts: {"distribution_bins": 50, "percentiles": 7, "pull_summary": 14, "threshold_bins": 18}
- serialization_status: {"explore_latest_row": true, "explore_payload": true, "latest_snapshot": true, "rip_target_row": true, "simulation_latest_row": true}
- slot_schema_compatibility_status: compatible
- warnings: None
- blockers: None
- read_path_gap_blockers: None

## Serialization Status

- payloads_json_serializable: True

## Blockers

- None

## Next Recommended Step

- Proceed to controlled frontend smoke and reporting publication checks using the same persisted run IDs.
