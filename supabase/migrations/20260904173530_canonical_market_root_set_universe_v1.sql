BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(
    p_root_set_id uuid DEFAULT NULL::uuid
)
RETURNS TABLE(
    root_set_id uuid,
    root_set_name text,
    member_set_id uuid,
    member_set_name text,
    member_type text,
    market_scope text,
    canonical_card_id uuid,
    card_name text,
    card_number text,
    rarity text,
    canonical_review_status text,
    card_variant_id uuid,
    edition text,
    printing_type text,
    special_type text,
    identity_basis text,
    market_price numeric,
    captured_at date,
    source text,
    price_selection_reason text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH near_mint AS (
    SELECT c.id
    FROM public.conditions c
    WHERE lower(c.name) = 'near mint'
    ORDER BY c.id
    LIMIT 1
),
roots AS (
    SELECT s.id AS root_set_id,
           s.name AS root_set_name
    FROM public.sets s
    WHERE s.parent_opening_set_id IS NULL
      AND s.catalog_only = false
      AND (p_root_set_id IS NULL OR s.id = p_root_set_id)
),
members AS (
    SELECT r.root_set_id,
           r.root_set_name,
           r.root_set_id AS member_set_id,
           r.root_set_name AS member_set_name,
           'main'::text AS member_type
    FROM roots r
    UNION ALL
    SELECT r.root_set_id,
           r.root_set_name,
           child.id,
           child.name,
           coalesce(child.subset_type, 'subset')::text
    FROM roots r
    JOIN public.sets child
      ON child.parent_opening_set_id = r.root_set_id
     AND child.counts_toward_parent_set_value = true
),
eligible_cards AS (
    SELECT m.root_set_id,
           m.root_set_name,
           m.member_set_id,
           m.member_set_name,
           m.member_type,
           pcc.id AS canonical_card_id,
           pcc.name AS card_name,
           coalesce(pcc.number, pcc.printed_number) AS card_number,
           pcc.rarity,
           pcc.canonical_review_status
    FROM members m
    JOIN public.pokemon_canonical_cards pcc
      ON pcc.set_id = m.member_set_id
     AND pcc.set_value_eligible = true
),
edition_evidence AS (
    SELECT ec.root_set_id,
           count(DISTINCT ec.canonical_card_id)::integer AS eligible_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = '1st-edition')::integer AS first_edition_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = 'unlimited')::integer AS unlimited_card_count
    FROM eligible_cards ec
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
    GROUP BY ec.root_set_id
),
root_profiles AS (
    SELECT r.root_set_id,
           r.root_set_name,
           coalesce(ev.eligible_card_count, 0) AS eligible_card_count,
           coalesce(ev.first_edition_card_count, 0) AS first_edition_card_count,
           coalesce(ev.unlimited_card_count, 0) AS unlimited_card_count,
           CASE
             WHEN lower(r.root_set_name) = 'base' THEN 'base_three_printings'
             WHEN coalesce(ev.eligible_card_count, 0) > 0
              AND coalesce(ev.first_edition_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
              AND coalesce(ev.unlimited_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
               THEN 'edition_split'
             ELSE 'standard'
           END AS profile
    FROM roots r
    LEFT JOIN edition_evidence ev ON ev.root_set_id = r.root_set_id
),
root_scopes AS (
    SELECT rp.root_set_id, rp.root_set_name, 'standard'::text AS market_scope
    FROM root_profiles rp
    WHERE rp.profile = 'standard'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'edition_split'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('shadowless'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'base_three_printings'
),
standard_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           'standard'::text AS market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           price.card_variant_id,
           cv.edition,
           cv.printing_type,
           cv.special_type,
           meta.identity_basis,
           price.market_price,
           price.captured_at,
           price.source,
           price.price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope = 'standard'
    LEFT JOIN public.pokemon_canonical_card_market_prices_latest price
      ON price.canonical_card_id = ec.canonical_card_id
     AND price.set_id = ec.member_set_id
    LEFT JOIN public.card_variants cv ON cv.id = price.card_variant_id
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.card_variant_id = price.card_variant_id
     AND meta.canonical_card_id = ec.canonical_card_id
),
edition_variant_latest AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           meta.card_variant_id,
           meta.edition,
           meta.printing_type,
           meta.special_type,
           meta.identity_basis,
           latest.market_price,
           latest.captured_at,
           latest.source,
           row_number() OVER (
             PARTITION BY ec.root_set_id, rs.market_scope, ec.canonical_card_id
             ORDER BY
               CASE meta.identity_basis
                 WHEN 'explicit_legacy_identity_link' THEN 0
                 WHEN 'parent_pokemon_tcg_api_id' THEN 1
                 WHEN 'normalized_name_number_fallback' THEN 2
                 ELSE 9
               END,
               CASE WHEN meta.special_type IS NULL OR meta.special_type = '' THEN 0 ELSE 1 END,
               CASE
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'non-holo' THEN 0
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'holo' THEN 1
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'reverse-holo' THEN 2
                 WHEN meta.printing_type = 'holo' THEN 0
                 WHEN meta.printing_type = 'non-holo' THEN 1
                 WHEN meta.printing_type = 'reverse-holo' THEN 2
                 ELSE 9
               END,
               latest.captured_at DESC NULLS LAST,
               meta.card_variant_id
           ) AS selection_rank
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
     AND (
       (rs.market_scope = 'first_edition' AND meta.edition = '1st-edition')
       OR (rs.market_scope = 'unlimited' AND meta.edition = 'unlimited')
       OR (rs.market_scope = 'shadowless' AND meta.edition = 'shadowless')
     )
    CROSS JOIN near_mint nm
    LEFT JOIN LATERAL (
      SELECT o.market_price, o.captured_at, o.source
      FROM public.card_variant_price_observations o
      WHERE o.card_variant_id = meta.card_variant_id
        AND o.condition_id = nm.id
        AND o.market_price IS NOT NULL
        AND o.market_price > 0
        AND trim(both '"' from upper(coalesce(o.currency,''))) = 'USD'
      ORDER BY o.captured_at DESC NULLS LAST, o.created_at DESC NULLS LAST, o.id DESC
      LIMIT 1
    ) latest ON true
),
edition_selected AS (
    SELECT *
    FROM edition_variant_latest
    WHERE selection_rank = 1
),
edition_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           sel.card_variant_id,
           sel.edition,
           sel.printing_type,
           sel.special_type,
           sel.identity_basis,
           sel.market_price,
           sel.captured_at,
           sel.source,
           CASE
             WHEN sel.card_variant_id IS NULL THEN 'missing_required_edition_variant'
             WHEN sel.market_price IS NULL THEN 'required_edition_variant_missing_nm_price'
             ELSE 'edition_exact_latest_nm_preferred_printing'
           END AS price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    LEFT JOIN edition_selected sel
      ON sel.root_set_id = ec.root_set_id
     AND sel.market_scope = rs.market_scope
     AND sel.canonical_card_id = ec.canonical_card_id
)
SELECT * FROM standard_rows
UNION ALL
SELECT root_set_id, root_set_name, member_set_id, member_set_name, member_type,
       market_scope, canonical_card_id, card_name, card_number, rarity,
       canonical_review_status, card_variant_id, edition, printing_type,
       special_type, identity_basis, market_price, captured_at, source,
       price_selection_reason
