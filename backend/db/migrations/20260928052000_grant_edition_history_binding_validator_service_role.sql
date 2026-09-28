-- Permit the service-role edition-history publisher to execute its
-- SECURITY INVOKER binding validator. Public/authenticated callers remain denied.
BEGIN;

REVOKE ALL ON FUNCTION public.pokemon_market_binding_is_valid_v3(
  uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,text
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.pokemon_market_binding_is_valid_v3(
  uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,text
) TO service_role;

COMMENT ON FUNCTION public.pokemon_market_binding_is_valid_v3(
  uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,text
) IS 'Read-only edition basket binding validator. Executable by service_role because refresh_pokemon_edition_history_day_v1 is an authorized service-role publication RPC.';

COMMIT;
