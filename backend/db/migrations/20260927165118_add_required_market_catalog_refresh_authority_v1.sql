BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='12s';

CREATE OR REPLACE FUNCTION public.list_pokemon_market_required_catalog_refreshes_v1(
  p_as_of date DEFAULT (timezone('America/Phoenix',now()))::date
)
RETURNS TABLE(
  source_set_id uuid,
  source_set_name text,
  canonical_key text,
  dependent_market_count integer,
  required_variant_count integer,
  priced_required_variant_count integer,
  last_source_capture_date date,
  last_source_capture_created_at timestamptz,
  refresh_due boolean
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path=''
AS $f$
WITH nm AS (
  SELECT id
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1
), active_versions AS (
  SELECT DISTINCT ON (v.root_set_id,v.market_scope)
         v.root_set_id,v.market_scope,v.basket_version
  FROM public.pokemon_market_basket_versions_v3 v
  WHERE v.state='APPROVED'
    AND v.effective_from<=p_as_of
  ORDER BY v.root_set_id,v.market_scope,v.effective_from DESC,v.basket_version DESC
), required AS (
  SELECT DISTINCT b.root_set_id,b.market_scope,b.source_set_id_override AS source_set_id,b.card_variant_id
  FROM active_versions av
  JOIN public.pokemon_market_basket_bindings_v3 b
    ON b.root_set_id=av.root_set_id
   AND b.market_scope=av.market_scope
   AND b.basket_version=av.basket_version
  JOIN public.sets src ON src.id=b.source_set_id_override
  WHERE b.resolution='BOUND'
    AND b.source_set_id_override IS NOT NULL
    AND src.catalog_only
    AND public.pokemon_market_binding_is_valid_v3(
      b.root_set_id,b.market_scope,b.member_set_id,b.canonical_card_id,b.card_variant_id,
      b.source_set_id_override,b.source_policy,b.identity_basis,b.edition,b.printing_type,b.special_type
    )
), required_price AS (
  SELECT r.source_set_id,r.root_set_id,r.market_scope,r.card_variant_id,
         EXISTS(
           SELECT 1
           FROM public.card_variant_price_observations o
           CROSS JOIN nm
           WHERE o.card_variant_id=r.card_variant_id
             AND o.condition_id=nm.id
             AND o.source='TCGPlayer'
             AND trim(both '"' from upper(coalesce(o.currency,'')))='USD'
             AND o.captured_at<=p_as_of
             AND o.market_price>0
         ) AS has_price
  FROM required r
), source_refresh AS (
  SELECT s.id AS source_set_id,
         max(o.captured_at) AS last_source_capture_date,
         max(o.created_at) FILTER(WHERE o.captured_at=(
           SELECT max(o2.captured_at)
           FROM public.cards c2
           JOIN public.card_variants v2 ON v2.card_id=c2.id
           JOIN public.card_variant_price_observations o2 ON o2.card_variant_id=v2.id
           CROSS JOIN nm
           WHERE c2.set_id=s.id
             AND o2.condition_id=nm.id
             AND o2.source='TCGPlayer'
             AND trim(both '"' from upper(coalesce(o2.currency,'')))='USD'
             AND o2.captured_at<=p_as_of
             AND o2.market_price>0
         )) AS last_source_capture_created_at
  FROM public.sets s
  JOIN public.cards c ON c.set_id=s.id
  JOIN public.card_variants v ON v.card_id=c.id
  JOIN public.card_variant_price_observations o ON o.card_variant_id=v.id
  CROSS JOIN nm
  WHERE o.condition_id=nm.id
    AND o.source='TCGPlayer'
    AND trim(both '"' from upper(coalesce(o.currency,'')))='USD'
    AND o.captured_at<=p_as_of
    AND o.market_price>0
  GROUP BY s.id
), agg AS (
  SELECT rp.source_set_id,
         count(DISTINCT (rp.root_set_id,rp.market_scope))::integer AS dependent_market_count,
         count(DISTINCT rp.card_variant_id)::integer AS required_variant_count,
         count(DISTINCT rp.card_variant_id) FILTER(WHERE rp.has_price)::integer AS priced_required_variant_count
  FROM required_price rp
  GROUP BY rp.source_set_id
)
SELECT s.id,s.name,s.canonical_key,
       a.dependent_market_count,a.required_variant_count,a.priced_required_variant_count,
       sr.last_source_capture_date,sr.last_source_capture_created_at,
       coalesce(sr.last_source_capture_date<p_as_of,true) AS refresh_due
FROM agg a
JOIN public.sets s ON s.id=a.source_set_id
LEFT JOIN source_refresh sr ON sr.source_set_id=s.id
ORDER BY s.name,s.id;
$f$;

REVOKE ALL ON FUNCTION public.list_pokemon_market_required_catalog_refreshes_v1(date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_pokemon_market_required_catalog_refreshes_v1(date)
TO service_role;

COMMENT ON FUNCTION public.list_pokemon_market_required_catalog_refreshes_v1(date) IS
  'Lists catalog-only source sets required by approved edition baskets and marks them due when no positive Near Mint source observation was captured on the requested market date. This is operational refresh authority only; missing per-card prices remain fail-closed.';

COMMIT;
