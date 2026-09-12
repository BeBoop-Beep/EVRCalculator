DO $do$
DECLARE
  v_def text;
BEGIN
  SELECT pg_get_functiondef(p.oid)
    INTO v_def
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='get_pokemon_canonical_card_market_prices_latest_for_set'
    AND p.prokind='f'
  LIMIT 1;

  IF v_def IS NULL THEN
    RAISE EXCEPTION 'Production canonical latest-price resolver not found';
  END IF;

  v_def := replace(
      v_def,
      'CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(',
      'CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_legacy_shadow('
  );
  EXECUTE v_def;
END
$do$;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_legacy_shadow(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_legacy_shadow(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id uuid)
RETURNS TABLE(canonical_card_id uuid, set_id uuid, pokemon_tcg_api_card_id text, legacy_card_id uuid, card_variant_id uuid, condition_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
  SELECT *
  FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(target_set_id);
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid) TO service_role;

COMMENT ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid) IS
'Production canonical latest-price resolver backed by Price Storage V2 current state. Exact pre-cutover raw resolver retained as get_pokemon_canonical_card_market_prices_latest_for_set_legacy_shadow(uuid).';