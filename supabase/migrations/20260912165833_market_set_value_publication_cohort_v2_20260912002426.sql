CREATE OR REPLACE VIEW public.pokemon_market_set_value_publication_cohort_v2
WITH (security_invoker = true)
AS
SELECT
    s.id AS set_id,
    a.activated_market_date,
    a.deactivated_market_date,
    a.enabled AS authority_enabled,
    s.name AS set_name,
    s.canonical_key,
    e.name AS era_name,
    s.release_date,
    s.logo_image_url,
    s.symbol_image_url,
    'standard'::text AS market_scope,
    c.canonical_market_date,
    c.set_value_certified,
    c.top10_certified,
    c.market_scope_certified,
    c.price_freshness_certified,
    c.current_certification_status,
    c.oldest_component_price_date,
    c.newest_component_price_date,
    c.coverage_pct,
    coalesce(c.current_market_scope_certified, false) AS market_publication_ready
FROM public.pokemon_market_root_authority a
JOIN public.sets s ON s.id = a.set_id
LEFT JOIN public.eras e ON e.id = s.era_id
LEFT JOIN public.pokemon_market_root_set_publication_current_certification_v1 c
    ON c.set_id = s.id
   AND c.market_scope = 'standard'
WHERE a.enabled
  AND coalesce(s.catalog_only, false) = false;

COMMENT ON VIEW public.pokemon_market_set_value_publication_cohort_v2 IS
    'Authority-backed set + current-certification annotation projection for Sep 10, 2026+ Market publication. Every row originates in pokemon_market_root_authority; certification is nullable annotation and never a membership gate. Callers constrain the authority interval.';

REVOKE ALL ON public.pokemon_market_set_value_publication_cohort_v2 FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.pokemon_market_set_value_publication_cohort_v2 TO service_role;

