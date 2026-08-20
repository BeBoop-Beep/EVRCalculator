-- Market Date Quality: the Market surface's own publication authority.
-- Deliberately independent of public.pokemon_scrape_batches (the 167-set
-- cohort). A Market date is judged only on the canonical Market cohort.
BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_date_quality (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tcg TEXT NOT NULL DEFAULT 'pokemon',
    market_date DATE NOT NULL,
    status TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    cohort_set_count INTEGER NOT NULL DEFAULT 0,
    qualifying_set_count INTEGER NOT NULL DEFAULT 0,
    missing_set_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    cohort_fingerprint TEXT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_market_date_quality_status_check
        CHECK (status IN ('READY', 'INCOMPLETE', 'DEGRADED', 'LEGACY_VERIFIED')),
    CONSTRAINT pokemon_market_date_quality_identity
        UNIQUE (tcg, market_date, contract_version)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_market_date_quality_date
    ON public.pokemon_market_date_quality(tcg, market_date DESC);

COMMIT;
