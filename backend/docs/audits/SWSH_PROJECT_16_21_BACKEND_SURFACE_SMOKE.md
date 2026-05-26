# SWSH Project 12 Backend Surface Smoke

Generated: 2026-05-26T15:35:56.850886+00:00

## Decision

- final_decision: closed_backend_surface_smoke_verified
- db_mutation_performed: False
- execute_rerun_performed: False

## Verified Run IDs

- swsh6: parent_run_id=e76e7463-7ad3-4d2e-a1bb-a589ab066e41 simulation_summary_id=f77304a9-f489-4a32-b2e1-c9d58f3f9d1b
- swsh7: parent_run_id=035c440c-772c-4f47-a240-38af664bb3df simulation_summary_id=4d591a71-d187-4c7a-b960-7ed20ab5a6ab

## Backend Surfaces Checked

- /explore/page -> get_explore_page_payload
- /explore/rip-statistics/targets -> get_rip_statistics_targets_payload
- /evr/runs/latest -> get_latest_evr_run_snapshot
- latest views: explore_rip_statistics_latest, simulation_latest_by_target, set_pack_score_rankings_latest

## Table Read Coverage

- {"explore_rip_statistics_latest": true, "set_pack_score_rankings_latest": true, "simulation_derived_metrics": true, "simulation_latest_by_target": true, "simulation_percentiles": true, "simulation_pull_summary": true, "simulation_run_summary": true, "simulation_value_distribution_bins": true, "simulation_value_threshold_bins": true}

## Per-Set Status

### swsh6

- latest_run_id_checks: {"explore_rip_statistics_latest": {"matches_expected": true, "selected_run_id": "e76e7463-7ad3-4d2e-a1bb-a589ab066e41"}, "latest_snapshot_service": {"matches_expected": true, "selected_run_id": "e76e7463-7ad3-4d2e-a1bb-a589ab066e41", "service_error": null}, "simulation_latest_by_target": {"matches_expected": true, "selected_run_id": "e76e7463-7ad3-4d2e-a1bb-a589ab066e41"}}
- critical_field_status: {"missing_or_null_critical_fields": [], "missing_or_null_rip_fields": [], "summary_source": "latest_snapshot"}
- payload_counts: {"distribution_bins": 50, "percentiles": 7, "pull_summary": 13, "threshold_bins": 18}
- serialization_status: {"explore_latest_row": true, "explore_payload": true, "latest_snapshot": true, "rip_target_row": true, "simulation_latest_row": true}
- slot_schema_compatibility_status: compatible
- warnings: None
- blockers: None
- read_path_gap_blockers: None

### swsh7

- latest_run_id_checks: {"explore_rip_statistics_latest": {"matches_expected": true, "selected_run_id": "035c440c-772c-4f47-a240-38af664bb3df"}, "latest_snapshot_service": {"matches_expected": true, "selected_run_id": "035c440c-772c-4f47-a240-38af664bb3df", "service_error": null}, "simulation_latest_by_target": {"matches_expected": true, "selected_run_id": "035c440c-772c-4f47-a240-38af664bb3df"}}
- critical_field_status: {"missing_or_null_critical_fields": [], "missing_or_null_rip_fields": [], "summary_source": "latest_snapshot"}
- payload_counts: {"distribution_bins": 50, "percentiles": 7, "pull_summary": 12, "threshold_bins": 18}
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
