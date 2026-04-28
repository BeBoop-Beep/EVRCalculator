-- Add cost-ratio metrics to simulation_derived_metrics table for PACK display calculations.
ALTER TABLE IF EXISTS public.simulation_derived_metrics
    ADD COLUMN IF NOT EXISTS mean_value_to_cost_ratio NUMERIC,
    ADD COLUMN IF NOT EXISTS expected_loss_when_losing_fraction NUMERIC,
    ADD COLUMN IF NOT EXISTS p05_shortfall_to_cost NUMERIC,
    ADD COLUMN IF NOT EXISTS median_loss_when_losing_fraction NUMERIC;
