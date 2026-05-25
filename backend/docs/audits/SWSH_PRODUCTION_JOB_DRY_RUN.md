# SWSH Production Job Dry-Run

Generated: 2026-05-24T00:51:34.826692+00:00

Real production EVR job path dry-run for swsh6/swsh7 with all writes intercepted in-memory.

## Global Safety

- Dry run enforced: True
- Actual writes performed total: 0
- Intended writes captured total: 646
- Strict DB input: True
- Runtime approval input status: strict_db_input_passed

## Chilling Reign (swsh6)

- set_key: chillingReign
- selected simulation engine: slot_schema
- Monte Carlo V2 bypassed: True
- slot_schema runtime used: True
- DB input source: db_evr_input_preparation_service
- pack count: 100000
- estimated pack price: 10.95
- value to cost ratio: 0.3117811050228311
- average pack value: 3.4140031
- median pack value: 1.61
- metric semantics version: formula_roi_v2
- ROI formula: (average_pack_value - estimated_pack_price) / estimated_pack_price
- formula ROI: -0.6882188949771689
- reported ROI: -0.6882188949771689
- legacy value/cost ratio: 0.3117811050228311
- ROI absolute delta: 0.0
- ROI consistency passed: True
- value_to_cost_ratio consistency passed: True
- value_to_cost_ratio absolute delta: 0.0
- probability_to_beat_pack_cost from values: 0.03166
- reported probability_to_beat_pack_cost: 0.03166
- probability_to_beat_pack_cost absolute delta: 0.0
- probability_to_beat_pack_cost consistency passed: True
- semantic status: {"probability_to_beat_pack_cost": "value_derived_probability_aligned", "roi": "formula_roi_aligned", "value_to_cost_ratio": "value_to_cost_ratio_aligned"}
- P05/P95/P99: 1.3 / 6.319999999999999 / 31.660099999999947
- output payload keys: booster_box_value_vs_cost_comparison, booster_box_value_vs_cost_comparison_by_variant, calculated_expected_value_per_pack, canonical_key, derived, etb_metrics, etb_value_vs_cost_comparison, etb_value_vs_cost_comparison_by_variant, input_source, pack_price, pack_value_vs_cost_comparison, persisted, run_metadata, set_name, total_ev
- intended persistence targets: calculation_configs, calculation_price_snapshots, calculation_runs, simulation_derived_metrics, simulation_input_cards, simulation_pull_summary, simulation_run_summary, simulation_value_distribution_bins, simulation_value_threshold_bins
- intended write counts: {"calculation_configs": 1, "calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 233, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- writes actually performed: 0

### Warning Flags

- No warning flags triggered.

## Evolving Skies (swsh7)

- set_key: evolvingSkies
- selected simulation engine: slot_schema
- Monte Carlo V2 bypassed: True
- slot_schema runtime used: True
- DB input source: db_evr_input_preparation_service
- pack count: 100000
- estimated pack price: 45.86
- value to cost ratio: 0.1504338443087658
- average pack value: 6.8988961
- median pack value: 1.2
- metric semantics version: formula_roi_v2
- ROI formula: (average_pack_value - estimated_pack_price) / estimated_pack_price
- formula ROI: -0.8495661556912342
- reported ROI: -0.8495661556912342
- legacy value/cost ratio: 0.1504338443087658
- ROI absolute delta: 0.0
- ROI consistency passed: True
- value_to_cost_ratio consistency passed: True
- value_to_cost_ratio absolute delta: 0.0
- probability_to_beat_pack_cost from values: 0.01343
- reported probability_to_beat_pack_cost: 0.01343
- probability_to_beat_pack_cost absolute delta: 0.0
- probability_to_beat_pack_cost consistency passed: True
- semantic status: {"probability_to_beat_pack_cost": "value_derived_probability_aligned", "roi": "formula_roi_aligned", "value_to_cost_ratio": "value_to_cost_ratio_aligned"}
- P05/P95/P99: 0.8595000000000073 / 12.340499999999883 / 139.54
- output payload keys: booster_box_value_vs_cost_comparison, booster_box_value_vs_cost_comparison_by_variant, calculated_expected_value_per_pack, canonical_key, derived, etb_metrics, etb_value_vs_cost_comparison, etb_value_vs_cost_comparison_by_variant, input_source, pack_price, pack_value_vs_cost_comparison, persisted, run_metadata, set_name, total_ev
- intended persistence targets: calculation_configs, calculation_price_snapshots, calculation_runs, simulation_derived_metrics, simulation_input_cards, simulation_pull_summary, simulation_run_summary, simulation_value_distribution_bins, simulation_value_threshold_bins
- intended write counts: {"calculation_configs": 1, "calculation_price_snapshots": 2, "calculation_runs": 1, "simulation_derived_metrics": 1, "simulation_input_cards": 237, "simulation_pull_summary": 14, "simulation_run_summary": 1, "simulation_value_distribution_bins": 50, "simulation_value_threshold_bins": 18}
- writes actually performed: 0

### Warning Flags

- No warning flags triggered.

## Guardrails

- Other SWSH runtime unchanged: True
- SV/Mega routing changed: False
- SV/Mega all expected v2: True
