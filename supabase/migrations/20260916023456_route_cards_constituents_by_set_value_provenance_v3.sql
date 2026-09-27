SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $check$
BEGIN
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[])'::regprocedure)) <> 'c1cc1a6581fd91c63cb0728a8499328e' THEN
    RAISE EXCEPTION 'Concurrent change detected: public card constituent reader changed; revalidate before cutover';
  END IF;
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v3_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'f1429b14ea7f035a287256a487804abc' THEN
    RAISE EXCEPTION 'Concurrent change detected: authority-routed V3 shadow changed; revalidate before cutover';
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
  FROM public.get_pokemon_cards_daily_constituents_v3_shadow(
    p_set_ids, p_start_date, p_end_date, p_card_ids
  );
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) TO postgres, service_role;

COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) IS
'Canonical reusable card-day constituent authority. Routing follows persisted standard Set Value provenance per requested root/day: accepted canonical-root Set Value dates use the same root+eligible-subset canonical as-of price authority; all other dates preserve the previously served legacy-compatible path. Service-role only.';
