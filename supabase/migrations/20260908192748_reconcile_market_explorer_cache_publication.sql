BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_query_cache_build_base_metadata(
  p_query_fingerprint text
)
RETURNS TABLE(
  constituent_count bigint,
  detail_count bigint,
  nonnull_instrument_count bigint,
  unique_instrument_count bigint,
  min_rank integer,
  max_rank integer,
  query_contract_version text,
  service_version text,
  instrument_methodology_version text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO ''
AS $function$
  SELECT c.constituent_count,
         count(d.*)::bigint,
         count(d.instrument_id)::bigint,
         count(DISTINCT d.instrument_id)::bigint,
         min(d.rank),
         max(d.rank),
         c.query_contract_version,
         c.service_version,
         c.instrument_methodology_version
  FROM public.pokemon_market_explorer_query_cache c
  LEFT JOIN public.pokemon_market_explorer_query_cache_constituents d
    ON d.query_fingerprint = c.query_fingerprint
  WHERE c.query_fingerprint = p_query_fingerprint
  GROUP BY c.constituent_count, c.query_contract_version, c.service_version,
           c.instrument_methodology_version
$function$;

CREATE OR REPLACE FUNCTION public.prepare_pokemon_market_explorer_query_cache_constituents(
  p_query_fingerprint text,
  p_build_token uuid
)
RETURNS integer
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
  affected integer := 0;
BEGIN
  IF p_query_fingerprint IS NULL
     OR length(p_query_fingerprint) <> 64
     OR p_build_token IS NULL THEN
    RETURN -1;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_query_cache c
    WHERE c.query_fingerprint = p_query_fingerprint
      AND c.status = 'building'
      AND c.build_token = p_build_token
      AND c.build_expires_at > clock_timestamp()
  ) THEN
    RETURN -1;
  END IF;

  UPDATE public.pokemon_market_explorer_query_cache_constituents d
  SET instrument_id = NULL,
      card_variant_id = NULL
  WHERE d.query_fingerprint = p_query_fingerprint
    AND (d.instrument_id IS NOT NULL OR d.card_variant_id IS NOT NULL);

  GET DIAGNOSTICS affected = ROW_COUNT;
  RETURN affected;
END
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_query_cache_build_base_metadata(text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.prepare_pokemon_market_explorer_query_cache_constituents(text,uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_query_cache_build_base_metadata(text)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.prepare_pokemon_market_explorer_query_cache_constituents(text,uuid)
  TO service_role;

COMMIT;
