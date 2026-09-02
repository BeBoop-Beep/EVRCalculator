BEGIN;

-- Semantics-preserving planner pushdowns for the daily-candidate scope filters:
--   1. PANEL daily-state scan: push s.market_date BETWEEN p_start_date AND p_end_date
--      down into the join against pokemon_market_explorer_card_daily_states.
--   2. PAYLOAD open-interval metadata scan: push o.set_id = ANY(p_set_ids) down into
--      the join against pokemon_card_variant_market_price_intervals.
-- No result-shape or business-logic change; matches production migration
-- 20260902031454_push_down_market_explorer_daily_scope_filters exactly.

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET enable_nestloop TO 'off'
SET statement_timeout TO '300s'
AS $function$
WITH coverage_ok AS MATERIALIZED (
  SELECT count(*) = cardinality(p_set_ids) AS ok
  FROM public.pokemon_market_explorer_card_daily_coverage
  WHERE set_id = ANY(p_set_ids)
    AND computed_through >= p_end_date
),
dates AS MATERIALIZED (
  SELECT q.market_date,
         lag(q.market_date) OVER (ORDER BY q.market_date) AS previous_market_date,
         max(q.market_date) OVER () AS latest_market_date
  FROM public.pokemon_market_date_quality q
  CROSS JOIN coverage_ok c
  WHERE c.ok
    AND q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
    AND q.market_date BETWEEN p_start_date AND p_end_date
),
static_variants AS MATERIALIZED (
  SELECT o.card_variant_id
  FROM public.pokemon_card_variant_market_price_intervals o
  WHERE o.valid_to IS NULL
    AND o.set_id = ANY(p_set_ids)
    AND (p_card_ids IS NULL OR cardinality(p_card_ids) = 0 OR o.canonical_card_id = ANY(p_card_ids))
    AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0 OR public.market_explorer_rarity_segment(o.rarity) = ANY(p_segment_ids))
    AND (
      p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1
        FROM public.pokemon_card_desirability_links l
        WHERE l.pokemon_canonical_card_id = o.canonical_card_id
          AND l.pokemon_reference_id = ANY(p_pokemon_ids)
      )
    )
),
panel AS MATERIALIZED (
  SELECT d.market_date,
         d.previous_market_date,
         s.card_variant_id,
         s.market_price
  FROM dates d
  JOIN public.pokemon_market_explorer_card_daily_states s
    ON s.market_date = d.market_date
   AND s.set_id = ANY(p_set_ids)
   AND s.market_date BETWEEN p_start_date AND p_end_date
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
      OR (
        sr.release_date IS NOT NULL
        AND d.market_date >= sr.release_date
        AND (
          ('new' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date <= 180)
          OR ('recent' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 181 AND 730)
          OR ('established' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 731 AND 1825)
          OR ('legacy' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date > 1825)
        )
      )
    )
),
eligible AS MATERIALIZED (
  SELECT market_date, count(*)::bigint AS n
  FROM panel
  GROUP BY market_date
),
ranked AS MATERIALIZED (
  SELECT p.*,
         row_number() OVER (PARTITION BY market_date ORDER BY market_price DESC, card_variant_id) AS market_rank
  FROM panel p
  WHERE p_top_n IS NOT NULL
),
selected AS MATERIALIZED (
  SELECT p.*, NULL::bigint AS market_rank
  FROM panel p
  WHERE p_top_n IS NULL
  UNION ALL
  SELECT r.*
  FROM ranked r
  WHERE r.market_rank <= p_top_n
),
series AS MATERIALIZED (
  SELECT cur.market_date,
         count(*)::bigint AS constituent_count,
         e.n::bigint AS eligible_universe_count,
         sum(cur.market_price)::numeric AS basket_value,
         count(prev.card_variant_id)::bigint AS common_count,
         coalesce(sum(cur.market_price) FILTER (WHERE prev.card_variant_id IS NOT NULL), 0)::numeric AS common_current_value,
         coalesce(sum(prev.market_price), 0)::numeric AS common_previous_value
  FROM selected cur
  JOIN eligible e ON e.market_date = cur.market_date
  LEFT JOIN selected prev
    ON prev.market_date = cur.previous_market_date
   AND prev.card_variant_id = cur.card_variant_id
  GROUP BY cur.market_date, e.n
),
latest AS MATERIALIZED (
  SELECT s.*,
         CASE
           WHEN s.market_rank IS NULL THEN row_number() OVER (ORDER BY s.market_price DESC, s.card_variant_id)
           ELSE s.market_rank
         END AS final_rank
  FROM selected s
  JOIN dates d
    ON d.market_date = s.market_date
   AND d.market_date = d.latest_market_date
),
payload AS MATERIALIZED (
  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'card_variant_id', l.card_variant_id,
        'canonical_card_id', o.canonical_card_id,
        'legacy_card_id', o.legacy_card_id,
        'set_id', o.set_id,
        'card_name', o.card_name,
        'card_number', o.card_number,
        'rarity', o.rarity,
        'edition', o.edition,
        'printing_type', o.printing_type,
        'special_type', o.special_type,
        'image_url', o.image_url,
        'market_date', l.market_date,
        'market_price', l.market_price,
        'rank', l.final_rank
      ) ORDER BY l.final_rank
    ),
    '[]'::jsonb
  ) AS body
  FROM latest l
  JOIN public.pokemon_card_variant_market_price_intervals o
    ON o.card_variant_id = l.card_variant_id
   AND o.valid_to IS NULL
   AND o.set_id = ANY(p_set_ids)
)
SELECT s.market_date,
       s.constituent_count,
       s.eligible_universe_count,
       s.basket_value,
       s.common_count,
       s.common_current_value,
       s.common_previous_value,
       CASE WHEN s.market_date = d.latest_market_date THEN p.body ELSE NULL END
FROM series s
JOIN dates d ON d.market_date = s.market_date
CROSS JOIN payload p
ORDER BY s.market_date
$function$;

COMMIT;
