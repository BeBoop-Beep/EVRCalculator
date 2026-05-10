-- Migration 016: Add derived intelligence metrics to simulation_derived_metrics.
-- Adds only the required fields for Stage 1.

ALTER TABLE public.simulation_derived_metrics
ADD COLUMN IF NOT EXISTS chase_potential_score numeric,
ADD COLUMN IF NOT EXISTS experience_score numeric,
ADD COLUMN IF NOT EXISTS chase_potential_tier text,
ADD COLUMN IF NOT EXISTS experience_tier text,
ADD COLUMN IF NOT EXISTS derived_metric_version text;

-- Add indexes on the new composite scores
CREATE INDEX IF NOT EXISTS idx_simulation_derived_metrics_chase_potential_score
  ON public.simulation_derived_metrics(chase_potential_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_simulation_derived_metrics_experience_score
  ON public.simulation_derived_metrics(experience_score DESC NULLS LAST);
