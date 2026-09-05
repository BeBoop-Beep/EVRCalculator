BEGIN;

-- Keep the market-domain readiness projection self-sufficient for the global
-- Market publisher. Visual metadata is included here so the publisher does not
-- need to rejoin the RIP/public-analytics set cohort.
CREATE OR REPLACE VIEW public.pokemon_market_root_set_market_ready_v1
WITH (security_invoker = true)
AS
SELECT s.id AS set_id,
       s.name AS set_name,
       s.canonical_key,
       s.release_date,
       e.name AS era_name,
       c.market_scope,
       c.set_value,
       c.expected_card_count,
       c.priced_card_count,
       c.coverage_pct,
       c.canonical_market_date,
       c.current_market_scope_certified AS market_publication_ready,
       c.current_certification_status,
       c.oldest_component_price_date,
       c.newest_component_price_date,
       c.top10_row_count,
       c.top10_certified,
       s.logo_image_url,
       s.symbol_image_url
FROM public.pokemon_market_root_set_publication_current_certification_v1 c
JOIN public.sets s
  ON s.id = c.set_id
LEFT JOIN public.eras e
  ON e.id = s.era_id
WHERE coalesce(s.catalog_only, false) = false
  AND s.parent_opening_set_id IS NULL;

COMMENT ON VIEW public.pokemon_market_root_set_market_ready_v1 IS
'Market-domain publication eligibility for root Pokemon sets/scopes. Independent of opening simulation and RIP eligibility. market_publication_ready is true only when structural and current-price certification both pass.';

REVOKE ALL ON public.pokemon_market_root_set_market_ready_v1
  FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_set_market_ready_v1
  TO service_role;

-- One service-side call for all Set Value histories needed by the global Market
-- snapshot. The per-root RPC remains the mathematical authority; this wrapper
-- only batches it and therefore cannot diverge on parent/subset or vintage
-- edition semantics.
CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_value_daily_history_bulk_v1(
  p_root_set_ids uuid[],
  p_start_date date,
  p_end_date date
)
RETURNS TABLE(
  set_id uuid,
  set_name text,
  market_scope text,
  market_date date,
  set_value numeric,
  expected_card_count integer,
  priced_card_count integer,
  coverage_pct numeric,
  certified_on_date boolean,
  source text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
SELECT h.*
FROM unnest(coalesce(p_root_set_ids, '{}'::uuid[])) root(set_id)
CROSS JOIN LATERAL public.get_pokemon_market_root_set_value_daily_history_v1(
  root.set_id,
  p_start_date,
  p_end_date
) h
ORDER BY h.set_id, h.market_scope, h.market_date;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_bulk_v1(uuid[],date,date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_bulk_v1(uuid[],date,date)
  TO service_role;

COMMENT ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_bulk_v1(uuid[],date,date) IS
'Batch service-only canonical root-set Set Value history for Market publication. Reuses the per-root parent/subset and edition-aware authority.';

COMMIT;
