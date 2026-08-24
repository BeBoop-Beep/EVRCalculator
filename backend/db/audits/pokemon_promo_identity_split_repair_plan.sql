-- Read-only audit and repair planner for promo names whose embedded card number
-- disappeared upstream: "Name - NNN (Qualifier)" -> "Name(Qualifier)".
--
-- This file intentionally contains no INSERT, UPDATE, DELETE, MERGE, DDL, or
-- function calls.  The transaction mode makes accidental writes fail closed.

BEGIN TRANSACTION READ ONLY;

-- Cohort audit across every set.  Only compact-name cards carrying at least
-- one observation enter the cohort.  A repair is eligible only when
-- match_count=1.  Counts are always derived from live rows.
WITH normalized_cards AS (
    SELECT
        c.*,
        s.canonical_key,
        s.name AS set_name,
        lower(regexp_replace(
            trim(regexp_replace(
                c.name,
                '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*([(].*)$',
                '\2'
            )),
            '[[:space:]]+[(]',
            '('
        )) AS normalized_name,
        coalesce(nullif(regexp_replace(
            split_part(lower(trim(coalesce(c.card_number, ''))), '/', 1),
            '^0+',
            ''
        ), ''), '0') AS normalized_number,
        c.name ~ '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*[(]'
            AS historical_format
    FROM public.cards c
    JOIN public.sets s ON s.id = c.set_id
), historical AS (
    SELECT * FROM normalized_cards WHERE historical_format
), cohort AS (
    SELECT n.*
    FROM normalized_cards n
    WHERE NOT n.historical_format
      AND n.name ~ '[(]'
      AND EXISTS (
          SELECT 1
          FROM public.card_variants v
          JOIN public.card_variant_price_observations o ON o.card_variant_id = v.id
          WHERE v.card_id = n.id
      )
), candidate_counts AS (
    SELECT
        n.id,
        n.set_id,
        n.canonical_key,
        n.set_name,
        count(h.id) AS match_count
    FROM cohort n
    LEFT JOIN historical h USING (set_id, normalized_name, normalized_number)
    GROUP BY n.id, n.set_id, n.canonical_key, n.set_name
)
SELECT
    cc.set_id,
    cc.canonical_key,
    cc.set_name,
    count(*) AS cohort_cards,
    count(*) FILTER (WHERE match_count = 1) AS one_to_one,
    count(*) FILTER (WHERE match_count > 1) AS ambiguous,
    count(*) FILTER (WHERE match_count = 0) AS unmatched
FROM candidate_counts cc
GROUP BY cc.set_id, cc.canonical_key, cc.set_name
HAVING count(*) FILTER (WHERE match_count = 1) > 0
ORDER BY cc.canonical_key;

-- Exact Nintendo card and variant mapping.  Consumers must reject every row
-- whose card_match_count or variant_match_count is not exactly one.
WITH normalized_cards AS (
    SELECT
        c.*,
        lower(regexp_replace(trim(regexp_replace(
            c.name,
            '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*([(].*)$',
            '\2'
        )), '[[:space:]]+[(]', '(')) AS normalized_name,
        coalesce(nullif(regexp_replace(
            split_part(lower(trim(coalesce(c.card_number, ''))), '/', 1),
            '^0+', ''
        ), ''), '0') AS normalized_number,
        c.name ~ '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*[(]'
            AS historical_format
    FROM public.cards c
    WHERE c.set_id = '78c7f000-9a9e-45ca-8233-8f36030f6019'
), card_candidates AS (
    SELECT
        newer.id AS duplicate_card_id,
        newer.name AS duplicate_name,
        historical.id AS historical_card_id,
        historical.name AS historical_name,
        count(historical.id) OVER (PARTITION BY newer.id) AS card_match_count
    FROM normalized_cards newer
    JOIN normalized_cards historical
      ON historical.historical_format
     AND historical.normalized_name = newer.normalized_name
     AND historical.normalized_number = newer.normalized_number
    WHERE NOT newer.historical_format
      AND EXISTS (
          SELECT 1
          FROM public.card_variants v
          JOIN public.card_variant_price_observations o ON o.card_variant_id = v.id
          WHERE v.card_id = newer.id
      )
), variant_candidates AS (
    SELECT
        cards.*,
        duplicate_variant.id AS duplicate_variant_id,
        historical_variant.id AS historical_variant_id,
        duplicate_variant.printing_type,
        duplicate_variant.special_type,
        duplicate_variant.edition,
        count(historical_variant.id) OVER (PARTITION BY duplicate_variant.id)
            AS variant_match_count
    FROM card_candidates cards
    JOIN public.card_variants duplicate_variant
      ON duplicate_variant.card_id = cards.duplicate_card_id
    LEFT JOIN public.card_variants historical_variant
      ON historical_variant.card_id = cards.historical_card_id
     AND historical_variant.printing_type IS NOT DISTINCT FROM duplicate_variant.printing_type
     AND historical_variant.special_type IS NOT DISTINCT FROM duplicate_variant.special_type
     AND historical_variant.edition IS NOT DISTINCT FROM duplicate_variant.edition
)
SELECT *
FROM variant_candidates
ORDER BY duplicate_name, printing_type, special_type, edition;

