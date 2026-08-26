-- Follow-up to 20260826000000: bound the observation scan, and give the
-- observation read a covering index.
--
-- WHAT THE FIRST MIGRATION MISSED
-- ------------------------------
-- The interval model removed the per-card-per-day lookup, but its `observations`
-- CTE was bounded only ABOVE (`captured_at <= p_end_date`). Every call therefore
-- re-read each card's ENTIRE price history, which is wasted work in general and
-- wasted five times over for a chunked caller. Measured cost of that alone:
-- 6,356ms -> 569ms was the win on a 3-set scope, but a 22-set scope still ran
-- 12.2s because it was dragging all history along.
--
-- The window is now bounded on BOTH sides:
--   * `in_range`  - observations captured inside [p_start_date, p_end_date]
--   * `carry_in`  - the ONE observation still in force on p_start_date, found
--                   with a single lookup per card. Without it, a window that
--                   opens mid-history would lose every card whose most recent
--                   price predates the window, which is most of them.
--
-- THE COVERING INDEX
-- ------------------
-- With the algorithm fixed, EXPLAIN showed the remaining cost was pure I/O:
--
--   Index Scan using idx_card_variant_price_observations_variant_condition_captured_
--     (actual time=1.051..23.083 rows=127 loops=492)
--     Buffers: shared hit=46796 read=18219
--
-- 492 loops x 23ms = 11.3s, with 18,219 PHYSICAL reads: the index located the
-- rows but every row needed a random heap fetch for id/market_price/source.
-- `idx_cvpo_variant_condition_captured_covering` carries those three columns in
-- its payload so the scan can stay in the index.
--
-- Built CONCURRENTLY: this table is 6.5 GB / 17.3M rows in production and a
-- plain CREATE INDEX would hold ACCESS EXCLUSIVE for the whole build, blocking
-- even reads. Resulting size 1,570 MB.
--
-- NOTE FOR WHOEVER RUNS THIS ON A FRESH DATABASE: an index-only scan also needs
-- the visibility map, which only VACUUM sets. This table was 47.3% all-visible
-- when the index was added, so `VACUUM (ANALYZE) card_variant_price_observations`
-- belongs with this change rather than being left to autovacuum.

BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents(
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

    SELECT id INTO v_near_mint_condition_id
    FROM public.conditions WHERE lower(name) = 'near mint' ORDER BY id LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH canonical_checklist AS (
        SELECT pcc.id AS pokemon_canonical_card_id, pcc.set_id AS pokemon_set_id,
               pcc.pokemon_tcg_api_card_id, pcc.name, pcc.number, pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = ANY(p_set_ids)
          AND (p_card_ids IS NULL OR pcc.id = ANY(p_card_ids))
    ),
    canonical_card_links AS (
        SELECT DISTINCT cc.pokemon_canonical_card_id, cc.pokemon_set_id, c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c ON c.set_id = cc.pokemon_set_id
         AND (c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
              OR (lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) =
                      lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                  AND (coalesce(cc.number, '') = coalesce(c.card_number, '')
                       OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                       OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                       OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0'))))
    ),
    canonical_variant_links AS (
        SELECT DISTINCT ccl.pokemon_canonical_card_id, ccl.pokemon_set_id, ccl.card_id, cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id, pokemon_set_id FROM canonical_variant_links
    ),
    in_range AS (
        SELECT cvl.pokemon_canonical_card_id, cvl.pokemon_set_id, cvl.card_variant_id,
               o.id AS observation_id, o.market_price, o.source, o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at >= p_start_date AND o.captured_at <= p_end_date
    ),
    carry_in AS (
        SELECT lc.pokemon_canonical_card_id, lc.pokemon_set_id, prior.card_variant_id,
               prior.observation_id, prior.market_price, prior.source, prior.captured_at
        FROM linked_cards lc
        JOIN LATERAL (
            SELECT cvl.card_variant_id, o.id AS observation_id, o.market_price, o.source, o.captured_at
            FROM canonical_variant_links cvl
            JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
            WHERE cvl.pokemon_canonical_card_id = lc.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < p_start_date
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) prior ON true
    ),
    observations AS (
        SELECT * FROM in_range
        UNION ALL
        SELECT * FROM carry_in
    ),
    validity AS (
        SELECT ob.*,
               lead(ob.captured_at) OVER (
                   PARTITION BY ob.pokemon_canonical_card_id
                   ORDER BY ob.captured_at, ob.observation_id
               ) AS superseded_from
        FROM observations ob
    )
    SELECT v.pokemon_canonical_card_id AS canonical_card_id,
           v.pokemon_set_id AS set_id,
           d.market_date, v.market_price, v.card_variant_id, v.source, v.captured_at
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

COMMIT;

-- Outside the transaction: CREATE INDEX CONCURRENTLY cannot run inside one.
-- CREATE INDEX CONCURRENTLY idx_cvpo_variant_condition_captured_covering
--     ON public.card_variant_price_observations (card_variant_id, condition_id, captured_at)
--     INCLUDE (id, market_price, source);
-- VACUUM (ANALYZE) public.card_variant_price_observations;
