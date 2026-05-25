# SWSH Controlled Persistence Preflight

Generated: 2026-05-24T04:53:22.584767+00:00

Default run mode is dry-run with no DB writes.

## Global

- Run mode: dry_run
- Strict DB input: True
- Actual writes performed total: 0
- Intended writes captured total: 660
- Safety assertions passed: True

## Chilling Reign (swsh6)

- canonical_key: chillingReign
- run mode: dry_run
- selected engine: slot_schema
- pack_count: 100000
- estimated_pack_price: 10.95
- pack price source/status: unreported / unreported
- average_pack_value: 3.4012716
- median_pack_value: 1.61
- formula ROI: -0.6893815890410959
- value_to_cost_ratio: 0.31061841095890413
- probability_to_beat_pack_cost: 0.0304
- P05/P95/P99: 1.3 / 6.170499999999883 / 31.65009999999995
- metric_semantics_version: formula_roi_v2
- persistence payload validators passed: True
- intended persistence targets: calculation_price_snapshots, calculation_runs, simulation_derived_metrics, simulation_input_cards, simulation_percentiles, simulation_pull_summary, simulation_run_summary, simulation_state_counts, simulation_value_distribution_bins, simulation_value_threshold_bins
- intended write counts: {"calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 233, "simulation_percentiles": 7, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_state_counts": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- expected parent run payload keys: config_hash, config_id, run_id, snapshot_count
- expected simulation output payload keys: derived_metric_count, distribution_bin_count, percentile_count, pull_summary_count, run_summary_id, state_count, threshold_bin_count
- readiness_status: ready

### Triggered Warning Flags

- None

## Evolving Skies (swsh7)

- canonical_key: evolvingSkies
- run mode: dry_run
- selected engine: slot_schema
- pack_count: 100000
- estimated_pack_price: 45.86
- pack price source/status: unreported / unreported
- average_pack_value: 7.0348813
- median_pack_value: 1.2
- formula ROI: -0.8466009310946359
- value_to_cost_ratio: 0.15339906890536417
- probability_to_beat_pack_cost: 0.01397
- P05/P95/P99: 0.86 / 12.389999999999999 / 139.65009999999992
- metric_semantics_version: formula_roi_v2
- persistence payload validators passed: True
- intended persistence targets: calculation_price_snapshots, calculation_runs, simulation_derived_metrics, simulation_input_cards, simulation_percentiles, simulation_pull_summary, simulation_run_summary, simulation_state_counts, simulation_value_distribution_bins, simulation_value_threshold_bins
- intended write counts: {"calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 237, "simulation_percentiles": 7, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_state_counts": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- expected parent run payload keys: config_hash, config_id, run_id, snapshot_count
- expected simulation output payload keys: derived_metric_count, distribution_bin_count, percentile_count, pull_summary_count, run_summary_id, state_count, threshold_bin_count
- readiness_status: ready

### Triggered Warning Flags

- None

## Write Operation Classification

- calculation_configs: get_or_create
- calculation_price_snapshots: insert_only
- calculation_runs: insert_only
- simulation_derived_metrics: insert_only
- simulation_etb_summary: insert_only
- simulation_input_cards: insert_only
- simulation_percentiles: insert_only
- simulation_pull_summary: insert_only
- simulation_run_summary: insert_only
- simulation_state_counts: insert_only
- simulation_value_distribution_bins: insert_only
- simulation_value_threshold_bins: insert_only
