-- Internal analytics authority: only backend service-role snapshot builders
-- call this RPC. Keep it unavailable to public Data API roles.
REVOKE EXECUTE
ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE)
FROM anon, authenticated;
