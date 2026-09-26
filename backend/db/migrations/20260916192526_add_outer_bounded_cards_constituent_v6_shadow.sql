CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v6_shadow(
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
WITH segments AS MATERIALIZED (
  SELECT gs::date AS from_date,
         least(p_end_date, (gs::date + 6)) AS through_date
  FROM generate_series(p_start_date, p_end_date, interval '7 days') AS gs
  WHERE p_start_date IS NOT NULL
    AND p_end_date IS NOT NULL
    AND p_start_date <= p_end_date
), result_rows AS (
  SELECT r.canonical_card_id,
         r.set_id,
         r.market_date,
         r.market_price,
         r.card_variant_id,
         r.source,
         r.captured_at
  FROM segments s
  CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v4_shadow(
    p_set_ids,
    s.from_date,
    s.through_date,
    p_card_ids
  ) AS r
)
SELECT r.canonical_card_id,
       r.set_id,
       r.market_date,
       r.market_price,
       r.card_variant_id,
       r.source,
       r.captured_at
FROM result_rows r
ORDER BY r.market_date, r.canonical_card_id, r.set_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v6_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v6_shadow(uuid[],date,date,uuid[]) TO postgres, service_role;

COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents_v6_shadow(uuid[],date,date,uuid[]) IS
'Non-serving candidate wrapper over v4. Splits the requested date interval into <=7-day whole-request segments to bound nonlinear execution time while preserving exact v4 row semantics and ordering.';
