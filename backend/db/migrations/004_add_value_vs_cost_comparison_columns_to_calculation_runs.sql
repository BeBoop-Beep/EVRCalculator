-- Persist value-vs-cost comparison ratios on parent calculation runs.
ALTER TABLE IF EXISTS public.calculation_runs
    ADD COLUMN IF NOT EXISTS simulated_mean_pack_value_vs_pack_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS simulated_median_pack_value_vs_pack_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calculated_expected_pack_value_vs_pack_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS simulated_mean_etb_value_vs_etb_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS simulated_median_etb_value_vs_etb_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calculated_expected_etb_value_vs_etb_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS simulated_mean_booster_box_value_vs_booster_box_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS simulated_median_booster_box_value_vs_booster_box_cost DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calculated_expected_booster_box_value_vs_booster_box_cost DOUBLE PRECISION;
