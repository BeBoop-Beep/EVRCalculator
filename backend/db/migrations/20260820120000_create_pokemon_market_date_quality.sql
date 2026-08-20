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

-- =============================================================================
-- Security: backend-only publication authority
-- =============================================================================
-- Same posture as public.pokemon_scrape_batches (migrations 047/051). This
-- table decides whether the Market surface may publish, so it must never be
-- readable or writable through the public PostgREST roles. RLS is enabled with
-- NO policy: non-BYPASSRLS roles are denied outright.

ALTER TABLE public.pokemon_market_date_quality ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.pokemon_market_date_quality FROM PUBLIC;
REVOKE ALL ON TABLE public.pokemon_market_date_quality FROM anon;
REVOKE ALL ON TABLE public.pokemon_market_date_quality FROM authenticated;

-- Reset service_role too, so it does not retain the default set including
-- TRUNCATE. This table is the sole input to the Market publication gate; a
-- compromised service key must not be able to erase the quality lineage that
-- keeps a DEGRADED date out of chain-link math. Revoke+grant run inside this
-- migration's transaction, so service_role is never momentarily unprivileged.
REVOKE ALL ON TABLE public.pokemon_market_date_quality FROM service_role;

-- Exactly what the Market quality service performs: read history, upsert the
-- evaluated verdict. No DELETE - historical quality rows are audit evidence
-- and are never removed to make history look clean.
GRANT SELECT, INSERT, UPDATE
  ON TABLE public.pokemon_market_date_quality TO service_role;

REVOKE ALL ON SEQUENCE public.pokemon_market_date_quality_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.pokemon_market_date_quality_id_seq FROM anon;
REVOKE ALL ON SEQUENCE public.pokemon_market_date_quality_id_seq FROM authenticated;

GRANT USAGE, SELECT ON SEQUENCE public.pokemon_market_date_quality_id_seq TO service_role;

COMMIT;
