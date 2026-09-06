BEGIN;

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
       c.top10_certified
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

COMMIT;
