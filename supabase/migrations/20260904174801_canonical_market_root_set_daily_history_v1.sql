BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1(
    p_root_set_id uuid,
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
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH root AS (
    SELECT s.id AS root_set_id, s.name AS root_set_name
    FROM public.sets s
    WHERE s.id = p_root_set_id
      AND s.parent_opening_set_id IS NULL
      AND s.catalog_only = false
),
members AS (
    SELECT r.root_set_id, r.root_set_name, r.root_set_id AS member_set_id
    FROM root r
    UNION ALL
    SELECT r.root_set_id, r.root_set_name, child.id
    FROM root r
    JOIN public.sets child
      ON child.parent_opening_set_id = r.root_set_id
     AND child.counts_toward_parent_set_value = true
),
member_counts AS (
    SELECT root_set_id, count(*)::integer AS expected_member_count
    FROM members
    GROUP BY root_set_id
),
scopes AS (
    SELECT DISTINCT latest.set_id, latest.set_name, latest.market_scope
    FROM public.pokemon_market_root_set_value_latest_v1 latest
    JOIN root r ON r.root_set_id = latest.set_id
),
standard_history AS (
    SELECT r.root_set_id AS set_id,
           r.root_set_name AS set_name,
           'standard'::text AS market_scope,
           h.snapshot_date AS market_date,
           round(sum(h.set_value), 2) AS set_value,
           sum(h.total_card_count)::integer AS expected_card_count,
           sum(h.priced_card_count)::integer AS priced_card_count,
           round(sum(h.priced_card_count)::numeric / nullif(sum(h.total_card_count),0)::numeric * 100, 2) AS coverage_pct,
           (
             count(DISTINCT h.set_id) = max(mc.expected_member_count)
             AND sum(h.total_card_count) > 0
             AND sum(h.priced_card_count) = sum(h.total_card_count)
           ) AS certified_on_date,
           'member_standard_history_sum_v1'::text AS source
    FROM root r
    JOIN scopes scope ON scope.set_id = r.root_set_id AND scope.market_scope = 'standard'
    JOIN members m ON m.root_set_id = r.root_set_id
    JOIN member_counts mc ON mc.root_set_id = r.root_set_id
    JOIN public.pokemon_set_value_daily_history h
      ON h.set_id = m.member_set_id
     AND h.value_scope = 'standard'
     AND h.snapshot_date BETWEEN p_start_date AND p_end_date
    GROUP BY r.root_set_id, r.root_set_name, h.snapshot_date
),
eligible_cards AS (
    SELECT m.root_set_id,
           m.root_set_name,
           m.member_set_id,
           pcc.id AS canonical_card_id,
           pcc.rarity
    FROM members m
    JOIN public.pokemon_canonical_cards pcc
      ON pcc.set_id = m.member_set_id
     AND pcc.set_value_eligible = true
),
expected_cards AS (
    SELECT root_set_id, count(DISTINCT canonical_card_id)::integer AS expected_card_count
    FROM eligible_cards
    GROUP BY root_set_id
),
edition_scopes AS (
    SELECT s.set_id, s.set_name, s.market_scope,
           CASE s.market_scope
             WHEN 'first_edition' THEN '1st-edition'
             WHEN 'unlimited' THEN 'unlimited'
             WHEN 'shadowless' THEN 'shadowless'
           END AS edition
    FROM scopes s
    WHERE s.market_scope IN ('first_edition','unlimited','shadowless')
),
market_dates AS (
    SELECT q.market_date
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg = 'pokemon'
      AND q.status IN ('READY','LEGACY_VERIFIED')
      AND q.market_date BETWEEN p_start_date AND p_end_date
),
edition_grid AS (
    SELECT es.set_id, es.set_name, es.market_scope, es.edition, d.market_date
    FROM edition_scopes es
    CROSS JOIN market_dates d
),
edition_candidates AS (
    SELECT g.set_id,
           g.set_name,
           g.market_scope,
           g.market_date,
           ec.canonical_card_id,
           fact.card_variant_id,
           fact.market_price,
           row_number() OVER (
             PARTITION BY g.set_id, g.market_scope, g.market_date, ec.canonical_card_id
             ORDER BY
               CASE fact.identity_basis
                 WHEN 'explicit_legacy_identity_link' THEN 0
                 WHEN 'parent_pokemon_tcg_api_id' THEN 1
                 WHEN 'variant_pokemon_tcg_api_id' THEN 2
                 WHEN 'normalized_name_number_fallback' THEN 3
                 ELSE 9
               END,
               CASE WHEN fact.special_type IS NULL OR fact.special_type = '' THEN 0 ELSE 1 END,
               CASE
                 WHEN ec.rarity IN ('Common','Uncommon') AND fact.printing_type = 'non-holo' THEN 0
                 WHEN ec.rarity IN ('Common','Uncommon') AND fact.printing_type = 'holo' THEN 1
                 WHEN ec.rarity IN ('Common','Uncommon') AND fact.printing_type = 'reverse-holo' THEN 2
                 WHEN fact.printing_type = 'holo' THEN 0
                 WHEN fact.printing_type = 'non-holo' THEN 1
                 WHEN fact.printing_type = 'reverse-holo' THEN 2
                 ELSE 9
               END,
               fact.source_date DESC,
               fact.card_variant_id
           ) AS selection_rank
    FROM edition_grid g
    JOIN eligible_cards ec ON ec.root_set_id = g.set_id
    JOIN public.pokemon_card_variant_market_price_intervals fact
      ON fact.set_id = ec.member_set_id
     AND fact.canonical_card_id = ec.canonical_card_id
     AND fact.edition = g.edition
     AND fact.valid_from <= g.market_date
     AND (fact.valid_to IS NULL OR g.market_date < fact.valid_to)
),
edition_selected AS (
    SELECT *
    FROM edition_candidates
    WHERE selection_rank = 1
),
edition_history AS (
    SELECT g.set_id,
           g.set_name,
           g.market_scope,
           g.market_date,
           round(coalesce(sum(sel.market_price),0),2) AS set_value,
           max(ec.expected_card_count)::integer AS expected_card_count,
           count(DISTINCT sel.canonical_card_id)::integer AS priced_card_count,
           round(count(DISTINCT sel.canonical_card_id)::numeric / nullif(max(ec.expected_card_count),0)::numeric * 100, 2) AS coverage_pct,
           (
             max(ec.expected_card_count) > 0
             AND count(DISTINCT sel.canonical_card_id) = max(ec.expected_card_count)
           ) AS certified_on_date,
           'variant_interval_edition_exact_v1'::text AS source
    FROM edition_grid g
    JOIN expected_cards ec ON ec.root_set_id = g.set_id
    LEFT JOIN edition_selected sel
      ON sel.set_id = g.set_id
     AND sel.market_scope = g.market_scope
     AND sel.market_date = g.market_date
    GROUP BY g.set_id, g.set_name, g.market_scope, g.market_date
)
SELECT * FROM standard_history
UNION ALL
SELECT * FROM edition_history
ORDER BY market_date, market_scope;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date) IS
'Canonical root-set Set Value history. Standard roots reuse the established per-member standard history and combine qualifying child subsets into the parent. Vintage edition scopes are rebuilt from the Near Mint USD variant interval authority and never mix editions. Each day carries a fail-closed certified_on_date coverage flag; Base remains uncertified until provider edition identities exist.';

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date) TO service_role;

COMMIT;
