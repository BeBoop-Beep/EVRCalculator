-- Market Explorer Pass 4: push point-in-time price/release membership, ranking,
-- and common-cohort reduction into Postgres. The API passes only normalized
-- taxonomy values and resolved UUID authorities; no user SQL reaches this RPC.

BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date,
    p_card_ids uuid[] DEFAULT NULL::uuid[],
    p_price_segment_ids text[] DEFAULT NULL::text[],
    p_release_age_cohort_ids text[] DEFAULT NULL::text[],
    p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
    market_date date,
    constituent_count bigint,
    eligible_universe_count bigint,
    basket_value numeric,
    common_count bigint,
    common_current_value numeric,
    common_previous_value numeric,
    current_constituents jsonb
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH panel AS MATERIALIZED (
    SELECT c.canonical_card_id, c.set_id, c.market_date, c.market_price
    FROM public.get_pokemon_cards_daily_constituents(
        p_set_ids, p_start_date, p_end_date, p_card_ids
    ) c
    JOIN public.sets s ON s.id = c.set_id
    WHERE
      (
        p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0 OR
        ('obtainable' = ANY(p_price_segment_ids) AND c.market_price < 10) OR
        ('intermediate' = ANY(p_price_segment_ids) AND c.market_price >= 10 AND c.market_price < 100) OR
        ('premium' = ANY(p_price_segment_ids) AND c.market_price >= 100)
      )
      AND (
        p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids) = 0 OR
        (s.release_date IS NOT NULL AND c.market_date >= s.release_date AND (
          ('new' = ANY(p_release_age_cohort_ids) AND c.market_date - s.release_date <= 180) OR
          ('recent' = ANY(p_release_age_cohort_ids) AND c.market_date - s.release_date BETWEEN 181 AND 730) OR
          ('established' = ANY(p_release_age_cohort_ids) AND c.market_date - s.release_date BETWEEN 731 AND 1825) OR
          ('legacy' = ANY(p_release_age_cohort_ids) AND c.market_date - s.release_date > 1825)
        ))
      )
), ranked AS (
    SELECT p.*,
           row_number() OVER (
             PARTITION BY p.market_date
             ORDER BY p.market_price DESC, p.canonical_card_id
           ) AS market_rank
    FROM panel p
), selected AS MATERIALIZED (
    SELECT * FROM ranked
    WHERE p_top_n IS NULL OR market_rank <= p_top_n
), observed_dates AS (
    SELECT market_date,
           lag(market_date) OVER (ORDER BY market_date) AS previous_market_date,
           max(market_date) OVER () AS latest_market_date
    FROM (SELECT DISTINCT market_date FROM panel) dates
), eligible_counts AS (
    SELECT market_date, count(*) AS eligible_universe_count
    FROM panel GROUP BY market_date
)
SELECT d.market_date,
       count(cur.canonical_card_id)::bigint AS constituent_count,
       coalesce(ec.eligible_universe_count, 0)::bigint,
       coalesce(sum(cur.market_price), 0)::numeric AS basket_value,
       count(prev.canonical_card_id)::bigint AS common_count,
       coalesce(sum(cur.market_price) FILTER (WHERE prev.canonical_card_id IS NOT NULL), 0)::numeric AS common_current_value,
       coalesce(sum(prev.market_price), 0)::numeric AS common_previous_value,
       CASE WHEN d.market_date = d.latest_market_date THEN
         coalesce(jsonb_agg(jsonb_build_object(
           'canonical_card_id', cur.canonical_card_id,
           'set_id', cur.set_id,
           'market_date', cur.market_date,
           'market_price', cur.market_price,
           'rank', cur.market_rank
         ) ORDER BY cur.market_rank) FILTER (WHERE cur.canonical_card_id IS NOT NULL), '[]'::jsonb)
       ELSE NULL END AS current_constituents
FROM observed_dates d
JOIN eligible_counts ec ON ec.market_date = d.market_date
LEFT JOIN selected cur ON cur.market_date = d.market_date
LEFT JOIN selected prev
  ON prev.market_date = d.previous_market_date
 AND prev.canonical_card_id = cur.canonical_card_id
GROUP BY d.market_date, d.previous_market_date, d.latest_market_date, ec.eligible_universe_count
ORDER BY d.market_date;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[], date, date, uuid[], text[], text[], integer) IS
'Point-in-time Market Explorer card cohort. Filters price/release membership per date, ranks after filtering, and returns chain-link aggregates plus only the latest selected basket.';

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[], date, date, uuid[], text[], text[], integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[], date, date, uuid[], text[], text[], integer) TO service_role;

COMMIT;
