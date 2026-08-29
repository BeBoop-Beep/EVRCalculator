-- The first boundary sentinel pass found Plus Market Breadth in this otherwise
-- public-looking sealed-market snapshot. Keep the mixed raw payload backend-only.

BEGIN;

DROP POLICY IF EXISTS pokemon_set_sealed_market_snapshot_latest_read_policy
    ON public.pokemon_set_sealed_market_snapshot_latest;

ALTER TABLE public.pokemon_set_sealed_market_snapshot_latest
    ENABLE ROW LEVEL SECURITY;

REVOKE SELECT ON public.pokemon_set_sealed_market_snapshot_latest
    FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_set_sealed_market_snapshot_latest
    TO service_role;

COMMIT;
