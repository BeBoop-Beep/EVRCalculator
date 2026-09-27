CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history(
    p_set_id UUID DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_start_date DATE;
    v_end_date DATE;
    v_rows_upserted INTEGER := 0;
BEGIN
    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RAISE NOTICE 'Near Mint condition not found; pokemon_set_value_daily_history refresh skipped.';
        RETURN 0;
    END IF;

    -- Critical optimization: when callers provide explicit bounds, do not scan the
    -- entire observations table to calculate MIN/MAX first.
    IF p_start_date IS NOT NULL AND p_end_date IS NOT NULL THEN
        v_start_date := p_start_date;
        v_end_date := p_end_date;
    ELSE
        SELECT
            COALESCE(p_start_date, MIN(o.captured_at)),
            COALESCE(p_end_date, MAX(o.captured_at))
        INTO v_start_date, v_end_date
        FROM public.card_variant_price_observations o
        JOIN public.card_variants cv
          ON cv.id = o.card_variant_id
        JOIN public.cards c
          ON c.id = cv.card_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND cv.special_type IS NULL
          AND cv.printing_type IN ('holo', 'non-holo')
          AND (p_set_id IS NULL OR c.set_id = p_set_id);
    END IF;

    IF v_start_date IS NULL OR v_end_date IS NULL OR v_start_date > v_end_date THEN
        RETURN 0;
    END IF;

    WITH canonical_counts AS (
        SELECT set_id, count(*)::integer AS total_card_count
        FROM public.pokemon_canonical_cards
        GROUP BY set_id
    ),
    legacy_counts AS (
        SELECT
            set_id,
            count(DISTINCT COALESCE(pokemon_tcg_api_id::text, id::text))::integer AS total_card_count
        FROM public.cards
        GROUP BY set_id
    ),
    total_counts AS (
        SELECT
            s.id AS set_id,
            COALESCE(cc.total_card_count, lc.total_card_count, 0) AS total_card_count
        FROM public.sets s
        LEFT JOIN canonical_counts cc
          ON cc.set_id = s.id
        LEFT JOIN legacy_counts lc
          ON lc.set_id = s.id
        WHERE p_set_id IS NULL OR s.id = p_set_id
    ),
    priced_standard_cards AS (
        SELECT
            c.set_id,
            o.captured_at AS snapshot_date,
            COALESCE(c.pokemon_tcg_api_id::text, c.id::text) AS checklist_card_key,
            MAX(o.market_price) AS card_price
        FROM public.card_variant_price_observations o
        JOIN public.card_variants cv
          ON cv.id = o.card_variant_id
        JOIN public.cards c
          ON c.id = cv.card_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.captured_at BETWEEN v_start_date AND v_end_date
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND cv.special_type IS NULL
          AND cv.printing_type IN ('holo', 'non-holo')
          AND (p_set_id IS NULL OR c.set_id = p_set_id)
        GROUP BY
            c.set_id,
            o.captured_at,
            COALESCE(c.pokemon_tcg_api_id::text, c.id::text)
    ),
    aggregated AS (
        SELECT
            pc.set_id,
            pc.snapshot_date,
            ROUND(SUM(pc.card_price)::numeric, 2) AS set_value,
            COUNT(*)::integer AS priced_card_count,
            MAX(tc.total_card_count)::integer AS total_card_count
        FROM priced_standard_cards pc
        LEFT JOIN total_counts tc
          ON tc.set_id = pc.set_id
        GROUP BY pc.set_id, pc.snapshot_date
    ),
    upserted AS (
        INSERT INTO public.pokemon_set_value_daily_history (
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            total_card_count,
            source
        )
        SELECT
            set_id,
            snapshot_date,
            'standard' AS value_scope,
            set_value,
            priced_card_count,
            COALESCE(total_card_count, 0) AS total_card_count,
            'card_variant_price_observations_near_mint_standard_checklist_snapshot' AS source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            source = EXCLUDED.source,
            updated_at = now()
        RETURNING 1
    )
    SELECT count(*)
    INTO v_rows_upserted
    FROM upserted;

    RETURN COALESCE(v_rows_upserted, 0);
END;
$$;
