-- Versioned filter-first candidate for three-set Market Explorer acceptance.
-- No production authority is replaced by this migration.
BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_candidate(
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
), interval_source AS MATERIALIZED (
 -- Static dimensions are resolved once per interval, before date expansion.
 SELECT fact.observation_id, fact.card_variant_id, fact.canonical_card_id,
        fact.set_id, fact.valid_from, fact.valid_to, fact.market_price,
        lag(fact.valid_from) OVER (
          PARTITION BY fact.card_variant_id ORDER BY fact.valid_from) previous_valid_from,
        lag(fact.market_price) OVER (
          PARTITION BY fact.card_variant_id ORDER BY fact.valid_from) previous_interval_price
 FROM public.pokemon_card_variant_market_price_intervals fact
 WHERE fact.set_id = ANY(p_set_ids)
   AND (p_card_ids IS NULL OR cardinality(p_card_ids) = 0
        OR fact.canonical_card_id = ANY(p_card_ids))
   AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0
        OR public.market_explorer_rarity_segment(fact.rarity) = ANY(p_segment_ids))
   AND (p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1 FROM public.pokemon_card_desirability_links pokemon_link
        WHERE pokemon_link.pokemon_canonical_card_id = fact.canonical_card_id
          AND pokemon_link.pokemon_reference_id = ANY(p_pokemon_ids)))
), panel AS MATERIALIZED (
 SELECT dates.market_date, dates.previous_market_date,
        source.observation_id, source.card_variant_id, source.market_price,
        source.valid_from, source.previous_valid_from, source.previous_interval_price
 FROM interval_source source
 CROSS JOIN date_context dates
 JOIN public.sets set_row ON set_row.id = source.set_id
 WHERE source.valid_from <= dates.market_date
   AND (source.valid_to IS NULL OR dates.market_date < source.valid_to)
   -- Price and release-age dimensions remain point-in-time filters.
   AND (p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0
        OR ('obtainable' = ANY(p_price_segment_ids) AND source.market_price < 10)
        OR ('intermediate' = ANY(p_price_segment_ids)
            AND source.market_price >= 10 AND source.market_price < 100)
        OR ('premium' = ANY(p_price_segment_ids) AND source.market_price >= 100))
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
), observed_dates AS MATERIALIZED (
 SELECT dates.market_date, dates.previous_market_date,
        max(dates.market_date) OVER () latest_market_date
 FROM date_context dates
 JOIN (SELECT DISTINCT panel.market_date FROM panel) observed
   ON observed.market_date = dates.market_date
), eligible AS MATERIALIZED (
 SELECT panel.market_date, count(*)::bigint eligible_universe_count
 FROM panel GROUP BY panel.market_date
), fast_series AS MATERIALIZED (
 -- Static, unranked cohorts avoid a window over expanded variant-date states.
 SELECT panel.market_date,
        count(*)::bigint constituent_count,
        count(*)::bigint eligible_universe_count,
        coalesce(sum(panel.market_price), 0)::numeric basket_value,
        count(*) FILTER (WHERE panel.previous_market_date IS NOT NULL AND (
          panel.valid_from <= panel.previous_market_date OR
          panel.previous_valid_from <= panel.previous_market_date))::bigint common_count,
        coalesce(sum(panel.market_price) FILTER (
          WHERE panel.previous_market_date IS NOT NULL AND (
            panel.valid_from <= panel.previous_market_date OR
            panel.previous_valid_from <= panel.previous_market_date)), 0)::numeric common_current_value,
        coalesce(sum(CASE
          WHEN panel.valid_from <= panel.previous_market_date THEN panel.market_price
          ELSE panel.previous_interval_price END) FILTER (
          WHERE panel.previous_market_date IS NOT NULL AND (
            panel.valid_from <= panel.previous_market_date OR
            panel.previous_valid_from <= panel.previous_market_date)), 0)::numeric common_previous_value
 FROM panel
 WHERE p_top_n IS NULL
   AND (p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0)
   AND (p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids) = 0)
 GROUP BY panel.market_date
), ranked AS MATERIALIZED (
 SELECT panel.market_date, panel.previous_market_date, panel.observation_id,
        panel.card_variant_id, panel.market_price,
        CASE WHEN p_top_n IS NULL THEN NULL::bigint ELSE
          row_number() OVER (PARTITION BY panel.market_date
            ORDER BY panel.market_price DESC, panel.card_variant_id) END market_rank
 FROM panel
 WHERE p_top_n IS NOT NULL
    OR (p_price_segment_ids IS NOT NULL AND cardinality(p_price_segment_ids) > 0)
    OR (p_release_age_cohort_ids IS NOT NULL AND cardinality(p_release_age_cohort_ids) > 0)
), selected AS MATERIALIZED (
 SELECT * FROM ranked
 WHERE p_top_n IS NULL OR market_rank <= p_top_n
), selected_with_previous AS MATERIALIZED (
 SELECT selected.*,
        lag(selected.market_date) OVER (
          PARTITION BY selected.card_variant_id ORDER BY selected.market_date) prev_seen_date,
        lag(selected.market_price) OVER (
          PARTITION BY selected.card_variant_id ORDER BY selected.market_date) prev_selected_price
 FROM selected
), slow_series AS MATERIALIZED (
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
 FROM observed_dates dates
 LEFT JOIN eligible ON eligible.market_date = dates.market_date
 LEFT JOIN selected_with_previous state ON state.market_date = dates.market_date
 WHERE p_top_n IS NOT NULL
    OR (p_price_segment_ids IS NOT NULL AND cardinality(p_price_segment_ids) > 0)
    OR (p_release_age_cohort_ids IS NOT NULL AND cardinality(p_release_age_cohort_ids) > 0)
 GROUP BY dates.market_date, dates.previous_market_date, eligible.eligible_universe_count
), series AS MATERIALIZED (
 SELECT * FROM fast_series UNION ALL SELECT * FROM slow_series
), latest_selected AS MATERIALIZED (
 SELECT panel.market_date, panel.observation_id, panel.card_variant_id,
        panel.market_price,
        row_number() OVER (ORDER BY panel.market_price DESC, panel.card_variant_id) market_rank
 FROM panel JOIN observed_dates dates
   ON dates.market_date = panel.market_date AND dates.market_date = dates.latest_market_date
 WHERE p_top_n IS NULL
 UNION ALL
 SELECT state.market_date, state.observation_id, state.card_variant_id,
        state.market_price, state.market_rank
 FROM selected_with_previous state JOIN observed_dates dates
   ON dates.market_date = state.market_date AND dates.market_date = dates.latest_market_date
 WHERE p_top_n IS NOT NULL
), latest_constituents AS MATERIALIZED (
 SELECT coalesce(jsonb_agg(jsonb_build_object(
   'card_variant_id', latest.card_variant_id,
   'canonical_card_id', fact.canonical_card_id,
   'legacy_card_id', fact.legacy_card_id,
   'set_id', fact.set_id, 'card_name', fact.card_name,
   'card_number', fact.card_number, 'rarity', fact.rarity,
   'edition', fact.edition, 'printing_type', fact.printing_type,
   'special_type', fact.special_type, 'image_url', fact.image_url,
   'market_date', latest.market_date, 'market_price', latest.market_price,
   'rank', latest.market_rank) ORDER BY latest.market_rank), '[]'::jsonb) payload
 FROM latest_selected latest
 JOIN public.pokemon_card_variant_market_price_intervals fact
   ON fact.observation_id = latest.observation_id
)
SELECT series.market_date, series.constituent_count,
       series.eligible_universe_count, series.basket_value,
       series.common_count, series.common_current_value,
       series.common_previous_value,
       CASE WHEN series.market_date = dates.latest_market_date
            THEN latest.payload ELSE NULL END current_constituents
FROM series JOIN observed_dates dates ON dates.market_date = series.market_date
CROSS JOIN latest_constituents latest
ORDER BY series.market_date;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) IS
'Versioned filter-first candidate; static dimensions precede date expansion and static unranked common cohorts use interval predecessor prices.';

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)
 TO service_role;

COMMIT;
