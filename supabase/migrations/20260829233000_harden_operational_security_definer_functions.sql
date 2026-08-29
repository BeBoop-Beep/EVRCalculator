-- Restrict operational SECURITY DEFINER functions to trusted backend callers.
-- All referenced application relations are schema-qualified, so only built-ins
-- need to be resolvable through the function search path.

ALTER FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean)
  SET search_path = pg_catalog;
ALTER FUNCTION public.heartbeat_pokemon_set_onboarding_job(uuid, text, integer)
  SET search_path = pg_catalog;
ALTER FUNCTION public.cleanup_expired_waitlist_signups()
  SET search_path = pg_catalog;
ALTER FUNCTION public.get_nightly_snapshot_pricing_freshness(date, integer)
  SET search_path = pg_catalog;

REVOKE ALL ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.heartbeat_pokemon_set_onboarding_job(uuid, text, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.cleanup_expired_waitlist_signups()
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_nightly_snapshot_pricing_freshness(date, integer)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_pokemon_set_onboarding_job(uuid, text, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.cleanup_expired_waitlist_signups()
  TO service_role;
GRANT EXECUTE ON FUNCTION public.get_nightly_snapshot_pricing_freshness(date, integer)
  TO service_role;
