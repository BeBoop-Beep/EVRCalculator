DO $do$
DECLARE
  v_def text;
BEGIN
  SELECT pg_get_functiondef(p.oid)
    INTO v_def
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='get_pokemon_market_root_set_card_prices_latest_v1'
    AND p.prokind='f'
  LIMIT 1;

  IF v_def IS NULL THEN
    RAISE EXCEPTION 'Production root-set latest-price function not found';
  END IF;

  v_def := replace(
      v_def,
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(',
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_legacy_shadow('
  );
  EXECUTE v_def;
END
$do$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_legacy_shadow(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_legacy_shadow(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id uuid DEFAULT NULL::uuid)
RETURNS TABLE(
  root_set_id uuid,
  root_set_name text,
  member_set_id uuid,
  member_set_name text,
  member_type text,
  market_scope text,
  canonical_card_id uuid,
  card_name text,
  card_number text,
  rarity text,
  canonical_review_status text,
  card_variant_id uuid,
  edition text,
  printing_type text,
  special_type text,
  identity_basis text,
  market_price numeric,
  captured_at date,
  source text,
  price_selection_reason text
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
AS $function$
  SELECT *
  FROM public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(p_root_set_id);
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(uuid) IS
'Production root-set latest-price contract backed by Price Storage V2 for edition-specific current prices. Exact pre-cutover raw-backed function retained as get_pokemon_market_root_set_card_prices_latest_v1_legacy_shadow(uuid).';