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
    -- Observations that fall INSIDE the requested window.
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
    -- The single observation still in force ON p_start_date. Exactly ONE
    -- lookup per card, where the old implementation did one per card per DAY.
    -- Without it a window opening mid-history would lose every card whose last
    -- price predates it.
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
