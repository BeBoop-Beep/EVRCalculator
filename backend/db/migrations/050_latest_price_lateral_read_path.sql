-- Phase 7 — Repair the production latest-price read path.
--
-- Incident (July 26 audit, reverified before this migration): every consumer of
-- public.card_market_usd_latest_by_condition filters by `variant_id IN (...)`,
-- but the view computed row_number() OVER (PARTITION BY cv.id, cvpo.condition_id)
-- across the *entire* observation history first. A window function is an
-- optimization barrier, so the variant filter could not be pushed down. The live
-- plan was:
--
--     Seq Scan on card_variant_price_observations (14,104,897 rows)
--       -> Sort (work_mem = 3500 kB)
--         -> WindowAgg / row_number()
--
-- With work_mem at 3500 kB the sort spilled to disk, which is how production
-- reached ~8.4 GB of temporary writes and then:
--
--     ERROR: 53100: could not write to file "base/pgsql_tmp/...":
--     No space left on device
--
-- Observed blast radius: the largest set (Ascended Heroes, 753 variants) froze at
-- market date 2026-06-20 while smaller sets kept publishing.
--
-- Fix: rewrite the view to drive from card_variants and resolve the latest row
-- per (variant, condition) with a LATERAL DISTINCT ON, served by the existing
-- index idx_card_variant_price_observations_variant_condition_captured_ on
-- (card_variant_id, condition_id, captured_at DESC). This keeps the variant
-- filter push-downable, so a per-set read touches only that set's variants.
--
-- This is a pure read-path change: no new storage, no backfill, no data movement,
-- and therefore no additional disk pressure on an already disk-constrained
-- instance. Observation history is untouched.
--
-- Semantics are preserved exactly. DISTINCT ON (condition_id) with
-- ORDER BY condition_id, captured_at DESC NULLS LAST, created_at DESC NULLS LAST,
-- id DESC selects the identical row that row_number() = 1 selected, because the
-- window partitioned on (cv.id, cvpo.condition_id) and each card_variant belongs
-- to exactly one card/set. Column names, order, and nullability are unchanged.
--
-- Verified equivalence before applying (old logic vs new, all 19 columns, EXCEPT
-- ALL in both directions):
--   Ascended Heroes (frozen, 753 variants) 1828 rows, 0 diffs
--   Prismatic Evolutions (current)         1612 rows, 0 diffs
--   Journey Together (one day behind)      1087 rows, 0 diffs
--   McDonald's Collection 2011 (small)       60 rows, 0 diffs
--
-- Apply manually in the Supabase SQL editor (repo migrations are applied by
-- hand; the Supabase migration ledger is separate).

BEGIN;

CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition AS
SELECT
    c.id            AS card_id,
    c.set_id,
    s.name          AS set_name,
    c.name          AS card_name,
    c.card_number,
    c.rarity,
    cv.id           AS variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.condition_id,
    cond.name       AS condition,
    latest.market_price,
    latest.high_price,
    latest.low_price,
    latest.currency,
    latest.source,
    latest.captured_at,
    latest.created_at
FROM public.card_variants cv
JOIN public.cards c ON c.id = cv.card_id
LEFT JOIN public.sets s ON s.id = c.set_id
CROSS JOIN LATERAL (
    SELECT DISTINCT ON (cvpo.condition_id)
        cvpo.condition_id,
        cvpo.market_price,
        cvpo.high_price,
        cvpo.low_price,
        cvpo.currency,
        cvpo.source,
        cvpo.captured_at,
        cvpo.created_at
    FROM public.card_variant_price_observations cvpo
    WHERE cvpo.card_variant_id = cv.id
      AND (cvpo.currency = 'USD'::text OR cvpo.currency = '"USD"'::text)
    ORDER BY
        cvpo.condition_id,
        cvpo.captured_at DESC NULLS LAST,
        cvpo.created_at DESC NULLS LAST,
        cvpo.id DESC
) latest
LEFT JOIN public.conditions cond ON cond.id = latest.condition_id;

COMMENT ON VIEW public.card_market_usd_latest_by_condition IS
    'Latest USD price observation per (card_variant, condition). LATERAL DISTINCT ON '
    'so that variant_id filters push down to '
    'idx_card_variant_price_observations_variant_condition_captured_. Do not '
    'reintroduce a row_number() window here: it is an optimization barrier that '
    'forces a full 14M-row sort and exhausts temp disk (see migration 050).';

-- Reclaim disk headroom on the instance that ran out of temp space.
-- idx_price_lookup is byte-identical to
-- idx_card_variant_price_observations_variant_condition_captured_
--   both: btree (card_variant_id, condition_id, captured_at DESC)
-- and has idx_scan = 0 over the lifetime of the database (pg_stat_database.
-- stats_reset IS NULL, so the counter was never cleared). Dropping it frees
-- ~1072 MB and cannot change any plan, because an identical index remains.
DROP INDEX IF EXISTS public.idx_price_lookup;

COMMIT;
