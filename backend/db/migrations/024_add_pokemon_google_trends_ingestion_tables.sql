-- Migration 024: add Pokemon Google Trends relative search-interest ingestion tables.
--
-- These tables store Google Trends source snapshots, anchor-normalized source rows,
-- and derived relative search-interest scores only. They are intentionally not wired
-- into RIP Score, Opening Experience, simulation logic, card-hit mapping, or UI views.
--
-- Google Trends values are normalized relative search interest. They are not absolute
-- total search counts or total search volume.

CREATE TABLE IF NOT EXISTS public.pokemon_trend_source_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    geo TEXT NOT NULL DEFAULT 'US',
    timeframe TEXT NOT NULL,
    window_role TEXT NOT NULL CHECK (window_role IN ('recent', 'validation', 'current', 'baseline')),
    query_type TEXT NOT NULL CHECK (query_type IN ('search_term')),
    anchor_term TEXT NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_source_snapshots_source_captured
    ON public.pokemon_trend_source_snapshots (source_name, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_source_snapshots_window
    ON public.pokemon_trend_source_snapshots (geo, timeframe, window_role, captured_at DESC);

CREATE TABLE IF NOT EXISTS public.pokemon_trend_source_rows (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_trend_source_snapshots(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    pokemon_reference_id BIGINT REFERENCES public.pokemon_reference(id) ON DELETE SET NULL,
    pokedex_number INTEGER,
    pokemon_name TEXT NOT NULL,
    query_term TEXT NOT NULL,
    geo TEXT NOT NULL DEFAULT 'US',
    timeframe TEXT NOT NULL,
    window_role TEXT NOT NULL CHECK (window_role IN ('recent', 'validation', 'current', 'baseline')),
    query_type TEXT NOT NULL CHECK (query_type IN ('search_term')),
    anchor_term TEXT NOT NULL,
    batch_key TEXT NOT NULL,
    raw_interest_value NUMERIC,
    anchor_interest_value NUMERIC,
    relative_to_anchor NUMERIC,
    is_ambiguous BOOLEAN NOT NULL DEFAULT false,
    extraction_confidence TEXT NOT NULL CHECK (extraction_confidence IN ('high', 'medium', 'low', 'insufficient')),
    raw_row_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_source_rows_snapshot
    ON public.pokemon_trend_source_rows (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_source_rows_reference
    ON public.pokemon_trend_source_rows (pokemon_reference_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_source_rows_window
    ON public.pokemon_trend_source_rows (geo, timeframe, window_role);

CREATE TABLE IF NOT EXISTS public.pokemon_trend_scores (
    id BIGSERIAL PRIMARY KEY,
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    score_name TEXT NOT NULL CHECK (
        score_name IN ('search_popularity_score', 'recent_trend_score', 'trend_momentum_score')
    ),
    relative_search_interest_score NUMERIC NOT NULL CHECK (
        relative_search_interest_score >= 0 AND relative_search_interest_score <= 100
    ),
    normalized_rank INTEGER,
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'insufficient')),
    scoring_version TEXT NOT NULL,
    primary_snapshot_id BIGINT NOT NULL REFERENCES public.pokemon_trend_source_snapshots(id) ON DELETE CASCADE,
    contributing_snapshot_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pokemon_reference_id, source_name, score_name, primary_snapshot_id, scoring_version)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_scores_reference_score
    ON public.pokemon_trend_scores (pokemon_reference_id, score_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_trend_scores_primary_snapshot
    ON public.pokemon_trend_scores (primary_snapshot_id);

ALTER TABLE public.pokemon_trend_source_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_trend_source_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_trend_scores ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_trend_source_snapshots'
          AND policyname = 'pokemon_trend_source_snapshots_read_policy'
    ) THEN
        CREATE POLICY pokemon_trend_source_snapshots_read_policy
            ON public.pokemon_trend_source_snapshots
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_trend_source_rows'
          AND policyname = 'pokemon_trend_source_rows_read_policy'
    ) THEN
        CREATE POLICY pokemon_trend_source_rows_read_policy
            ON public.pokemon_trend_source_rows
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_trend_scores'
          AND policyname = 'pokemon_trend_scores_read_policy'
    ) THEN
        CREATE POLICY pokemon_trend_scores_read_policy
            ON public.pokemon_trend_scores
            FOR SELECT
            USING (true);
    END IF;
END $$;
