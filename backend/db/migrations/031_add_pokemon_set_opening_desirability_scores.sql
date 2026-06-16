-- Migration 031: add persisted Opening Desirability score snapshots.
--
-- Scope:
--   - Adds an opt-in persistence target for the Opening Desirability prototype.
--   - Adds a public-safe latest view for downstream API/frontend integration.
--
-- Non-goals:
--   - No changes to V2 Pure Desirability.
--   - No changes to V1, EVR, RIP Score weights, or production frontend wiring.
--   - No persistence of formula, weight, or component-score audit JSON.

CREATE TABLE IF NOT EXISTS public.pokemon_set_opening_desirability_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    set_name TEXT,
    set_canonical_key TEXT,

    opening_desirability_score NUMERIC,
    opening_desirability_rank INTEGER,
    collector_appeal_score NUMERIC,
    collector_appeal_rank INTEGER,
    chase_appeal_score NUMERIC,
    chase_appeal_rank INTEGER,
    chase_appeal_data_quality TEXT NOT NULL,
    opening_desirability_display_status TEXT NOT NULL,
    opening_desirability_summary TEXT,
    public_tooltip_copy_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    source_v2_component_row_id UUID,
    source_rip_calculation_run_id UUID,

    pure_desirability_score NUMERIC,
    monetary_chase_appeal_score NUMERIC,
    rip_desirability_score_80_20 NUMERIC,
    rip_desirability_score_70_30 NUMERIC,
    rip_desirability_score_60_40 NUMERIC,

    scoring_version TEXT NOT NULL,
    built_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    CONSTRAINT pokemon_set_opening_desirability_chase_quality_check CHECK (
        chase_appeal_data_quality IN ('usable', 'partial', 'missing')
    ),
    CONSTRAINT pokemon_set_opening_desirability_display_status_check CHECK (
        opening_desirability_display_status IN (
            'scored',
            'collector_only',
            'insufficient_chase_data'
        )
    ),
    CONSTRAINT pokemon_set_opening_desirability_score_bounds_check CHECK (
        (opening_desirability_score IS NULL OR opening_desirability_score BETWEEN 0 AND 100)
        AND (collector_appeal_score IS NULL OR collector_appeal_score BETWEEN 0 AND 100)
        AND (chase_appeal_score IS NULL OR chase_appeal_score BETWEEN 0 AND 100)
        AND (pure_desirability_score IS NULL OR pure_desirability_score BETWEEN 0 AND 100)
        AND (monetary_chase_appeal_score IS NULL OR monetary_chase_appeal_score BETWEEN 0 AND 100)
        AND (rip_desirability_score_80_20 IS NULL OR rip_desirability_score_80_20 BETWEEN 0 AND 100)
        AND (rip_desirability_score_70_30 IS NULL OR rip_desirability_score_70_30 BETWEEN 0 AND 100)
        AND (rip_desirability_score_60_40 IS NULL OR rip_desirability_score_60_40 BETWEEN 0 AND 100)
    ),
    CONSTRAINT pokemon_set_opening_desirability_rank_positive_check CHECK (
        (opening_desirability_rank IS NULL OR opening_desirability_rank > 0)
        AND (collector_appeal_rank IS NULL OR collector_appeal_rank > 0)
        AND (chase_appeal_rank IS NULL OR chase_appeal_rank > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_set_id
    ON public.pokemon_set_opening_desirability_scores (set_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_set_canonical_key
    ON public.pokemon_set_opening_desirability_scores (set_canonical_key);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_scoring_version
    ON public.pokemon_set_opening_desirability_scores (scoring_version);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_built_at
    ON public.pokemon_set_opening_desirability_scores (built_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_opening_rank
    ON public.pokemon_set_opening_desirability_scores (opening_desirability_rank);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_collector_rank
    ON public.pokemon_set_opening_desirability_scores (collector_appeal_rank);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_opening_desirability_chase_rank
    ON public.pokemon_set_opening_desirability_scores (chase_appeal_rank);

ALTER TABLE public.pokemon_set_opening_desirability_scores ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_set_opening_desirability_scores'
          AND policyname = 'pokemon_set_opening_desirability_scores_read_policy'
    ) THEN
        CREATE POLICY pokemon_set_opening_desirability_scores_read_policy
            ON public.pokemon_set_opening_desirability_scores
            FOR SELECT
            USING (true);
    END IF;
END $$;

CREATE OR REPLACE VIEW public.pokemon_set_opening_desirability_latest
WITH (security_invoker = true) AS
SELECT
    set_id,
    set_name,
    set_canonical_key,
    opening_desirability_score,
    opening_desirability_rank,
    collector_appeal_score,
    collector_appeal_rank,
    chase_appeal_score,
    chase_appeal_rank,
    chase_appeal_data_quality,
    opening_desirability_display_status,
    opening_desirability_summary,
    public_tooltip_copy_json,
    source_v2_component_row_id,
    source_rip_calculation_run_id,
    scoring_version,
    built_at
FROM (
    SELECT
        scores.*,
        row_number() OVER (
            PARTITION BY scores.set_id, scores.scoring_version
            ORDER BY scores.built_at DESC, scores.created_at DESC, scores.id DESC
        ) AS latest_row_number
    FROM public.pokemon_set_opening_desirability_scores AS scores
) AS latest
WHERE latest.latest_row_number = 1;

