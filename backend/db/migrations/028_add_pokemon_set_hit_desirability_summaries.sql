-- Migration 028: add materialized Pokemon set hit-card desirability summaries.
--
-- This table summarizes Pokemon desirability for hit-eligible canonical cards.
-- It is intentionally additive and does not read from or modify TCGplayer,
-- card_variants, pricing, market reconciliation, simulation, or frontend state.

CREATE TABLE IF NOT EXISTS public.pokemon_set_hit_desirability_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    set_name TEXT,
    set_canonical_key TEXT,
    aggregation_version TEXT NOT NULL,
    hit_policy_version TEXT NOT NULL,
    composite_scoring_version TEXT NOT NULL,
    fan_popularity_snapshot_id BIGINT,
    current_trend_snapshot_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    composite_score_row_count INTEGER,
    composite_score_coverage_ratio NUMERIC,
    built_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    hit_eligible_card_count INTEGER NOT NULL DEFAULT 0,
    scored_hit_eligible_card_count INTEGER NOT NULL DEFAULT 0,
    linked_pokemon_count INTEGER NOT NULL DEFAULT 0,
    unique_linked_pokemon_count INTEGER NOT NULL DEFAULT 0,
    scored_link_count INTEGER NOT NULL DEFAULT 0,
    missing_score_count INTEGER NOT NULL DEFAULT 0,
    fallback_link_count INTEGER NOT NULL DEFAULT 0,
    multi_pokemon_card_count INTEGER NOT NULL DEFAULT 0,

    average_hit_desirability_score NUMERIC,
    weighted_average_hit_desirability_score NUMERIC,
    max_hit_desirability_score NUMERIC,
    top_3_hit_desirability_score NUMERIC,
    top_5_hit_desirability_score NUMERIC,
    desirability_concentration_top_1_share NUMERIC,
    desirability_concentration_top_3_share NUMERIC,
    desirability_depth_score NUMERIC,
    effective_desirable_card_count NUMERIC,

    top_desirable_pokemon_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_desirable_cards_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_score_reference_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    CONSTRAINT pokemon_set_hit_desirability_unique_summary_key UNIQUE (
        set_id,
        aggregation_version,
        hit_policy_version,
        composite_scoring_version,
        fan_popularity_snapshot_id
    ),
    CONSTRAINT pokemon_set_hit_desirability_counts_check CHECK (
        hit_eligible_card_count >= 0
        AND scored_hit_eligible_card_count >= 0
        AND linked_pokemon_count >= 0
        AND unique_linked_pokemon_count >= 0
        AND scored_link_count >= 0
        AND missing_score_count >= 0
        AND fallback_link_count >= 0
        AND multi_pokemon_card_count >= 0
    ),
    CONSTRAINT pokemon_set_hit_desirability_score_bounds_check CHECK (
        (average_hit_desirability_score IS NULL OR average_hit_desirability_score BETWEEN 0 AND 100)
        AND (
            weighted_average_hit_desirability_score IS NULL
            OR weighted_average_hit_desirability_score BETWEEN 0 AND 100
        )
        AND (max_hit_desirability_score IS NULL OR max_hit_desirability_score BETWEEN 0 AND 100)
        AND (top_3_hit_desirability_score IS NULL OR top_3_hit_desirability_score BETWEEN 0 AND 100)
        AND (top_5_hit_desirability_score IS NULL OR top_5_hit_desirability_score BETWEEN 0 AND 100)
        AND (desirability_depth_score IS NULL OR desirability_depth_score BETWEEN 0 AND 100)
    ),
    CONSTRAINT pokemon_set_hit_desirability_share_bounds_check CHECK (
        (
            desirability_concentration_top_1_share IS NULL
            OR desirability_concentration_top_1_share BETWEEN 0 AND 1
        )
        AND (
            desirability_concentration_top_3_share IS NULL
            OR desirability_concentration_top_3_share BETWEEN 0 AND 1
        )
    ),
    CONSTRAINT pokemon_set_hit_desirability_effective_count_check CHECK (
        effective_desirable_card_count IS NULL OR effective_desirable_card_count >= 1
    )
);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_set_id
    ON public.pokemon_set_hit_desirability_summaries (set_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_set_canonical_key
    ON public.pokemon_set_hit_desirability_summaries (set_canonical_key);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_aggregation_version
    ON public.pokemon_set_hit_desirability_summaries (aggregation_version);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_policy_composite
    ON public.pokemon_set_hit_desirability_summaries (
        hit_policy_version,
        composite_scoring_version
    );

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_weighted_average
    ON public.pokemon_set_hit_desirability_summaries (weighted_average_hit_desirability_score);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_hit_desirability_built_at
    ON public.pokemon_set_hit_desirability_summaries (built_at);

ALTER TABLE public.pokemon_set_hit_desirability_summaries ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_set_hit_desirability_summaries'
          AND policyname = 'pokemon_set_hit_desirability_summaries_read_policy'
    ) THEN
        CREATE POLICY pokemon_set_hit_desirability_summaries_read_policy
            ON public.pokemon_set_hit_desirability_summaries
            FOR SELECT
            USING (true);
    END IF;
END $$;