FROM edition_rows;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(uuid) IS
'Canonical latest raw-card market universe by root set. Modern roots include child subsets where counts_toward_parent_set_value=true. Vintage roots with strong edition evidence split into first_edition/unlimited. Base is fail-closed into first_edition/shadowless/unlimited scopes so incomplete identity coverage is visible instead of silently mixed. All prices are Near Mint USD and one preferred physical variant is selected per canonical card per scope.';

CREATE OR REPLACE VIEW public.pokemon_market_root_set_value_latest_v1
WITH (security_invoker = true)
AS
SELECT rows.root_set_id AS set_id,
       max(rows.root_set_name) AS set_name,
       rows.market_scope,
       round(coalesce(sum(rows.market_price), 0::numeric), 2) AS set_value,
       count(*)::integer AS expected_card_count,
       count(rows.card_variant_id)::integer AS resolved_variant_count,
       count(rows.market_price)::integer AS priced_card_count,
       round(count(rows.market_price)::numeric / nullif(count(*),0)::numeric * 100, 2) AS coverage_pct,
       min(rows.captured_at) FILTER (WHERE rows.market_price IS NOT NULL) AS oldest_component_price_date,
       max(rows.captured_at) FILTER (WHERE rows.market_price IS NOT NULL) AS newest_component_price_date,
       count(*) FILTER (WHERE rows.canonical_review_status = 'needs_review')::integer AS needs_review_card_count,
       count(*) FILTER (WHERE rows.price_selection_reason = 'missing_required_edition_variant')::integer AS missing_required_variant_count,
       count(*) FILTER (WHERE rows.price_selection_reason = 'required_edition_variant_missing_nm_price')::integer AS missing_price_count,
       CASE
         WHEN count(*) = 0 THEN 'unavailable'
         WHEN count(*) FILTER (WHERE rows.canonical_review_status = 'needs_review') > 0 THEN 'needs_review'
         WHEN count(rows.card_variant_id) < count(*) THEN 'identity_incomplete'
         WHEN count(rows.market_price) = count(*) THEN 'complete'
         WHEN count(rows.market_price)::numeric / nullif(count(*),0)::numeric >= 0.99 THEN 'high_coverage'
         WHEN count(rows.market_price)::numeric / nullif(count(*),0)::numeric >= 0.95 THEN 'partial'
         ELSE 'incomplete'
       END AS quality_status,
       (count(*) > 0
        AND count(*) FILTER (WHERE rows.canonical_review_status = 'needs_review') = 0
        AND count(rows.card_variant_id) = count(*)
        AND count(rows.market_price) = count(*)) AS publishable_100pct
