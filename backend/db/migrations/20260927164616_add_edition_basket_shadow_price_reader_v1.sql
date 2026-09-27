BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='12s';

CREATE OR REPLACE FUNCTION public.get_pokemon_edition_basket_card_prices_as_of_v1(
  p_root_set_id uuid,
  p_market_date date,
  p_raw_oracle boolean DEFAULT false
)
RETURNS TABLE(
  canonical_card_id uuid,
  member_set_id uuid,
  market_scope text,
  basket_version integer,
  card_variant_id uuid,
  source_set_id uuid,
  source_policy text,
  source_edition text,
  market_price numeric,
  observed_date date,
  canonical_review_status text
)
LANGUAGE sql
STABLE
SET search_path=''
AS $f$
WITH root AS (
  SELECT s.id
  FROM public.sets s
  JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=s.id
  WHERE s.id=p_root_set_id
    AND s.parent_opening_set_id IS NULL
    AND NOT s.catalog_only
    AND p_market_date IS NOT NULL
), selected_versions AS (
  SELECT DISTINCT ON (v.market_scope)
         v.market_scope,v.basket_version,v.effective_from
  FROM public.pokemon_market_basket_versions_v3 v
  JOIN root r ON r.id=v.root_set_id
  WHERE v.state='APPROVED'
    AND v.market_scope<>'standard'
    AND v.effective_from<=p_market_date
  ORDER BY v.market_scope,v.effective_from DESC,v.basket_version DESC
), nm AS (
  SELECT id
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1
), bindings AS (
  SELECT b.canonical_card_id,b.member_set_id,b.market_scope,b.basket_version,
         b.card_variant_id,
         coalesce(b.source_set_id_override,b.member_set_id) AS source_set_id,
         coalesce(b.source_policy,'same_member_catalog_v1') AS source_policy,
         b.edition AS source_edition,
         c.canonical_review_status
  FROM selected_versions sv
  JOIN public.pokemon_market_basket_bindings_v3 b
    ON b.root_set_id=p_root_set_id
   AND b.market_scope=sv.market_scope
   AND b.basket_version=sv.basket_version
  JOIN public.pokemon_canonical_cards c ON c.id=b.canonical_card_id
  WHERE b.resolution='BOUND'
    AND public.pokemon_market_binding_is_valid_v3(
      b.root_set_id,b.market_scope,b.member_set_id,b.canonical_card_id,b.card_variant_id,
      b.source_set_id_override,b.source_policy,b.identity_basis,b.edition,b.printing_type,b.special_type
    )
), priced AS (
  SELECT b.*,
         price.market_price,
         price.observed_date
  FROM bindings b
  CROSS JOIN nm
  LEFT JOIN LATERAL (
    SELECT ev.market_price,obs.observed_date
    FROM LATERAL (
      SELECT max(least(r.observed_through,p_market_date)) AS observed_date
      FROM public.card_variant_price_observation_ranges_v2 r
      WHERE NOT p_raw_oracle
        AND r.card_variant_id=b.card_variant_id
        AND r.condition_id=nm.id
        AND r.source='TCGPlayer'
        AND r.currency='USD'
        AND r.observed_from<=p_market_date
    ) obs
    JOIN LATERAL (
      SELECT e.market_price
      FROM public.card_variant_price_events_v2 e
      WHERE NOT p_raw_oracle
        AND e.card_variant_id=b.card_variant_id
        AND e.condition_id=nm.id
        AND e.source='TCGPlayer'
        AND e.currency='USD'
        AND e.effective_date<=p_market_date
        AND e.market_price>0
      ORDER BY e.effective_date DESC,e.id DESC
      LIMIT 1
    ) ev ON obs.observed_date IS NOT NULL
    WHERE NOT p_raw_oracle
    UNION ALL
    SELECT raw.market_price,raw.captured_at
    FROM LATERAL (
      SELECT o.market_price,o.captured_at
      FROM public.card_variant_price_observations o
      WHERE p_raw_oracle
        AND o.card_variant_id=b.card_variant_id
        AND o.condition_id=nm.id
        AND o.source='TCGPlayer'
        AND trim(both '"' from upper(coalesce(o.currency,'')))='USD'
        AND o.captured_at<=p_market_date
        AND o.market_price>0
      ORDER BY o.captured_at DESC,o.created_at DESC,o.id DESC
      LIMIT 1
    ) raw
    WHERE p_raw_oracle
  ) price ON true
)
SELECT canonical_card_id,member_set_id,market_scope,basket_version,card_variant_id,
       source_set_id,source_policy,source_edition,market_price,observed_date,canonical_review_status
FROM priced
ORDER BY market_scope,canonical_card_id;
$f$;

REVOKE ALL ON FUNCTION public.get_pokemon_edition_basket_card_prices_as_of_v1(uuid,date,boolean)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_edition_basket_card_prices_as_of_v1(uuid,date,boolean)
TO service_role;

COMMENT ON FUNCTION public.get_pokemon_edition_basket_card_prices_as_of_v1(uuid,date,boolean) IS
  'Shadow reader for approved V3 edition baskets. Uses exact frozen card_variant_id bindings and as-of V2/raw pricing; it does not alter the live history writer or serving path.';

COMMIT;
