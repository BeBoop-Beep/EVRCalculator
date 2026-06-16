-- Migration 023: add Pokemon desirability source ingestion tables.
--
-- These tables store source snapshots and normalized source scores only.
-- They are intentionally not wired into RIP Score, Opening Experience, or
-- simulation/explore views.

CREATE TABLE IF NOT EXISTS public.pokemon_reference (
    id BIGSERIAL PRIMARY KEY,
    pokedex_number INTEGER NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    api_source TEXT NOT NULL DEFAULT 'pokeapi',
    api_url TEXT NOT NULL,
    sprite_url TEXT,
    generation INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_reference_canonical_name
    ON public.pokemon_reference (canonical_name);

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_source_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    capture_method TEXT NOT NULL,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_source_snapshots_source_captured
    ON public.pokemon_desirability_source_snapshots (source_name, captured_at DESC);

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_source_rows (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_desirability_source_snapshots(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    pokemon_reference_id BIGINT REFERENCES public.pokemon_reference(id) ON DELETE SET NULL,
    pokedex_number INTEGER,
    pokemon_name TEXT NOT NULL,
    raw_rank INTEGER,
    raw_vote_count INTEGER,
    raw_score NUMERIC,
    raw_tier TEXT,
    source_detail_url TEXT,
    extraction_confidence TEXT NOT NULL,
    raw_row_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_source_rows_snapshot
    ON public.pokemon_desirability_source_rows (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_source_rows_reference
    ON public.pokemon_desirability_source_rows (pokemon_reference_id);

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_scores (
    id BIGSERIAL PRIMARY KEY,
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_desirability_source_snapshots(id) ON DELETE CASCADE,
    normalized_score NUMERIC NOT NULL CHECK (normalized_score >= 0 AND normalized_score <= 100),
    normalized_rank INTEGER,
    desirability_tier TEXT NOT NULL CHECK (desirability_tier IN ('S', 'A', 'B', 'C', 'D', 'F')),
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'insufficient')),
    scoring_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pokemon_reference_id, source_name, snapshot_id, scoring_version)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_scores_reference_source
    ON public.pokemon_desirability_scores (pokemon_reference_id, source_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_desirability_scores_snapshot
    ON public.pokemon_desirability_scores (snapshot_id);

ALTER TABLE public.pokemon_reference ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_desirability_source_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_desirability_source_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_desirability_scores ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_reference'
          AND policyname = 'pokemon_reference_read_policy'
    ) THEN
        CREATE POLICY pokemon_reference_read_policy
            ON public.pokemon_reference
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_desirability_source_snapshots'
          AND policyname = 'pokemon_desirability_source_snapshots_read_policy'
    ) THEN
        CREATE POLICY pokemon_desirability_source_snapshots_read_policy
            ON public.pokemon_desirability_source_snapshots
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_desirability_source_rows'
          AND policyname = 'pokemon_desirability_source_rows_read_policy'
    ) THEN
        CREATE POLICY pokemon_desirability_source_rows_read_policy
            ON public.pokemon_desirability_source_rows
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_desirability_scores'
          AND policyname = 'pokemon_desirability_scores_read_policy'
    ) THEN
        CREATE POLICY pokemon_desirability_scores_read_policy
            ON public.pokemon_desirability_scores
            FOR SELECT
            USING (true);
    END IF;
END $$;