FROM public.get_pokemon_market_root_set_card_prices_latest_v1(NULL::uuid) rows
GROUP BY rows.root_set_id, rows.market_scope;

COMMENT ON VIEW public.pokemon_market_root_set_value_latest_v1 IS
'Strict root-set Set Value audit surface. publishable_100pct is true only when every eligible canonical card resolves to the required physical scope and has a positive Near Mint USD price.';

CREATE OR REPLACE VIEW public.pokemon_market_root_set_top10_latest_v1
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT rows.*,
         row_number() OVER (
           PARTITION BY rows.root_set_id, rows.market_scope
           ORDER BY rows.market_price DESC NULLS LAST, rows.canonical_card_id
         ) AS rank
  FROM public.get_pokemon_market_root_set_card_prices_latest_v1(NULL::uuid) rows
  WHERE rows.market_price IS NOT NULL
)
SELECT r.root_set_id AS set_id,
       r.root_set_name AS set_name,
       r.market_scope,
       r.rank::integer,
       r.member_set_id,
       r.member_set_name,
       r.member_type,
       r.canonical_card_id,
       r.card_variant_id,
       r.card_name,
       r.card_number,
       r.rarity,
       r.edition,
       r.printing_type,
       r.market_price,
       r.captured_at,
       r.source,
       value.quality_status,
       value.publishable_100pct
FROM ranked r
JOIN public.pokemon_market_root_set_value_latest_v1 value
  ON value.set_id = r.root_set_id
 AND value.market_scope = r.market_scope
WHERE r.rank <= 10;

COMMENT ON VIEW public.pokemon_market_root_set_top10_latest_v1 IS
'Top 10 cards ranked from the exact same root-set/scope constituents as canonical Set Value. Modern subset cards compete directly with parent cards. Vintage edition scopes never mix first-edition and unlimited.';

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(uuid) TO service_role;
REVOKE ALL ON public.pokemon_market_root_set_value_latest_v1 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.pokemon_market_root_set_top10_latest_v1 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_set_value_latest_v1 TO service_role;
GRANT SELECT ON public.pokemon_market_root_set_top10_latest_v1 TO service_role;

COMMIT;
