BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_explore_set_value_snapshot_latest (
    tcg TEXT NOT NULL DEFAULT 'pokemon',
    scope TEXT NOT NULL DEFAULT 'market',
    payload_json JSONB NOT NULL,
    market_date DATE NOT NULL,
    set_count INTEGER NOT NULL CHECK (set_count >= 0),
    source_generation_fingerprint TEXT NOT NULL,
    payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (tcg, scope),
    CHECK (tcg = 'pokemon' AND scope = 'market')
);

CREATE INDEX IF NOT EXISTS idx_pokemon_explore_set_value_market_date
    ON public.pokemon_explore_set_value_snapshot_latest (market_date DESC);

DROP TRIGGER IF EXISTS trg_pokemon_explore_set_value_updated_at
    ON public.pokemon_explore_set_value_snapshot_latest;
CREATE TRIGGER trg_pokemon_explore_set_value_updated_at
BEFORE UPDATE ON public.pokemon_explore_set_value_snapshot_latest
FOR EACH ROW EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

ALTER TABLE public.pokemon_explore_set_value_snapshot_latest ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'pokemon_explore_set_value_snapshot_latest' AND policyname = 'pokemon_explore_set_value_snapshot_latest_read_policy') THEN
        CREATE POLICY pokemon_explore_set_value_snapshot_latest_read_policy ON public.pokemon_explore_set_value_snapshot_latest FOR SELECT USING (true);
    END IF;
END $$;
REVOKE ALL ON public.pokemon_explore_set_value_snapshot_latest FROM anon, authenticated;
GRANT SELECT ON public.pokemon_explore_set_value_snapshot_latest TO anon, authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_explore_set_value_snapshot_latest TO service_role;

COMMIT;
