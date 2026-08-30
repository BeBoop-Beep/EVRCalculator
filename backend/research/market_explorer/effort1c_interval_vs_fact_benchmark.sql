-- Effort 1C representative-DB benchmark fixture.
--
-- Run only AFTER Effort 1B schema deployment and a representative interval
-- backfill. This script creates session-local TEMP tables only. It does not
-- alter production schema and it never reads raw price observations.
-- Execute from psql with \timing on and capture every EXPLAIN result.

\set ON_ERROR_STOP on
\timing on

CREATE TEMP TABLE effort1c_variant_daily_fact ON COMMIT PRESERVE ROWS AS
SELECT
    quality.market_date,
    interval.card_variant_id,
    interval.canonical_card_id,
    interval.set_id,
    set_row.era_id,
    interval.market_price,
    public.market_explorer_rarity_segment(interval.rarity) AS rarity_segment,
    interval.edition,
    interval.printing_type,
    interval.special_type,
    CASE
      WHEN interval.market_price < 10 THEN 'obtainable'
      WHEN interval.market_price < 100 THEN 'intermediate'
      ELSE 'premium'
    END AS price_segment,
    CASE
      WHEN set_row.release_date IS NULL OR quality.market_date < set_row.release_date THEN NULL
      WHEN quality.market_date - set_row.release_date <= 180 THEN 'new'
      WHEN quality.market_date - set_row.release_date <= 730 THEN 'recent'
      WHEN quality.market_date - set_row.release_date <= 1825 THEN 'established'
      ELSE 'legacy'
    END AS release_age_segment
FROM public.pokemon_market_date_quality quality
JOIN public.pokemon_card_variant_market_price_intervals interval
  ON interval.valid_from <= quality.market_date
 AND (interval.valid_to IS NULL OR quality.market_date < interval.valid_to)
JOIN public.sets set_row ON set_row.id = interval.set_id
WHERE quality.tcg = 'pokemon'
  AND quality.status IN ('READY', 'LEGACY_VERIFIED');

CREATE UNIQUE INDEX effort1c_fact_variant_date
 ON effort1c_variant_daily_fact(card_variant_id, market_date);
CREATE INDEX effort1c_fact_set_date
 ON effort1c_variant_daily_fact(set_id, market_date)
 INCLUDE(card_variant_id, canonical_card_id, market_price, rarity_segment);
CREATE INDEX effort1c_fact_era_date
 ON effort1c_variant_daily_fact(era_id, market_date)
 INCLUDE(card_variant_id, canonical_card_id, market_price, rarity_segment);
CREATE INDEX effort1c_fact_date_dimensions
 ON effort1c_variant_daily_fact(market_date, rarity_segment, price_segment, release_age_segment)
 INCLUDE(card_variant_id, canonical_card_id, set_id, market_price);
ANALYZE effort1c_variant_daily_fact;

-- Capture physical cardinality and the real row width before interpreting
-- timing. TEMP relation sizes are session-local and therefore representative
-- of the exact candidate built above.
SELECT count(*) AS fact_rows,
       count(DISTINCT card_variant_id) AS variants,
       count(DISTINCT set_id) AS sets,
       min(market_date) AS first_market_date,
       max(market_date) AS latest_market_date
FROM effort1c_variant_daily_fact;
SELECT 'EFFORT1C_STORAGE ' || json_build_object(
       'factTotalBytes',pg_total_relation_size('effort1c_variant_daily_fact'),
       'factHeapBytes',pg_relation_size('effort1c_variant_daily_fact'),
       'factIndexBytes',pg_indexes_size('effort1c_variant_daily_fact'),
       'intervalTotalBytes',pg_total_relation_size('public.pokemon_card_variant_market_price_intervals'))::text;
SELECT pg_size_pretty(pg_total_relation_size('effort1c_variant_daily_fact')) AS total_size,
       pg_size_pretty(pg_relation_size('effort1c_variant_daily_fact')) AS heap_size,
       pg_size_pretty(pg_indexes_size('effort1c_variant_daily_fact')) AS index_size;

-- Replace the UUID arrays/filters for every row in the acceptance matrix.
-- Run each EXPLAIN twice: the first is cold-ish, the second is subsequent.
-- This interval query and fact query perform the same atomic intersection.

EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
WITH dates AS MATERIALIZED (
  SELECT market_date
  FROM public.pokemon_market_date_quality
  WHERE tcg = 'pokemon' AND status IN ('READY', 'LEGACY_VERIFIED')
), panel AS MATERIALIZED (
  SELECT d.market_date, i.card_variant_id, i.canonical_card_id,
         i.set_id, i.market_price
  FROM dates d
  JOIN public.pokemon_card_variant_market_price_intervals i
    ON i.valid_from <= d.market_date
   AND (i.valid_to IS NULL OR d.market_date < i.valid_to)
  WHERE i.set_id = ANY(ARRAY[
    '8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'::uuid,
    '93212749-ce0e-498e-975e-7d947a3448ce'::uuid
  ])
)
SELECT market_date, count(*) constituent_count, sum(market_price) basket_value
FROM panel GROUP BY market_date ORDER BY market_date;

EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
SELECT market_date, count(*) constituent_count, sum(market_price) basket_value
FROM effort1c_variant_daily_fact
WHERE set_id = ANY(ARRAY[
  '8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'::uuid,
  '93212749-ce0e-498e-975e-7d947a3448ce'::uuid
])
GROUP BY market_date ORDER BY market_date;

-- Second samples preserve ordering for machine parsing: interval1, fact1,
-- interval2, fact2. These are subsequent-cache samples, not mislabeled cold.
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
WITH dates AS MATERIALIZED (
  SELECT market_date FROM public.pokemon_market_date_quality
  WHERE tcg='pokemon' AND status IN ('READY','LEGACY_VERIFIED')
), panel AS MATERIALIZED (
  SELECT d.market_date,i.card_variant_id,i.canonical_card_id,i.set_id,i.market_price
  FROM dates d JOIN public.pokemon_card_variant_market_price_intervals i
    ON i.valid_from<=d.market_date AND (i.valid_to IS NULL OR d.market_date<i.valid_to)
  WHERE i.set_id=ANY(ARRAY['8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'::uuid,
                           '93212749-ce0e-498e-975e-7d947a3448ce'::uuid])
)
SELECT market_date,count(*) constituent_count,sum(market_price) basket_value
FROM panel GROUP BY market_date ORDER BY market_date;

EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
SELECT market_date,count(*) constituent_count,sum(market_price) basket_value
FROM effort1c_variant_daily_fact
WHERE set_id=ANY(ARRAY['8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'::uuid,
                       '93212749-ce0e-498e-975e-7d947a3448ce'::uuid])
GROUP BY market_date ORDER BY market_date;

-- Pokemon option C: canonical ID bridge join. Membership is timeless unless
-- the durable link authority itself gains effective dates, so duplicating it
-- once per variant-date is unnecessary until this plan proves otherwise.
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
SELECT fact.market_date, count(*) constituent_count, sum(fact.market_price) basket_value
FROM effort1c_variant_daily_fact fact
WHERE EXISTS (
  SELECT 1 FROM public.pokemon_card_desirability_links link
  WHERE link.pokemon_canonical_card_id = fact.canonical_card_id
    AND link.pokemon_reference_id = 149
)
GROUP BY fact.market_date ORDER BY fact.market_date;

-- Current-state candidate and Top 25 presentation. The aggregate uses every
-- constituent; LIMIT applies only to the separate display query.
CREATE TEMP TABLE effort1c_variant_current ON COMMIT PRESERVE ROWS AS
SELECT DISTINCT ON (card_variant_id) *
FROM effort1c_variant_daily_fact
ORDER BY card_variant_id, market_date DESC;
CREATE UNIQUE INDEX effort1c_current_variant ON effort1c_variant_current(card_variant_id);
CREATE INDEX effort1c_current_dimensions
 ON effort1c_variant_current(set_id, rarity_segment, price_segment, release_age_segment, market_price DESC)
 INCLUDE(card_variant_id, canonical_card_id, era_id);
ANALYZE effort1c_variant_current;

EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
SELECT count(*) constituent_count, sum(market_price) current_value
FROM effort1c_variant_current;

EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
SELECT card_variant_id, canonical_card_id, set_id, market_price
FROM effort1c_variant_current
ORDER BY market_price DESC, card_variant_id
LIMIT 25;
