BEGIN;

ALTER FUNCTION public.get_pokemon_market_mixed_movers_v1(date,integer)
  RENAME TO get_pokemon_market_mixed_movers_core_v1;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_mixed_movers_v1(
  p_market_date date,
  p_limit integer DEFAULT 50
)
RETURNS jsonb
LANGUAGE sql
VOLATILE
SECURITY INVOKER
SET search_path TO ''
SET statement_timeout TO '90s'
SET lock_timeout TO '2s'
AS $function$
WITH core AS MATERIALIZED (
  SELECT public.get_pokemon_market_mixed_movers_core_v1(
    p_market_date,p_limit
  ) AS a
),
raw_counts AS (
  SELECT
    h.root_count::integer AS card_root_count,
    h.market_count::integer AS card_market_count
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
  WHERE h.market_date=p_market_date
),
serving AS (
  SELECT generation_id
  FROM public.pokemon_market_explorer_surface_serving_v2
  WHERE singleton=1
),
set_counts AS (
  SELECT
    count(DISTINCT c.set_id) FILTER (
      WHERE c.market_key='sealedMarket' AND c.asset='sealed'
    )::integer AS sealed_set_count,
    count(DISTINCT c.set_id)::integer AS market_set_count
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  JOIN serving s USING(generation_id)
  WHERE c.market_key IN ('raw','sealedMarket')
    AND c.set_id IS NOT NULL
)
SELECT
  core.a || jsonb_build_object(
    'cardRootCount',coalesce(raw_counts.card_root_count,0),
    'cardMarketCount',coalesce(raw_counts.card_market_count,0),
    'sealedSetCount',coalesce(set_counts.sealed_set_count,0),
    'marketSetCount',coalesce(set_counts.market_set_count,0)
  )
FROM core
LEFT JOIN raw_counts ON true
LEFT JOIN set_counts ON true;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_mixed_movers_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_mixed_movers_v1(date,integer)
  TO service_role;

REVOKE ALL ON FUNCTION public.get_pokemon_market_mixed_movers_core_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_mixed_movers_core_v1(date,integer)
  TO service_role;

COMMIT;
