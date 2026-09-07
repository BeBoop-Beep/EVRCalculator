BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  p_set_ids uuid[], p_start_date date, p_end_date date, p_use_v2 boolean,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET enable_nestloop TO 'off'
SET statement_timeout TO '300s'
AS $function$
WITH dates AS MATERIALIZED (
  SELECT q.market_date,
         lag(q.market_date) OVER (ORDER BY q.market_date) AS previous_market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
    AND q.market_date BETWEEN p_start_date AND p_end_date
),
static_variants AS MATERIALIZED (
  SELECT m.card_variant_id
  FROM public.pokemon_market_explorer_card_current_metadata m
  WHERE m.set_id = ANY(p_set_ids)
    AND (p_card_ids IS NULL OR cardinality(p_card_ids) = 0 OR m.canonical_card_id = ANY(p_card_ids))
    AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0 OR public.market_explorer_rarity_segment(m.rarity) = ANY(p_segment_ids))
    AND (
      p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1 FROM public.pokemon_card_desirability_links l
        WHERE l.pokemon_canonical_card_id = m.canonical_card_id
          AND l.pokemon_reference_id = ANY(p_pokemon_ids)
      )
    )
),
states AS MATERIALIZED (
  SELECT s.market_date, s.set_id, s.card_variant_id, s.market_price
  FROM public.pokemon_market_explorer_card_daily_states_v2_shadow s
  WHERE p_use_v2 AND s.set_id = ANY(p_set_ids)
    AND s.market_date BETWEEN p_start_date AND p_end_date
  UNION ALL
  SELECT s.market_date, s.set_id, s.card_variant_id, s.market_price
  FROM public.pokemon_market_explorer_card_daily_states s
  WHERE NOT p_use_v2 AND s.set_id = ANY(p_set_ids)
    AND s.market_date BETWEEN p_start_date AND p_end_date
),
panel AS MATERIALIZED (
  SELECT d.market_date, d.previous_market_date, s.card_variant_id, s.market_price
  FROM dates d
  JOIN states s ON s.market_date = d.market_date
  JOIN static_variants v ON v.card_variant_id = s.card_variant_id
  JOIN public.sets sr ON sr.id = s.set_id
  WHERE (
      p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0
      OR ('obtainable' = ANY(p_price_segment_ids) AND s.market_price < 10)
      OR ('intermediate' = ANY(p_price_segment_ids) AND s.market_price >= 10 AND s.market_price < 100)
      OR ('premium' = ANY(p_price_segment_ids) AND s.market_price >= 100)
    )
    AND (
      p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids) = 0
      OR (sr.release_date IS NOT NULL AND d.market_date >= sr.release_date AND (
        ('new' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date <= 180)
        OR ('recent' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 181 AND 730)
        OR ('established' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 731 AND 1825)
        OR ('legacy' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date > 1825)
      ))
    )
),
eligible AS MATERIALIZED (
  SELECT p.market_date, count(*)::bigint AS n FROM panel p GROUP BY p.market_date
),
ranked AS MATERIALIZED (
  SELECT p.*, row_number() OVER (
    PARTITION BY p.market_date ORDER BY p.market_price DESC, p.card_variant_id
  ) AS market_rank
  FROM panel p WHERE p_top_n IS NOT NULL
),
selected AS MATERIALIZED (
  SELECT p.*, NULL::bigint AS market_rank FROM panel p WHERE p_top_n IS NULL
  UNION ALL
  SELECT r.* FROM ranked r WHERE r.market_rank <= p_top_n
)
SELECT cur.market_date,
       count(*)::bigint,
       e.n::bigint,
       sum(cur.market_price)::numeric,
       count(prev.card_variant_id)::bigint,
       coalesce(sum(cur.market_price) FILTER (WHERE prev.card_variant_id IS NOT NULL), 0)::numeric,
       coalesce(sum(prev.market_price), 0)::numeric
FROM selected cur
JOIN eligible e ON e.market_date = cur.market_date
LEFT JOIN selected prev
  ON prev.market_date = cur.previous_market_date
 AND prev.card_variant_id = cur.card_variant_id
GROUP BY cur.market_date, e.n
ORDER BY cur.market_date
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer
) TO service_role;

COMMIT;
