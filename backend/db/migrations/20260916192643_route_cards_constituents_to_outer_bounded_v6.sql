DO $check$
BEGIN
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[])'::regprocedure)) <> '0949cf95d5c96b2e8d993c7fb397f532' THEN
    RAISE EXCEPTION 'public Cards constituent reader changed since validation; aborting v6 cutover';
  END IF;
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v6_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'e52943fd6271e4301e71433490e6e647' THEN
    RAISE EXCEPTION 'v6 shadow changed since validation; aborting v6 cutover';
  END IF;
END;
$check$;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
  canonical_card_id uuid,
  set_id uuid,
  market_date date,
  market_price numeric,
  card_variant_id uuid,
  source text,
  captured_at date
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
SET "TimeZone" = 'America/Phoenix'
AS $function$
  SELECT *
  FROM public.get_pokemon_cards_daily_constituents_v6_shadow(
    p_set_ids,
    p_start_date,
    p_end_date,
    p_card_ids
  );
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) TO postgres, service_role;

COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) IS
'Canonical reusable card-day constituent authority. Same v4 authority/provenance semantics, with the full requested interval additionally split into <=7-day outer segments to bound nonlinear execution time. Service-role only.';
