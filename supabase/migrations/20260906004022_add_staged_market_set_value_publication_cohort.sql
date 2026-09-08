CREATE OR REPLACE VIEW public.pokemon_market_set_value_publication_cohort_v1
WITH (security_invoker = true)
AS
WITH current_ready AS (
    SELECT c.set_id,
           c.set_name,
           s.canonical_key,
           e.name AS era_name,
           s.release_date,
           s.logo_image_url,
           s.symbol_image_url,
           c.market_scope,
           c.canonical_market_date,
           c.market_publication_ready,
           c.current_certification_status,
           0 AS source_priority
    FROM public.pokemon_market_root_set_market_ready_v1 c
    JOIN public.sets s ON s.id = c.set_id
    JOIN public.eras e ON e.id = s.era_id
    WHERE c.market_scope = 'standard'
      AND c.market_publication_ready
), rollout AS (
    SELECT r.set_id,
           r.set_name,
           r.canonical_key,
           r.era_name,
           r.release_date,
           r.logo_image_url,
           r.symbol_image_url,
           'standard'::text AS market_scope,
           c.canonical_market_date,
           true AS market_publication_ready,
           c.current_certification_status,
           1 AS source_priority
    FROM public.pokemon_market_rollout_root_sets_v1 r
    JOIN public.pokemon_market_root_set_publication_current_certification_v1 c
      ON c.set_id = r.set_id
     AND c.market_scope = 'standard'
    WHERE r.activated_market_date <= c.canonical_market_date
      AND coalesce(r.coverage_pct, 0) >= 95
)
SELECT DISTINCT ON (set_id)
       set_id,set_name,canonical_key,era_name,release_date,
       logo_image_url,symbol_image_url,market_scope,canonical_market_date,
       market_publication_ready,current_certification_status
FROM (
    SELECT * FROM current_ready
    UNION ALL
    SELECT * FROM rollout
) u
ORDER BY set_id, source_priority DESC;

REVOKE ALL ON public.pokemon_market_set_value_publication_cohort_v1 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_set_value_publication_cohort_v1 TO service_role;