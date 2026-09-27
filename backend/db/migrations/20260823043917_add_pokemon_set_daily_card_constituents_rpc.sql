CREATE OR REPLACE FUNCTION public.get_pokemon_set_daily_card_constituents(
    p_set_id UUID,
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE (
    canonical_card_id UUID,
    market_date DATE,
    market_price NUMERIC,
    card_variant_id UUID,
    source TEXT,
    captured_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    IF p_set_id IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_set_daily_card_constituents requires p_set_id';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_set_daily_card_constituents requires a bounded p_start_date/p_end_date';
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
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = p_set_id
    ),
    canonical_card_links AS (
        SELECT DISTINCT
            cc.pokemon_canonical_card_id,
            c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = p_set_id
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
            ccl.card_id,
            cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv
          ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id
        FROM canonical_variant_links
    ),
    set_dates AS (
        SELECT generated_day::date AS snapshot_date
        FROM generate_series(p_start_date, p_end_date, interval '1 day') AS generated_day
    )
    SELECT
        lc.pokemon_canonical_card_id AS canonical_card_id,
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

COMMENT ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE) IS
    'Read-only. Per-card daily Near Mint market values for one set over a bounded date range, using the exact canonical-card matching, variant-eligibility and America/Phoenix business-date rules as the standard scope of refresh_pokemon_set_value_daily_history (039_fix_set_value_hits_rollup.sql). Summing this function''s market_price for a given market_date must reconcile to that scope''s set_value for the same set and date. Feeds the future Cards Market Index (as chain-link constituents) and Market Breadth (as start/end period comparisons) — neither is implemented by this function.';

GRANT EXECUTE ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE) TO service_role;