-- Daily observation-key collision preview.  A nonzero result prohibits a
-- direct rehome and requires an explicit latest-wins decision before any write.
-- This deliberately examines every observation on the mapped duplicate
-- variants; it has no captured-date filter and no expected-row-count literal.
WITH duplicate_cards AS (
    SELECT newer.id AS duplicate_card_id, historical.id AS historical_card_id
    FROM public.cards newer
    JOIN public.cards historical
      ON historical.set_id = newer.set_id
     AND lower(regexp_replace(trim(regexp_replace(
            historical.name,
            '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*([(].*)$',
            '\2'
        )), '[[:space:]]+[(]', '(')) = lower(regexp_replace(trim(newer.name), '[[:space:]]+[(]', '('))
     AND coalesce(nullif(regexp_replace(split_part(lower(trim(coalesce(historical.card_number, ''))), '/', 1), '^0+', ''), ''), '0')
         = coalesce(nullif(regexp_replace(split_part(lower(trim(coalesce(newer.card_number, ''))), '/', 1), '^0+', ''), ''), '0')
    WHERE newer.set_id = '78c7f000-9a9e-45ca-8233-8f36030f6019'
      AND historical.name ~ '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*[(]'
      AND newer.name !~ '[[:space:]]*-[[:space:]]*[0-9]+(/[0-9]+)?[[:space:]]*[(]'
), variant_map AS (
    SELECT dv.id AS duplicate_variant_id, hv.id AS historical_variant_id
    FROM duplicate_cards c
    JOIN public.card_variants dv ON dv.card_id = c.duplicate_card_id
    JOIN public.card_variants hv
      ON hv.card_id = c.historical_card_id
     AND hv.printing_type IS NOT DISTINCT FROM dv.printing_type
     AND hv.special_type IS NOT DISTINCT FROM dv.special_type
     AND hv.edition IS NOT DISTINCT FROM dv.edition
)
SELECT
    duplicate_observation.id AS duplicate_observation_id,
    historical_observation.id AS conflicting_historical_observation_id
FROM variant_map vm
JOIN public.card_variant_price_observations duplicate_observation
  ON duplicate_observation.card_variant_id = vm.duplicate_variant_id
JOIN public.card_variant_price_observations historical_observation
  ON historical_observation.card_variant_id = vm.historical_variant_id
 AND historical_observation.condition_id = duplicate_observation.condition_id
 AND historical_observation.source = duplicate_observation.source
 AND historical_observation.captured_at = duplicate_observation.captured_at;

-- Proposed write transaction (not implemented or executed here): recreate the
-- same card/variant maps under locks; assert the live card and variant gates;
-- reject any observation or external-identity uniqueness conflict; update only
-- card_variant_id on every observation and external identity selected by the
-- proven duplicate_variant_id map; assert observation IDs and all non-FK values
-- are unchanged; rehome any nonempty FK-dependent tables explicitly; delete
-- duplicate variants/cards only after zero-orphan assertions; then commit.
-- No step may filter observations by market date or assume a row count.

ROLLBACK;
