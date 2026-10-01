BEGIN;

ALTER FUNCTION public.get_pokemon_market_raw_card_movers_v1(date,integer)
  RENAME TO get_pokemon_market_raw_card_movers_unfiltered_v1;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_raw_card_movers_v1(
  p_market_date date,
  p_limit integer DEFAULT 30
)
RETURNS jsonb
LANGUAGE sql
VOLATILE
SECURITY INVOKER
SET search_path TO ''
SET statement_timeout TO '90s'
SET lock_timeout TO '2s'
AS $function$
WITH authority AS MATERIALIZED (
  SELECT public.get_pokemon_market_raw_card_movers_unfiltered_v1(
    p_market_date,100
  ) AS a
),
movements AS MATERIALIZED (
  SELECT
    x.ordinality::integer AS original_rank,
    x.item AS movement,
    (x.item->>'cardVariantId')::uuid AS card_variant_id,
    (x.item->>'conditionId')::uuid AS condition_id,
    (x.item->>'startDate')::date AS baseline_date,
    (x.item->>'startingPrice')::numeric AS baseline_price
  FROM authority,
  LATERAL jsonb_array_elements(a->'movements')
    WITH ORDINALITY AS x(item,ordinality)
),
quality AS MATERIALIZED (
  SELECT
    m.*,
    pre.pre_price,
    EXISTS (
      SELECT 1
      FROM public.card_variant_price_observations o
      WHERE o.card_variant_id=m.card_variant_id
        AND o.condition_id=m.condition_id
        AND lower(o.source)='tcgplayer'
        AND o.market_price>0
        AND coalesce(o.captured_date,o.captured_at::date)>m.baseline_date
        AND coalesce(o.captured_date,o.captured_at::date)
              <=least(p_market_date,m.baseline_date+3)
        AND pre.pre_price IS NOT NULL
        AND pg_catalog.abs(o.market_price-pre.pre_price)/pre.pre_price<=0.10
    ) AS reverted_to_prebaseline
  FROM movements m
  LEFT JOIN LATERAL (
    SELECT o.market_price::numeric AS pre_price
    FROM public.card_variant_price_observations o
    WHERE o.card_variant_id=m.card_variant_id
      AND o.condition_id=m.condition_id
      AND lower(o.source)='tcgplayer'
      AND o.market_price>0
      AND coalesce(o.captured_date,o.captured_at::date)<m.baseline_date
      AND coalesce(o.captured_date,o.captured_at::date)>=m.baseline_date-3
    ORDER BY
      coalesce(o.captured_date,o.captured_at::date) DESC,
      o.created_at DESC,
      o.id DESC
    LIMIT 1
  ) pre ON true
),
classified AS MATERIALIZED (
  SELECT
    q.*,
    (
      q.pre_price IS NOT NULL
      AND pg_catalog.abs(q.baseline_price-q.pre_price)/q.pre_price>=0.15
      AND q.reverted_to_prebaseline
    ) AS baseline_transient
  FROM quality q
),
filtered AS MATERIALIZED (
  SELECT
    c.*,
    row_number() OVER (ORDER BY c.original_rank)::integer AS published_rank
  FROM classified c
  WHERE NOT c.baseline_transient
  ORDER BY c.original_rank
  LIMIT p_limit
),
aggregated AS (
  SELECT
    coalesce(
      jsonb_agg(
        jsonb_set(
          f.movement,
          '{rank}',
          to_jsonb(f.published_rank),
          true
        )
        ORDER BY f.published_rank
      ),
      '[]'::jsonb
    ) AS movements,
    count(*)::integer AS published_count
  FROM filtered f
),
excluded AS (
  SELECT count(*)::integer AS excluded_count
  FROM classified c
  WHERE c.baseline_transient
)
SELECT
  (a - 'movements' - 'publishedCount')
  || jsonb_build_object(
       'movements',g.movements,
       'publishedCount',g.published_count,
       'baselineQualityGuardVersion','target_baseline_reversion_guard_v1',
       'baselineTransientExcludedCount',e.excluded_count,
       'baselineTransientThresholdPct',15,
       'baselineReversionTolerancePct',10,
       'baselineReversionWindowDays',3
     )
FROM authority
CROSS JOIN aggregated g
CROSS JOIN excluded e;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_raw_card_movers_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_raw_card_movers_v1(date,integer)
  TO service_role;

REVOKE ALL ON FUNCTION public.get_pokemon_market_raw_card_movers_unfiltered_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_raw_card_movers_unfiltered_v1(date,integer)
  TO service_role;

COMMIT;
