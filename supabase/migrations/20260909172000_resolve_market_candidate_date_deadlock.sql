BEGIN;

-- The post-2026-09-09 publication gate needs to evaluate the newly completed
-- scrape date before that date can exist in pokemon_market_date_quality. Using
-- only the latest already-approved quality date here creates a circular
-- dependency: candidate certification cannot advance until quality advances,
-- while quality cannot advance until candidate certification does.
--
-- Treat the latest healthy, promoted, complete scrape batch as the candidate
-- date, while retaining the latest approved market date as a fallback/continuity
-- floor. This view remains service-only; public publication is still controlled
-- by pokemon_market_date_quality and the downstream publication gates.
CREATE OR REPLACE VIEW public.pokemon_market_root_set_publication_current_certification_v1
WITH (security_invoker = true)
AS
WITH approved_date AS (
  SELECT max(q.market_date)::date AS market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
),
healthy_scrape_date AS (
  SELECT max(b.market_date)::date AS market_date
  FROM public.pokemon_scrape_batches b
  WHERE b.status = 'complete'
    AND b.promoted_at IS NOT NULL
    AND coalesce(b.expected_set_count, 0) > 0
    AND coalesce(b.failed_set_count, 0) = 0
    AND coalesce(b.missing_set_count, 0) = 0
    AND b.succeeded_set_count = b.expected_set_count
),
canonical_date AS (
  SELECT CASE
           WHEN s.market_date IS NULL THEN a.market_date
           WHEN a.market_date IS NULL THEN s.market_date
           ELSE greatest(s.market_date, a.market_date)
         END AS market_date
  FROM approved_date a
  CROSS JOIN healthy_scrape_date s
)
SELECT c.*,
       d.market_date AS canonical_market_date,
       (
         c.market_scope_certified
         AND d.market_date IS NOT NULL
         AND c.oldest_component_price_date IS NOT NULL
         AND c.oldest_component_price_date >= d.market_date
         AND c.newest_component_price_date IS NOT NULL
         AND c.newest_component_price_date >= d.market_date
       ) AS price_freshness_certified,
       (
         c.market_scope_certified
         AND d.market_date IS NOT NULL
         AND c.oldest_component_price_date IS NOT NULL
         AND c.oldest_component_price_date >= d.market_date
         AND c.newest_component_price_date IS NOT NULL
         AND c.newest_component_price_date >= d.market_date
       ) AS current_market_scope_certified,
       CASE
         WHEN NOT c.market_scope_certified THEN c.certification_status
         WHEN d.market_date IS NULL THEN 'NO_CANDIDATE_MARKET_DATE'
         WHEN c.oldest_component_price_date IS NULL OR c.newest_component_price_date IS NULL
           THEN 'PRICE_FRESHNESS_UNKNOWN'
         WHEN c.oldest_component_price_date < d.market_date OR c.newest_component_price_date < d.market_date
           THEN 'PRICE_FRESHNESS_STALE'
         ELSE 'CERTIFIED_CURRENT'
       END AS current_certification_status
FROM public.pokemon_market_root_set_publication_certification_v1 c
CROSS JOIN canonical_date d;

COMMENT ON VIEW public.pokemon_market_root_set_publication_current_certification_v1 IS
'Fail-closed candidate/current Market certification layered over structural Set Value/Top 10 certification. The canonical date is the later of the latest healthy promoted complete Pokemon scrape batch and the latest approved Pokemon market date. Public publication remains gated by pokemon_market_date_quality.';

REVOKE ALL ON public.pokemon_market_root_set_publication_current_certification_v1
  FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_set_publication_current_certification_v1
  TO service_role;

COMMIT;
