-- Read-only Price Storage V2 fresh-cycle retirement gate.
--
-- PASS means a real post-2026-09-08 scrape has flowed through the V2 current,
-- event, interval and Market Explorer daily-state paths with exact provenance.
-- This query never changes data and is intentionally stricter than a row-count
-- smoke test: raw observations are append-only scrape receipts, while V2 events
-- are state changes, so event count is not expected to equal raw row count.

WITH fresh_date AS (
  SELECT max(o.captured_at)::date AS market_date
  FROM public.card_variant_price_observations o
  WHERE o.captured_at > DATE '2026-09-08'
),
raw_latest AS (
  SELECT *
  FROM (
    SELECT
      o.id,
      o.card_variant_id,
      o.condition_id,
      coalesce(o.source,'') AS source,
      trim(both '"' from upper(coalesce(o.currency,''))) AS currency,
      o.market_price,
      o.high_price,
      o.low_price,
      o.captured_at,
      o.created_at,
      row_number() OVER (
        PARTITION BY o.card_variant_id,o.condition_id,coalesce(o.source,''),
                     trim(both '"' from upper(coalesce(o.currency,'')))
        ORDER BY o.created_at DESC,o.id DESC
      ) AS rn
    FROM public.card_variant_price_observations o
    CROSS JOIN fresh_date d
    WHERE o.captured_at=d.market_date
  ) ranked
  WHERE rn=1
),
current_cmp AS (
  SELECT
    r.id,
    c.last_observation_id,
    (
      c.last_observation_id=r.id
      AND c.last_observed_date=r.captured_at
      AND c.market_price IS NOT DISTINCT FROM r.market_price
      AND c.high_price IS NOT DISTINCT FROM r.high_price
      AND c.low_price IS NOT DISTINCT FROM r.low_price
    ) AS exact
  FROM raw_latest r
  LEFT JOIN public.card_variant_price_current_v2 c
    ON c.card_variant_id=r.card_variant_id
   AND c.condition_id=r.condition_id
   AND c.source=r.source
   AND c.currency=r.currency
),
event_cmp AS (
  SELECT
    e.id,
    (
      o.id IS NOT NULL
      AND o.captured_at=e.effective_date
      AND o.market_price IS NOT DISTINCT FROM e.market_price
      AND o.high_price IS NOT DISTINCT FROM e.high_price
      AND o.low_price IS NOT DISTINCT FROM e.low_price
    ) AS exact
  FROM public.card_variant_price_events_v2 e
  LEFT JOIN public.card_variant_price_observations o
    ON o.id=e.source_observation_id
  CROSS JOIN fresh_date d
  WHERE e.effective_date=d.market_date
),
near_mint AS (
  SELECT id
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1
),
tracked_sets AS (
  SELECT count(DISTINCT set_id)::integer AS n
  FROM public.pokemon_market_explorer_card_current_metadata
),
interval_expected AS (
  SELECT m.card_variant_id,m.set_id,c.market_price
  FROM public.pokemon_market_explorer_card_current_metadata m
  CROSS JOIN near_mint nm
  JOIN public.card_variant_price_current_v2 c
    ON c.card_variant_id=m.card_variant_id
   AND c.condition_id=nm.id
   AND c.source='TCGPlayer'
   AND c.currency='USD'
   AND c.market_price>0
),
open_intervals AS (
  SELECT card_variant_id,set_id,market_price
  FROM public.pokemon_market_price_intervals_v2_shadow
  WHERE valid_to IS NULL
),
interval_diff AS (
  SELECT coalesce(e.card_variant_id,i.card_variant_id) AS card_variant_id
  FROM interval_expected e
  FULL JOIN open_intervals i USING(card_variant_id,set_id)
  WHERE e.card_variant_id IS NULL
     OR i.card_variant_id IS NULL
     OR e.market_price IS DISTINCT FROM i.market_price
),
coverage AS (
  SELECT
    count(*)::integer AS rows,
    count(*) FILTER (WHERE c.computed_through>=d.market_date)::integer AS through_fresh_date,
    min(c.computed_through) AS min_through,
    max(c.computed_through) AS max_through
  FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
  CROSS JOIN fresh_date d
),
metrics AS (
  SELECT
    d.market_date,
    (SELECT count(*) FROM raw_latest)::bigint AS raw_latest_keys,
    (SELECT count(*) FILTER (WHERE exact) FROM current_cmp)::bigint AS current_exact,
    (SELECT count(*) FILTER (WHERE NOT coalesce(exact,false)) FROM current_cmp)::bigint AS current_diff,
    (SELECT count(*) FROM event_cmp)::bigint AS event_rows,
    (SELECT count(*) FILTER (WHERE exact) FROM event_cmp)::bigint AS event_exact,
    (SELECT count(*) FILTER (WHERE NOT coalesce(exact,false)) FROM event_cmp)::bigint AS event_diff,
    (SELECT count(*) FROM interval_expected)::bigint AS interval_expected,
    (SELECT count(*) FROM open_intervals)::bigint AS interval_actual,
    (SELECT count(*) FROM interval_diff)::bigint AS interval_diff,
    (SELECT n FROM tracked_sets)::integer AS tracked_sets,
    (SELECT rows FROM coverage)::integer AS coverage_rows,
    (SELECT through_fresh_date FROM coverage)::integer AS coverage_through,
    (SELECT min_through FROM coverage) AS coverage_min_through,
    (SELECT max_through FROM coverage) AS coverage_max_through
  FROM fresh_date d
)
SELECT jsonb_build_object(
  'status', CASE
    WHEN market_date IS NOT NULL
     AND raw_latest_keys>0
     AND current_exact=raw_latest_keys
     AND current_diff=0
     AND event_exact=event_rows
     AND event_diff=0
     AND interval_expected=interval_actual
     AND interval_diff=0
     AND coverage_rows=tracked_sets
     AND coverage_through=tracked_sets
    THEN 'PASS'
    ELSE 'BLOCKED'
  END,
  'marketDate',market_date,
  'rawLatestKeys',raw_latest_keys,
  'currentExact',current_exact,
  'currentDiff',current_diff,
  'eventRows',event_rows,
  'eventExact',event_exact,
  'eventDiff',event_diff,
  'intervalExpected',interval_expected,
  'intervalActual',interval_actual,
  'intervalDiff',interval_diff,
  'trackedSets',tracked_sets,
  'coverageRows',coverage_rows,
  'coverageThroughFreshDate',coverage_through,
  'coverageMinThrough',coverage_min_through,
  'coverageMaxThrough',coverage_max_through
) AS price_storage_v2_fresh_cycle_retirement_gate
FROM metrics;