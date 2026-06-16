-- Migration 030: add side-by-side Pokemon set desirability component scores.
--
-- This table stores the Desirability V2 component model. It is intentionally
-- additive and is not consumed by RIP Score, set_desirability_service.py,
-- the EVR runner, or frontend code.

CREATE TABLE IF NOT EXISTS public.pokemon_set_desirability_component_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    set_name TEXT,
    set_canonical_key TEXT,

    scoring_version TEXT NOT NULL,
    hit_policy_version TEXT NOT NULL,
    composite_scoring_version TEXT NOT NULL,
    fan_popularity_snapshot_id TEXT,
    current_trend_snapshot_ids JSONB,

    source_config_path TEXT,
    config_fingerprint TEXT,

    set_desirability_score NUMERIC NOT NULL,

    chase_subject_strength NUMERIC NOT NULL,
    chase_subject_depth NUMERIC NOT NULL,
    accessible_favorite_hits NUMERIC NOT NULL,
    special_pack_chase_appeal NUMERIC NOT NULL,

    hit_eligible_card_count INTEGER NOT NULL DEFAULT 0,
    scored_hit_eligible_card_count INTEGER NOT NULL DEFAULT 0,
    unique_subject_count INTEGER NOT NULL DEFAULT 0,
    duplicate_subject_count INTEGER NOT NULL DEFAULT 0,
    premium_chase_subject_count INTEGER NOT NULL DEFAULT 0,
    major_hit_subject_count INTEGER NOT NULL DEFAULT 0,
    accessible_hit_count INTEGER NOT NULL DEFAULT 0,
    trainer_hit_count INTEGER NOT NULL DEFAULT 0,
    unmatched_hit_count INTEGER NOT NULL DEFAULT 0,

    top_subjects_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    subject_rollups_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    rarity_bucket_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    special_pack_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    component_inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    built_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

    CONSTRAINT pokemon_set_desirability_component_score_bounds_check CHECK (
        set_desirability_score BETWEEN 0 AND 100
        AND chase_subject_strength BETWEEN 0 AND 100
        AND chase_subject_depth BETWEEN 0 AND 100
        AND accessible_favorite_hits BETWEEN 0 AND 100
        AND special_pack_chase_appeal BETWEEN 0 AND 100
    ),
    CONSTRAINT pokemon_set_desirability_component_counts_check CHECK (
        hit_eligible_card_count >= 0
        AND scored_hit_eligible_card_count >= 0
        AND unique_subject_count >= 0
        AND duplicate_subject_count >= 0
        AND premium_chase_subject_count >= 0
        AND major_hit_subject_count >= 0
        AND accessible_hit_count >= 0
        AND trainer_hit_count >= 0
        AND unmatched_hit_count >= 0
    ),
    CONSTRAINT pokemon_set_desirability_component_unique_key UNIQUE (
        set_id,
        scoring_version,
        hit_policy_version,
        composite_scoring_version,
        fan_popularity_snapshot_id,
        config_fingerprint
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_unique_build
    ON public.pokemon_set_desirability_component_scores (
        set_id,
        scoring_version,
        hit_policy_version,
        composite_scoring_version,
        COALESCE(fan_popularity_snapshot_id, '__null__'),
        COALESCE(config_fingerprint, '__null__')
    );

CREATE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_set_id
    ON public.pokemon_set_desirability_component_scores (set_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_set_canonical_key
    ON public.pokemon_set_desirability_component_scores (set_canonical_key);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_version
    ON public.pokemon_set_desirability_component_scores (
        scoring_version,
        hit_policy_version,
        composite_scoring_version
    );

CREATE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_score
    ON public.pokemon_set_desirability_component_scores (set_desirability_score DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_desirability_component_built_at
    ON public.pokemon_set_desirability_component_scores (built_at DESC);

ALTER TABLE public.pokemon_set_desirability_component_scores ENABLE ROW LEVEL SECURITY;
