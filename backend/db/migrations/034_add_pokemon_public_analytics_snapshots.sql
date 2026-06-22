-- Page-ready public Pokemon analytics snapshots.
--
-- These tables are the thin read-model layer for public analytics pages. They
-- are populated by builder scripts and read by API endpoints; frontend code must
-- continue to use the backend/proxy routes rather than Supabase directly.

BEGIN;

CREATE OR REPLACE FUNCTION public.sync_pokemon_public_snapshot_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := timezone('utc', now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.pokemon_set_page_snapshot_latest (
    set_id UUID PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    set_identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    title_card_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rip_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    market_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    concentration_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    desirability_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    set_intelligence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_json JSONB NOT NULL,
    as_of TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS public.pokemon_set_market_dashboard_snapshot_latest (
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    window_key TEXT NOT NULL DEFAULT '365d',
    payload_json JSONB NOT NULL,
    set_value_histories_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    performance_vs_cost_history_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_chase_cards_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_chase_card_histories_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    available_scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    latest_market_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (set_id, window_key)
);

CREATE TABLE IF NOT EXISTS public.pokemon_explore_rankings_snapshot_latest (
    tcg TEXT NOT NULL DEFAULT 'pokemon',
    scope TEXT NOT NULL DEFAULT 'rip-statistics',
    ranking_payload_json JSONB NOT NULL,
    default_target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (tcg, scope)
);

CREATE TABLE IF NOT EXISTS public.pokemon_set_cards_snapshot_latest (
    set_id UUID PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    cards_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload_json JSONB NOT NULL,
    card_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS public.pokemon_set_top_chase_card_daily_history (
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    card_id UUID,
    card_variant_id UUID,
    rank INTEGER NOT NULL,
    name TEXT,
    rarity TEXT,
    image_url TEXT,
    image_small_url TEXT,
    image_large_url TEXT,
    market_price NUMERIC,
    source TEXT,
    source_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (set_id, snapshot_date, rank)
);

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_validation_snapshot_latest (
    tcg TEXT NOT NULL DEFAULT 'pokemon',
    scope TEXT NOT NULL DEFAULT 'latest',
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (tcg, scope)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_page_snapshot_latest_updated_at
    ON public.pokemon_set_page_snapshot_latest (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_market_dashboard_snapshot_latest_updated_at
    ON public.pokemon_set_market_dashboard_snapshot_latest (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_market_dashboard_snapshot_latest_market_date
    ON public.pokemon_set_market_dashboard_snapshot_latest (latest_market_date DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_top_chase_history_set_date
    ON public.pokemon_set_top_chase_card_daily_history (set_id, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_top_chase_history_card
    ON public.pokemon_set_top_chase_card_daily_history (card_id, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_cards_snapshot_latest_updated_at
    ON public.pokemon_set_cards_snapshot_latest (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_page_snapshot_payload_gin
    ON public.pokemon_set_page_snapshot_latest USING GIN (payload_json);

CREATE INDEX IF NOT EXISTS idx_pokemon_explore_rankings_snapshot_payload_gin
    ON public.pokemon_explore_rankings_snapshot_latest USING GIN (ranking_payload_json);

DROP TRIGGER IF EXISTS trg_pokemon_set_page_snapshot_latest_updated_at
    ON public.pokemon_set_page_snapshot_latest;
CREATE TRIGGER trg_pokemon_set_page_snapshot_latest_updated_at
BEFORE UPDATE ON public.pokemon_set_page_snapshot_latest
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

DROP TRIGGER IF EXISTS trg_pokemon_market_dashboard_snapshot_latest_updated_at
    ON public.pokemon_set_market_dashboard_snapshot_latest;
CREATE TRIGGER trg_pokemon_market_dashboard_snapshot_latest_updated_at
BEFORE UPDATE ON public.pokemon_set_market_dashboard_snapshot_latest
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

DROP TRIGGER IF EXISTS trg_pokemon_explore_rankings_snapshot_latest_updated_at
    ON public.pokemon_explore_rankings_snapshot_latest;
CREATE TRIGGER trg_pokemon_explore_rankings_snapshot_latest_updated_at
BEFORE UPDATE ON public.pokemon_explore_rankings_snapshot_latest
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

DROP TRIGGER IF EXISTS trg_pokemon_set_cards_snapshot_latest_updated_at
    ON public.pokemon_set_cards_snapshot_latest;
CREATE TRIGGER trg_pokemon_set_cards_snapshot_latest_updated_at
BEFORE UPDATE ON public.pokemon_set_cards_snapshot_latest
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

DROP TRIGGER IF EXISTS trg_pokemon_top_chase_history_updated_at
    ON public.pokemon_set_top_chase_card_daily_history;
CREATE TRIGGER trg_pokemon_top_chase_history_updated_at
BEFORE UPDATE ON public.pokemon_set_top_chase_card_daily_history
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

DROP TRIGGER IF EXISTS trg_pokemon_desirability_validation_snapshot_latest_updated_at
    ON public.pokemon_desirability_validation_snapshot_latest;
CREATE TRIGGER trg_pokemon_desirability_validation_snapshot_latest_updated_at
BEFORE UPDATE ON public.pokemon_desirability_validation_snapshot_latest
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

ALTER TABLE public.pokemon_set_page_snapshot_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_set_market_dashboard_snapshot_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_explore_rankings_snapshot_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_set_cards_snapshot_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_set_top_chase_card_daily_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_desirability_validation_snapshot_latest ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    table_name TEXT;
    policy_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'pokemon_set_page_snapshot_latest',
        'pokemon_set_market_dashboard_snapshot_latest',
        'pokemon_explore_rankings_snapshot_latest',
        'pokemon_set_cards_snapshot_latest',
        'pokemon_set_top_chase_card_daily_history',
        'pokemon_desirability_validation_snapshot_latest'
    ]
    LOOP
        policy_name := table_name || '_read_policy';
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = table_name
              AND policyname = policy_name
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT USING (true)',
                policy_name,
                table_name
            );
        END IF;
    END LOOP;
END $$;

GRANT SELECT ON public.pokemon_set_page_snapshot_latest TO anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_set_market_dashboard_snapshot_latest TO anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_explore_rankings_snapshot_latest TO anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_set_cards_snapshot_latest TO anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_set_top_chase_card_daily_history TO anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_desirability_validation_snapshot_latest TO anon, authenticated, service_role;

GRANT INSERT, UPDATE, DELETE ON public.pokemon_set_page_snapshot_latest TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_set_market_dashboard_snapshot_latest TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_explore_rankings_snapshot_latest TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_set_cards_snapshot_latest TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_set_top_chase_card_daily_history TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_desirability_validation_snapshot_latest TO service_role;

COMMIT;
