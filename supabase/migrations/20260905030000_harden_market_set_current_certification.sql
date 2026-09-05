BEGIN;

-- Persist the three deterministic canonical->legacy repairs discovered during
-- the Set Value authority audit. These are intentionally keyed by human-readable
-- set/card identity rather than generated UUIDs so the migration is portable
-- across environments.
WITH repairs(set_name, canonical_name, canonical_number, legacy_name, legacy_number) AS (
  VALUES
    ('Expedition Base Set', 'Mew',      '19', 'Mew (19)',      '019/165'),
    ('Expedition Base Set', 'Venusaur', '30', 'Venusaur (30)', '030/165'),
    ('Expedition Base Set', 'Charizard','6',  'Charizard (6)', '006/165')
), resolved AS (
  SELECT pcc.id AS canonical_card_id,
         c.id AS legacy_card_id,
         r.*
  FROM repairs r
  JOIN public.sets s
    ON s.name = r.set_name
  JOIN public.pokemon_canonical_cards pcc
    ON pcc.set_id = s.id
   AND pcc.name = r.canonical_name
   AND regexp_replace(split_part(lower(coalesce(pcc.number, pcc.printed_number, '')), '/', 1), '^0+', '') =
       regexp_replace(lower(r.canonical_number), '^0+', '')
  JOIN public.cards c
    ON c.set_id = s.id
   AND c.name = r.legacy_name
   AND lower(coalesce(c.card_number,'')) = lower(r.legacy_number)
)
INSERT INTO public.pokemon_canonical_card_legacy_identity_links(
  canonical_card_id,
  legacy_card_id,
  match_basis,
  confidence,
  notes,
  created_at,
  updated_at
)
SELECT canonical_card_id,
       legacy_card_id,
       'exact_set_number_legacy_identity_repair_20260904',
       'verified',
       format(
         'Verified deterministic repair: same set, exact normalized card number, unique legacy card candidate; canonical=%s #%s, legacy=%s #%s. NM freshness remains separately certification-gated.',
         canonical_name, canonical_number, legacy_name, legacy_number
       ),
       now(),
       now()
FROM resolved
ON CONFLICT (canonical_card_id) DO NOTHING;

-- Structural certification proves identity/variant/price/top-10 parity. This
-- layer additionally proves that every constituent price is current for the
-- canonical approved Pokemon market date. It deliberately uses market-date
-- authority rather than wall clock time.
CREATE OR REPLACE VIEW public.pokemon_market_root_set_publication_current_certification_v1
WITH (security_invoker = true)
AS
WITH canonical_date AS (
  SELECT max(market_date)::date AS market_date
  FROM public.pokemon_market_date_quality
  WHERE tcg = 'pokemon'
    AND status IN ('READY','LEGACY_VERIFIED')
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
         WHEN d.market_date IS NULL THEN 'NO_APPROVED_MARKET_DATE'
         WHEN c.oldest_component_price_date IS NULL OR c.newest_component_price_date IS NULL
           THEN 'PRICE_FRESHNESS_UNKNOWN'
         WHEN c.oldest_component_price_date < d.market_date OR c.newest_component_price_date < d.market_date
           THEN 'PRICE_FRESHNESS_STALE'
         ELSE 'CERTIFIED_CURRENT'
       END AS current_certification_status
FROM public.pokemon_market_root_set_publication_certification_v1 c
CROSS JOIN canonical_date d;

COMMENT ON VIEW public.pokemon_market_root_set_publication_current_certification_v1 IS
'Fail-closed current-market certification layered over structural Set Value/Top 10 certification. CERTIFIED_CURRENT requires every constituent price used by the scope to be observed on the latest approved Pokemon market date.';
REVOKE ALL ON public.pokemon_market_root_set_publication_current_certification_v1
  FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_set_publication_current_certification_v1
  TO service_role;

-- Exact card-level blocker inspection for post-scrape verification. The result
-- is deliberately service-only and derives from the same root-set constituent
-- authority as Set Value and Top 10.
CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_current_blockers_v1(
  p_root_set_id uuid
)
RETURNS TABLE(
  root_set_id uuid,
  root_set_name text,
  market_scope text,
  canonical_card_id uuid,
  card_name text,
  card_number text,
  rarity text,
  card_variant_id uuid,
  edition text,
  printing_type text,
  special_type text,
  market_price numeric,
  captured_at date,
  canonical_market_date date,
  price_selection_reason text,
  blocker_code text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
WITH canonical_date AS (
  SELECT max(q.market_date)::date AS market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
), prices AS MATERIALIZED (
  SELECT p.*
  FROM public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) p
), classified AS (
  SELECT p.root_set_id,
         p.root_set_name,
         p.market_scope,
         p.canonical_card_id,
         p.card_name,
         p.card_number,
         p.rarity,
         p.card_variant_id,
         p.edition,
         p.printing_type,
         p.special_type,
         p.market_price,
         p.captured_at::date,
         d.market_date AS canonical_market_date,
         p.price_selection_reason,
         CASE
           WHEN p.card_variant_id IS NULL
                AND coalesce(p.price_selection_reason,'') = 'missing_required_edition_variant'
             THEN 'REQUIRED_VARIANT_IDENTITY_MISSING'
           WHEN p.card_variant_id IS NULL
             THEN 'CANONICAL_PRICE_IDENTITY_MISSING'
           WHEN p.market_price IS NULL
             THEN 'NEAR_MINT_USD_PRICE_MISSING'
           WHEN d.market_date IS NULL
             THEN 'NO_APPROVED_MARKET_DATE'
           WHEN p.captured_at IS NULL
             THEN 'PRICE_FRESHNESS_UNKNOWN'
           WHEN p.captured_at::date < d.market_date
             THEN 'PRICE_FRESHNESS_STALE'
           ELSE NULL
         END AS blocker_code
  FROM prices p
  CROSS JOIN canonical_date d
)
SELECT *
FROM classified
WHERE blocker_code IS NOT NULL
ORDER BY market_scope, blocker_code, card_number, card_name, canonical_card_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_current_blockers_v1(uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_current_blockers_v1(uuid)
  TO service_role;

COMMENT ON FUNCTION public.get_pokemon_market_root_set_current_blockers_v1(uuid) IS
'Service-only diagnostic for canonical Set Value/Top 10 current-market blockers. Uses latest approved Pokemon market date and the same canonical root-set card-price authority as publication.';

COMMIT;
