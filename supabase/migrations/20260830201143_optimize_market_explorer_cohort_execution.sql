-- Replace the quadratic selected-current/selected-previous cohort join with
-- one window pass over the selected variant-date states.  This migration is
-- function-only: interval authority and published business data are unchanged.
BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort(
 p_set_ids uuid[], p_start_date date, p_end_date date,
 p_card_ids uuid[] DEFAULT NULL::uuid[],
 p_segment_ids text[] DEFAULT NULL::text[],
 p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
 p_price_segment_ids text[] DEFAULT NULL::text[],
 p_release_age_cohort_ids text[] DEFAULT NULL::text[],
 p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(market_date date, constituent_count bigint,
 eligible_universe_count bigint, basket_value numeric, common_count bigint,
 common_current_value numeric, common_previous_value numeric,
 current_constituents jsonb)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
WITH market_dates AS MATERIALIZED (
 SELECT DISTINCT quality.market_date
 FROM public.pokemon_market_date_quality quality
 WHERE quality.tcg = 'pokemon'
   AND quality.status IN ('READY', 'LEGACY_VERIFIED')
   AND quality.market_date BETWEEN p_start_date AND p_end_date
), date_context AS MATERIALIZED (
 SELECT usable.market_date,
        lag(usable.market_date) OVER (ORDER BY usable.market_date) previous_market_date,
        max(usable.market_date) OVER () latest_market_date
 FROM market_dates usable
), panel AS MATERIALIZED (
 SELECT dates.market_date, dates.previous_market_date,
        fact.card_variant_id, fact.canonical_card_id, fact.set_id,
        fact.market_price
 FROM date_context dates
 JOIN public.pokemon_card_variant_market_price_intervals fact
   ON fact.set_id = ANY(p_set_ids)
  AND fact.valid_from <= dates.market_date
  AND (fact.valid_to IS NULL OR dates.market_date < fact.valid_to)
 JOIN public.sets set_row ON set_row.id = fact.set_id
 WHERE (p_card_ids IS NULL OR cardinality(p_card_ids) = 0
        OR fact.canonical_card_id = ANY(p_card_ids))
   AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0
        OR public.market_explorer_rarity_segment(fact.rarity) = ANY(p_segment_ids))
   AND (p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1
        FROM public.pokemon_card_desirability_links pokemon_link
        WHERE pokemon_link.pokemon_canonical_card_id = fact.canonical_card_id
          AND pokemon_link.pokemon_reference_id = ANY(p_pokemon_ids)))
   AND (p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0
        OR ('obtainable' = ANY(p_price_segment_ids) AND fact.market_price < 10)
        OR ('intermediate' = ANY(p_price_segment_ids)
            AND fact.market_price >= 10 AND fact.market_price < 100)
        OR ('premium' = ANY(p_price_segment_ids) AND fact.market_price >= 100))
   AND (p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids) = 0
        OR (set_row.release_date IS NOT NULL
            AND dates.market_date >= set_row.release_date AND (
          ('new' = ANY(p_release_age_cohort_ids)
           AND dates.market_date - set_row.release_date <= 180)
       OR ('recent' = ANY(p_release_age_cohort_ids)
           AND dates.market_date - set_row.release_date BETWEEN 181 AND 730)
       OR ('established' = ANY(p_release_age_cohort_ids)
           AND dates.market_date - set_row.release_date BETWEEN 731 AND 1825)
       OR ('legacy' = ANY(p_release_age_cohort_ids)
           AND dates.market_date - set_row.release_date > 1825))))
), eligible AS MATERIALIZED (
 SELECT panel.market_date, count(*)::bigint eligible_universe_count
 FROM panel
 GROUP BY panel.market_date
), unranked_selected AS MATERIALIZED (
 -- The full-market path deliberately performs no historical row_number().
 SELECT panel.market_date, panel.previous_market_date,
        panel.card_variant_id, panel.market_price, NULL::bigint market_rank
 FROM panel
 WHERE p_top_n IS NULL
), top_n_ranked AS MATERIALIZED (
 -- Filters are already applied in panel; ranking is never global-universe-first.
 SELECT panel.market_date, panel.previous_market_date,
        panel.card_variant_id, panel.market_price,
        row_number() OVER (
          PARTITION BY panel.market_date
          ORDER BY panel.market_price DESC, panel.card_variant_id) market_rank
 FROM panel
 WHERE p_top_n IS NOT NULL
), selected AS MATERIALIZED (
 SELECT * FROM unranked_selected
 UNION ALL
 SELECT * FROM top_n_ranked WHERE market_rank <= p_top_n
), selected_with_previous AS MATERIALIZED (
 SELECT selected.*,
        lag(selected.market_date) OVER (
          PARTITION BY selected.card_variant_id
          ORDER BY selected.market_date) prev_seen_date,
        lag(selected.market_price) OVER (
          PARTITION BY selected.card_variant_id
          ORDER BY selected.market_date) prev_selected_price
 FROM selected
), series AS MATERIALIZED (
 SELECT dates.market_date,
        count(state.card_variant_id)::bigint constituent_count,
        coalesce(eligible.eligible_universe_count, 0)::bigint eligible_universe_count,
        coalesce(sum(state.market_price), 0)::numeric basket_value,
        count(state.card_variant_id) FILTER (
          WHERE state.prev_seen_date = dates.previous_market_date)::bigint common_count,
        coalesce(sum(state.market_price) FILTER (
          WHERE state.prev_seen_date = dates.previous_market_date), 0)::numeric common_current_value,
        coalesce(sum(state.prev_selected_price) FILTER (
          WHERE state.prev_seen_date = dates.previous_market_date), 0)::numeric common_previous_value
 FROM date_context dates
 LEFT JOIN eligible ON eligible.market_date = dates.market_date
 LEFT JOIN selected_with_previous state ON state.market_date = dates.market_date
 GROUP BY dates.market_date, dates.previous_market_date,
          eligible.eligible_universe_count
), latest_selected AS MATERIALIZED (
 SELECT state.market_date, state.card_variant_id, state.market_price,
        CASE WHEN state.market_rank IS NULL THEN
          row_number() OVER (ORDER BY state.market_price DESC, state.card_variant_id)
        ELSE state.market_rank END market_rank
 FROM selected_with_previous state
 JOIN date_context dates
   ON dates.market_date = state.market_date
  AND dates.market_date = dates.latest_market_date
), latest_constituents AS MATERIALIZED (
 SELECT coalesce(jsonb_agg(jsonb_build_object(
   'card_variant_id', latest.card_variant_id,
   'canonical_card_id', fact.canonical_card_id,
   'legacy_card_id', fact.legacy_card_id,
   'set_id', fact.set_id,
   'card_name', fact.card_name,
   'card_number', fact.card_number,
   'rarity', fact.rarity,
   'edition', fact.edition,
   'printing_type', fact.printing_type,
   'special_type', fact.special_type,
   'image_url', fact.image_url,
   'market_date', latest.market_date,
   'market_price', latest.market_price,
   'rank', latest.market_rank)
   ORDER BY latest.market_rank), '[]'::jsonb) payload
 FROM latest_selected latest
 JOIN public.pokemon_card_variant_market_price_intervals fact
   ON fact.card_variant_id = latest.card_variant_id
  AND fact.valid_from <= latest.market_date
  AND (fact.valid_to IS NULL OR latest.market_date < fact.valid_to)
)
SELECT series.market_date, series.constituent_count,
       series.eligible_universe_count, series.basket_value,
       series.common_count, series.common_current_value,
       series.common_previous_value,
       CASE WHEN series.market_date = dates.latest_market_date
            THEN latest.payload ELSE NULL END current_constituents
FROM series
JOIN date_context dates ON dates.market_date = series.market_date
CROSS JOIN latest_constituents latest
ORDER BY series.market_date;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) IS
'Variant-correct Market Explorer cohort over Near Mint USD intervals; filter-first paths use linear previous-selected windows and latest-only display metadata.';

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)
 TO service_role;

COMMIT;
