-- Add p99 value-to-cost ratio as a persisted derived metric.
ALTER TABLE IF EXISTS public.simulation_derived_metrics
    ADD COLUMN IF NOT EXISTS p99_value_to_cost_ratio NUMERIC;
