BEGIN;

CREATE TABLE public.pokemon_market_index_daily_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tcg TEXT NOT NULL DEFAULT 'pokemon' CHECK (tcg = 'pokemon'),
    index_key TEXT NOT NULL CHECK (index_key IN ('raw', 'top10')),
    market_date DATE NOT NULL,
    contract_version TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    basket_value NUMERIC NOT NULL CHECK (basket_value > 0),
    normalized_index_value NUMERIC NOT NULL CHECK (normalized_index_value > 0),
    daily_return NUMERIC,
    previous_market_date DATE,
    set_count INTEGER NOT NULL CHECK (set_count > 0),
    card_count INTEGER NOT NULL CHECK (card_count > 0),
    cohort_fingerprint TEXT NOT NULL,
    source_generation_fingerprint TEXT NOT NULL,
    constituents_json JSONB NOT NULL CHECK (jsonb_typeof(constituents_json) = 'array'),
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(diagnostics_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tcg, index_key, market_date, methodology_version)
);
CREATE INDEX pokemon_market_index_key_date_idx ON public.pokemon_market_index_daily_history (index_key, market_date DESC);
CREATE INDEX pokemon_market_index_methodology_date_idx ON public.pokemon_market_index_daily_history (methodology_version, market_date DESC);
CREATE TRIGGER trg_pokemon_market_index_updated_at BEFORE UPDATE ON public.pokemon_market_index_daily_history
FOR EACH ROW EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();
ALTER TABLE public.pokemon_market_index_daily_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_index_daily_history FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_market_index_daily_history TO service_role;

COMMIT;
