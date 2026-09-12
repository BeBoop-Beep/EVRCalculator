-- Close the SQL-side gap left by the pokemon_market_root_authority pass:
-- pokemon_market_set_value_publication_cohort_v1 was never touched, so any
-- caller that queried it directly for Sep 10+ membership was still subject to
-- its `WHERE c.market_publication_ready` gate and its rollout-override CTE
-- that force-sets market_publication_ready=true for certain sets. Neither of
-- those must ever again decide Sep 10+ Market root membership -- membership
-- is now exclusively public.pokemon_market_root_authority (see
-- 20260911235824_pokemon_market_root_authority.sql). v1 is left
-- unchanged and keeps serving pre-Sep10 historical behavior exactly as it did
-- (some code paths -- _canonical_market_root_cohort for 2026-09-09 -- still
-- read it intentionally and must not be disturbed).
--
-- This migration introduces a new versioned view,
-- pokemon_market_set_value_publication_cohort_v2, rather than replacing v1
-- in-place, because v1's contract (certification-gated membership via a
-- UNION of "current_ready" + "rollout" CTEs) is still the correct, frozen
-- behavior for pre-cutover dates. Replacing it in-place would risk silently
-- changing that frozen historical behavior. v2 is authority-backed at SQL
-- level: every row originates in pokemon_market_root_authority and carries
-- its temporal interval. Callers select the interval containing the requested
-- market date. Certification is nullable annotation only.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

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
    -- Annotation only, retained for shape-compatibility with v1 consumers.
    -- NEVER used by this view (or any Sep10+ caller) to gate row presence.
    coalesce(c.current_market_scope_certified, false) AS market_publication_ready
FROM public.pokemon_market_root_authority a
JOIN public.sets s
    ON s.id = a.set_id
LEFT JOIN public.eras e
    ON e.id = s.era_id
LEFT JOIN public.pokemon_market_root_set_publication_current_certification_v1 c
    ON c.set_id = s.id
   AND c.market_scope = 'standard'
WHERE a.enabled
  AND coalesce(s.catalog_only, false) = false;

COMMENT ON VIEW public.pokemon_market_set_value_publication_cohort_v2 IS
    'Authority-backed set + current-certification annotation projection for '
    'Sep 10, 2026+ Market publication. Every row originates in the temporal '
    'pokemon_market_root_authority table; certification is nullable annotation '
    'and never a membership gate. Callers constrain the authority interval. '
    'pokemon_market_set_value_publication_cohort_v1 remains unchanged and is '
    'the frozen authority for pre-2026-09-10 historical behavior.';

REVOKE ALL ON public.pokemon_market_set_value_publication_cohort_v2 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_set_value_publication_cohort_v2 TO service_role;

COMMIT;
