# SWSH Controlled Persistence Preflight

Generated: 2026-05-28T21:42:46.719320+00:00

Default run mode is dry-run with no DB writes.

## Global

- Run mode: execute
- Strict DB input: True
- Actual writes performed total: 677
- Intended writes captured total: 0
- Safety assertions passed: True

## Chilling Reign (swsh6)

- canonical_key: chillingReign
- run mode: execute
- selected engine: slot_schema
- pack_count: 2000
- estimated_pack_price: 11.14
- pack price source/status: unreported / unreported
- average_pack_value: 3.407355
- median_pack_value: 1.58
- formula ROI: -0.6941333034111311
- value_to_cost_ratio: 0.3058666965888689
- probability_to_beat_pack_cost: 0.0235
- P05/P95/P99: 1.26 / 5.101999999999998 / 16.754199999999987
- metric_semantics_version: formula_roi_v2
- persistence payload validators passed: True
- intended persistence targets: 
- intended write counts: {}
- expected parent run payload keys: config_hash, config_id, run_id, snapshot_count
- expected simulation output payload keys: derived_metric_count, distribution_bin_count, percentile_count, pull_summary_count, run_summary_id, state_count, threshold_bin_count
- readiness_status: ready

### Triggered Warning Flags

- None

## Evolving Skies (swsh7)

- canonical_key: evolvingSkies
- run mode: execute
- selected engine: slot_schema
- pack_count: 2000
- estimated_pack_price: 45.81
- pack price source/status: unreported / unreported
- average_pack_value: 6.80188
- median_pack_value: 1.24
- formula ROI: -0.8515197555118971
- value_to_cost_ratio: 0.148480244488103
- probability_to_beat_pack_cost: 0.0145
- P05/P95/P99: 0.85 / 13.382499999999997 / 73.76079999999999
- metric_semantics_version: formula_roi_v2
- persistence payload validators passed: True
- intended persistence targets: 
- intended write counts: {}
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
