-- Migration 025: add Pokemon Desirability Composite V1 scores.
--
-- This table combines favoritepokemon fan popularity with Google Trends current
-- 30-day relative search interest. It is intentionally not wired into RIP Score,
-- Opening Experience, frontend UI, simulations, or card-hit mapping.
--
-- Google Trends values are relative search interest only. They are not absolute
-- search volume, long-term popularity, or trend momentum.

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_composite_scores (
    id BIGSERIAL PRIMARY KEY,
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE CASCADE,
    pokedex_number INTEGER,
    pokemon_name TEXT NOT NULL,
    fan_popularity_score NUMERIC NOT NULL CHECK (
        fan_popularity_score >= 0 AND fan_popularity_score <= 100
    ),
    fan_popularity_rank INTEGER,
    fan_popularity_snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_desirability_source_snapshots(id) ON DELETE CASCADE,
    current_trend_score NUMERIC CHECK (
        current_trend_score IS NULL OR (current_trend_score >= 0 AND current_trend_score <= 100)
    ),
    current_trend_rank INTEGER,
    current_trend_snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_trend_source_snapshots(id) ON DELETE CASCADE,
    desirability_score NUMERIC NOT NULL CHECK (
        desirability_score >= 0 AND desirability_score <= 100
    ),
    desirability_rank INTEGER,
    desirability_tier TEXT NOT NULL CHECK (desirability_tier IN ('S', 'A', 'B', 'C', 'D', 'F')),
    scoring_version TEXT NOT NULL,
    score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (
        pokemon_reference_id,
        fan_popularity_snapshot_id,
        current_trend_snapshot_id,
        scoring_version
    )
);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_composite_reference
    ON public.pokemon_desirability_composite_scores (pokemon_reference_id, scoring_version, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_composite_rank
    ON public.pokemon_desirability_composite_scores (scoring_version, desirability_rank);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_composite_snapshots
    ON public.pokemon_desirability_composite_scores (
        fan_popularity_snapshot_id,
        current_trend_snapshot_id,
        scoring_version
    );

ALTER TABLE public.pokemon_desirability_composite_scores ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_desirability_composite_scores'
          AND policyname = 'pokemon_desirability_composite_scores_read_policy'
    ) THEN
        CREATE POLICY pokemon_desirability_composite_scores_read_policy
            ON public.pokemon_desirability_composite_scores
            FOR SELECT
            USING (true);
    END IF;
END $$;
