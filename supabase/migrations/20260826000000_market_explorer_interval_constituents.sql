-- Market Explorer daily card constituents: replace the per-card-per-day
-- "latest observation before boundary" lookup with a price-validity interval join.
--
-- WHY
-- ---
-- The previous implementation was:
--
--     FROM set_dates sd CROSS JOIN linked_cards lc
--     JOIN LATERAL (SELECT ... FROM card_variant_price_observations o
--                   WHERE ... AND o.captured_at < (sd.snapshot_date + 1 day)
--                   ORDER BY o.captured_at DESC, o.id DESC LIMIT 1) ON true
--
-- i.e. one indexed lookup + top-N sort per (card, date) pair. EXPLAIN on a
-- 120-card / 25-day scope measured 3,000 lateral loops and 53k shared buffer
-- touches, and the cost scales as cards x days: Global SIR (222 x 141) is
-- 31,302 lookups and Global Illustration Rare (492 x 141) is 69,372, which
-- exceeded the statement timeout outright.
--
-- THE EQUIVALENCE
-- ---------------
-- `captured_at` is a DATE, so the old boundary
--     captured_at < ((d + 1 day)::timestamp AT TIME ZONE 'America/Phoenix')
-- is exactly
--     captured_at <= d.
-- Therefore an observation is the answer for every date from its own
-- `captured_at` until the day before the next observation of the same canonical
-- card supersedes it, ordered by (captured_at, id) to reproduce the old
-- ORDER BY captured_at DESC, id DESC tie-break. Computing each card's timeline
-- ONCE with lead() and joining dates to those intervals returns the identical
-- rows without re-deriving the answer per day.
--
-- Semantics deliberately unchanged: Near Mint condition only, positive
-- non-null market_price, non-null captured_at, the same canonical card ->
-- card -> variant linkage and variant filters, the same emitted columns, the
-- same ordering, and the same INNER-join behaviour where a (card, date) pair
-- with no qualifying observation yields no row at all.
--
-- Verified by EXCEPT ALL in both directions on full 7-column rows before this
-- migration was written: 3,000 = 3,000 rows on one set, and 54,003 = 54,003
-- rows across two sets over full history, zero difference either way.
--
-- The previous implementation is RETAINED as
-- `get_pokemon_cards_daily_constituents_lateral` so the parity test can keep
-- comparing against it and so a rollback is a rename, not a restore.

BEGIN;

ALTER FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    RENAME TO get_pokemon_cards_daily_constituents_lateral;

CREATE FUNCTION public.get_pokemon_cards_daily_constituents(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date,
    p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
    canonical_card_id uuid,
    set_id uuid,
    market_date date,
    market_price numeric,
    card_variant_id uuid,
    source text,
    captured_at date
)
LANGUAGE plpgsql
STABLE
SET "TimeZone" TO 'America/Phoenix'
AS $function$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
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
          AND (p_card_ids IS NULL OR pcc.id = ANY(p_card_ids))
    ),
    canonical_card_links AS (
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
    -- Every qualifying observation for the linked variants, ONCE. Bounded at
    -- p_end_date because an observation captured later can never be the answer
    -- for a date at or before it.
    observations AS (
        SELECT
            cvl.pokemon_canonical_card_id,
            cvl.pokemon_set_id,
            cvl.card_variant_id,
            o.id AS observation_id,
            o.market_price,
            o.source,
            o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = cvl.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at <= p_end_date
    ),
    -- Each observation's validity window. The ordering reproduces the old
    -- ORDER BY captured_at DESC, id DESC: two observations captured on the
    -- same day give the earlier id a zero-length interval, so the higher id
    -- wins that day exactly as the old LIMIT 1 did.
    validity AS (
        SELECT
            ob.*,
            lead(ob.captured_at) OVER (
                PARTITION BY ob.pokemon_canonical_card_id
                ORDER BY ob.captured_at, ob.observation_id
            ) AS superseded_from
        FROM observations ob
    )
    SELECT
        v.pokemon_canonical_card_id AS canonical_card_id,
        v.pokemon_set_id AS set_id,
        d.market_date,
        v.market_price,
        v.card_variant_id,
        v.source,
        v.captured_at
    FROM validity v
    JOIN LATERAL (
        SELECT generate_series(
            greatest(v.captured_at, p_start_date),
            least(coalesce(v.superseded_from - 1, p_end_date), p_end_date),
            interval '1 day'
        )::date AS market_date
    ) d ON true
    WHERE coalesce(v.superseded_from - 1, p_end_date) >= p_start_date
    ORDER BY d.market_date, v.pokemon_canonical_card_id;
END;
$function$;

-- Grants mirror the retained implementation exactly: service_role only, never
-- anon or authenticated. The Explorer reaches this through the authenticated
-- Market Explorer API and the backend service, never from a browser.
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    TO service_role;

COMMIT;
