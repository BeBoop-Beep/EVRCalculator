-- Batched multi-set per-card daily market constituent layer (read-only RPC).
--
-- WHY THIS EXISTS
-- ===============
-- `get_pokemon_set_daily_card_constituents` (20260822130000) answers the same
-- question for exactly ONE set. That shape is correct for the Set Market page,
-- which only ever renders one set. It is the wrong shape for Market Explorer,
-- whose queries are defined by a FILTER rather than by a set: "every Special
-- Illustration Rare", "Scarlet & Violet Rare Ultra", "the top ten cards in the
-- whole tracked universe".
--
-- Under the single-set function those queries must fan out one call per
-- contributing set. Measured against production on 2026-08-24, over the full
-- 140-day history:
--
--     Global SIR (all eras)        22 sets    29,131 rows    296.1s
--     Global IR  (all eras)        21 sets    64,115 rows    292.9s
--     Scarlet & Violet SIR         16 sets    22,719 rows    217.6s
--     Sword & Shield Rare Ultra    22 sets    48,416 rows    200.7s
--
-- The cost is dominated by per-call round trips and per-call re-planning, not
-- by the volume of rows returned -- the largest result set is under 65k rows,
-- which is trivial. Each call also re-derives the canonical-card and variant
-- link graph for its set from scratch. Batching lets Postgres build that graph
-- once for the whole requested universe and produce one plan over it.
--
-- WHY A SECOND FUNCTION RATHER THAN CHANGING THE FIRST
-- ---------------------------------------------------
-- The single-set function is depended on by the Set Market pipeline. Widening
-- its signature in place would change a function every existing consumer calls,
-- to no benefit for those consumers. This is additive: nothing that exists
-- today changes behaviour, and the single-set function remains the authority
-- for the single-set page.
--
-- PREDICATE PARITY IS THE WHOLE CONTRACT
-- --------------------------------------
-- Every predicate below is intentionally IDENTICAL to the single-set function's
-- (which in turn mirrors `refresh_pokemon_set_value_daily_history`'s 'standard'
-- scope, 039_fix_set_value_hits_rollup.sql). The ONLY differences are:
--
--   * `set_id = ANY(p_set_ids)` in place of `set_id = p_set_id`;
--   * `cards.set_id` now joins the checklist row's own set rather than a single
--     constant -- required for correctness once more than one set is in scope,
--     because otherwise a card could link to a card record in a DIFFERENT set;
--   * an optional `p_card_ids` pre-filter, so a rarity-filtered query does not
--     compute link graphs and price lookups for cards it will discard; and
--   * `set_id` is returned, so a caller holding several sets can attribute a
--     row without a second lookup.
--
-- If the standard-scope predicates ever change, BOTH this function and
-- `get_pokemon_set_daily_card_constituents` must be updated in the same change.
-- That duplication is the known, deliberate cost recorded in the single-set
-- function's own header, not a new debt introduced here.
--
-- TIMEZONE
-- --------
-- `SET "TimeZone" TO 'America/Phoenix'` is a function attribute here, exactly
-- as it is on the live single-set function (verified via pg_proc.proconfig).
-- `card_variant_price_observations.captured_at` is a bare DATE, so comparing it
-- against the business-day boundary forces an implicit DATE->TIMESTAMPTZ cast
-- that uses the SESSION TimeZone. Without this attribute, every date except the
-- caller's "today" silently resolves to the wrong day's price.
--
-- MISSING-PRICE SEMANTICS
-- -----------------------
-- Unchanged: a canonical card with no qualifying Near Mint observation before a
-- day's boundary contributes NO ROW for that day. It is never zero-filled, and
-- its absence never removes that day's rows for other cards.

BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents(
    p_set_ids UUID[],
    p_start_date DATE,
    p_end_date DATE,
    p_card_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
    canonical_card_id UUID,
    set_id UUID,
    market_date DATE,
    market_price NUMERIC,
    card_variant_id UUID,
    source TEXT,
    captured_at DATE
)
LANGUAGE plpgsql
STABLE
SET "TimeZone" TO 'America/Phoenix'
AS $$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    IF p_set_ids IS NULL OR array_length(p_set_ids, 1) IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a bounded p_start_date/p_end_date';
    END IF;
    IF p_start_date > p_end_date THEN
        RAISE EXCEPTION 'p_start_date (%) must not be after p_end_date (%)', p_start_date, p_end_date;
    END IF;

    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH canonical_checklist AS (
        SELECT
            pcc.id AS pokemon_canonical_card_id,
            pcc.set_id AS pokemon_set_id,
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = ANY(p_set_ids)
          -- Optional narrowing. NULL means "no card filter", which keeps this
          -- function a strict superset of the single-set one.
          AND (p_card_ids IS NULL OR pcc.id = ANY(p_card_ids))
    ),
    canonical_card_links AS (
        -- Identical matching rule to the single-set function: exact API id
        -- match, else fuzzy name+number match. The set join is now per-row.
        SELECT DISTINCT
            cc.pokemon_canonical_card_id,
            cc.pokemon_set_id,
            c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = cc.pokemon_set_id
         AND (
             c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
             OR (
                 lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) =
                     lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                 AND (
                     coalesce(cc.number, '') = coalesce(c.card_number, '')
                     OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                     OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') =
                         ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                     OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') =
                         ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                 )
             )
         )
    ),
    canonical_variant_links AS (
        SELECT DISTINCT
            ccl.pokemon_canonical_card_id,
            ccl.pokemon_set_id,
            ccl.card_id,
            cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv
          ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id, pokemon_set_id
        FROM canonical_variant_links
    ),
    set_dates AS (
        SELECT generated_day::date AS snapshot_date
        FROM generate_series(p_start_date, p_end_date, interval '1 day') AS generated_day
    )
    SELECT
        lc.pokemon_canonical_card_id AS canonical_card_id,
        lc.pokemon_set_id AS set_id,
        sd.snapshot_date AS market_date,
        latest_price.market_price,
        latest_price.card_variant_id,
        latest_price.source,
        latest_price.captured_at
    FROM set_dates sd
    CROSS JOIN linked_cards lc
    JOIN LATERAL (
        SELECT
            o.market_price,
            cvl.card_variant_id,
            o.source,
            o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = cvl.card_variant_id
        WHERE cvl.pokemon_canonical_card_id = lc.pokemon_canonical_card_id
          AND o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at < ((sd.snapshot_date + interval '1 day')::timestamp AT TIME ZONE v_set_value_market_day_timezone)
        ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
        LIMIT 1
    ) latest_price ON true
    ORDER BY sd.snapshot_date, lc.pokemon_canonical_card_id;
END;
$$;

COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents(UUID[], DATE, DATE, UUID[]) IS
    'Read-only. Per-card daily Near Mint market values across MANY sets over a '
    'bounded date range, with an optional canonical-card pre-filter. Predicate-for-'
    'predicate identical to get_pokemon_set_daily_card_constituents (and therefore '
    'to the standard scope of refresh_pokemon_set_value_daily_history), differing '
    'only in accepting a set array, joining cards per checklist row rather than to '
    'one constant set, accepting an optional card filter, and returning set_id. '
    'Exists because Market Explorer queries are defined by a filter rather than by '
    'a set, and fanning them out one call per set costs minutes per query. Summing '
    'market_price for a (set_id, market_date) must reconcile to that set and date''s '
    'standard-scope set_value.';

GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(UUID[], DATE, DATE, UUID[]) TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(UUID[], DATE, DATE, UUID[]) FROM PUBLIC;
-- Internal analytics authority, matching the single-set function's posture:
-- only backend service-role callers may execute it.
REVOKE EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(UUID[], DATE, DATE, UUID[]) FROM anon, authenticated;

COMMIT;
