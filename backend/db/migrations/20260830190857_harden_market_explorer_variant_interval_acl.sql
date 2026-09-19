-- Narrow the backend-only Market Explorer interval table after Supabase's
-- project-level default table ACL granted service_role broader privileges.
REVOKE ALL PRIVILEGES
ON TABLE public.pokemon_card_variant_market_price_intervals
FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, DELETE
ON TABLE public.pokemon_card_variant_market_price_intervals
TO service_role;
