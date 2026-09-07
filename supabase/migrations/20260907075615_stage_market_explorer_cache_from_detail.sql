BEGIN;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_query_cache_build_from_detail(
  p_query_fingerprint text,
  p_build_token uuid,
  p_computed_from date,
  p_computed_through date,
  p_series_payload jsonb,
  p_current_value numeric,
  p_constituent_count bigint,
  p_eligible_universe_count bigint
)
RETURNS boolean
LANGUAGE plpgsql
SET search_path TO ''
SET statement_timeout TO '300s'
AS $function$
DECLARE
  staged_fingerprint text;
  detail_count bigint;
  detail_payload jsonb;
BEGIN
  IF p_query_fingerprint IS NULL
     OR length(p_query_fingerprint) <> 64
     OR p_build_token IS NULL
     OR p_constituent_count IS NULL
     OR p_constituent_count < 0 THEN
    RETURN false;
  END IF;

  SELECT count(*), coalesce(jsonb_agg(c.item ORDER BY c.rank), '[]'::jsonb)
    INTO detail_count, detail_payload
  FROM public.pokemon_market_explorer_query_cache_constituents c
  WHERE c.query_fingerprint = p_query_fingerprint;

  IF detail_count <> p_constituent_count THEN
    RETURN false;
  END IF;

  PERFORM set_config('market_explorer.skip_constituent_sync', 'on', true);

  UPDATE public.pokemon_market_explorer_query_cache
  SET computed_from = p_computed_from,
      computed_through = p_computed_through,
      series_payload = p_series_payload,
      current_value = p_current_value,
      constituent_count = p_constituent_count,
      eligible_universe_count = p_eligible_universe_count,
      current_constituents = detail_payload,
      updated_at = clock_timestamp()
  WHERE query_fingerprint = p_query_fingerprint
    AND status = 'building'
    AND build_token = p_build_token
    AND build_expires_at > clock_timestamp()
  RETURNING query_fingerprint INTO staged_fingerprint;

  RETURN staged_fingerprint IS NOT NULL;
END
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_query_cache_build_from_detail(
  text,uuid,date,date,jsonb,numeric,bigint,bigint
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_query_cache_build_from_detail(
  text,uuid,date,date,jsonb,numeric,bigint,bigint
) TO service_role;

COMMIT;
