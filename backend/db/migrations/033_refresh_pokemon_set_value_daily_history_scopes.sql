-- Replace the daily Pokemon set value refresh RPC with scoped rollups.
--
-- standard: all priced legacy cards in the set, deduped to one best variant
--           price per card per snapshot day.
-- hits:     the same priced-card layer filtered by canonical cards that have
--           pokemon_card_desirability_links.is_hit_eligible = true.
-- top10:    the top ten priced cards in the set for each snapshot day.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_cards_set_api_for_value_history
    ON public.cards (set_id, pokemon_tcg_api_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_cards_set_api_for_value_history
    ON public.pokemon_canonical_cards (set_id, pokemon_tcg_api_card_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_hit_card_for_value_history
    ON public.pokemon_card_desirability_links (pokemon_canonical_card_id)
    WHERE is_hit_eligible = true;

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

    WITH requested_sets AS (
        SELECT id
        FROM public.sets
        WHERE p_set_id IS NULL OR id = p_set_id
    ),
    tracked_card_variants AS (
        SELECT DISTINCT
            c.set_id,
            c.id AS card_id,
            cv.id AS card_variant_id,
            canonical_match.id AS pokemon_canonical_card_id,
            EXISTS (
                SELECT 1
                FROM public.pokemon_card_desirability_links link
                WHERE link.pokemon_canonical_card_id = canonical_match.id
                  AND link.is_hit_eligible = true
            ) AS is_hit_eligible,
            'card_variants_by_set'::text AS universe_source
        FROM requested_sets s
        JOIN public.cards c
          ON c.set_id = s.id
        JOIN public.card_variants cv
          ON cv.card_id = c.id
        LEFT JOIN LATERAL (
            SELECT pcc.id
            FROM public.pokemon_canonical_cards pcc
            WHERE pcc.set_id = c.set_id
              AND (
                  pcc.pokemon_tcg_api_card_id = cv.pokemon_tcg_api_id
                  OR pcc.pokemon_tcg_api_card_id = c.pokemon_tcg_api_id
                  OR (
                      lower(regexp_replace(coalesce(pcc.name, ''), '[[:space:]]+', ' ', 'g')) =
                          lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                      AND (
                          coalesce(pcc.number, '') = coalesce(c.card_number, '')
                          OR coalesce(pcc.printed_number, '') = coalesce(c.card_number, '')
                          OR ltrim(split_part(coalesce(pcc.number, ''), '/', 1), '0') =
                              ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                          OR ltrim(split_part(coalesce(pcc.printed_number, ''), '/', 1), '0') =
                              ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                      )
                  )
              )
            ORDER BY
                CASE
                    WHEN pcc.pokemon_tcg_api_card_id = cv.pokemon_tcg_api_id THEN 1
                    WHEN pcc.pokemon_tcg_api_card_id = c.pokemon_tcg_api_id THEN 2
                    ELSE 3
                END,
                pcc.id
            LIMIT 1
        ) canonical_match ON true
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    tracked_cards AS (
        SELECT
            set_id,
            card_id,
            bool_or(is_hit_eligible)::boolean AS is_hit_eligible,
            min(universe_source) AS universe_source
        FROM tracked_card_variants
        GROUP BY set_id, card_id
    ),
    observed_bounds AS (
        SELECT
            tcv.set_id,
            min(timezone('utc', o.captured_at)::date) AS first_observation_date,
            max(timezone('utc', o.captured_at)::date) AS latest_observation_date
        FROM tracked_card_variants tcv
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = tcv.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
        GROUP BY tcv.set_id
    ),
    set_dates AS (
        SELECT
            b.set_id,
            generated_day::date AS snapshot_date
        FROM observed_bounds b
        CROSS JOIN LATERAL generate_series(
            greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date)),
            least(coalesce(p_end_date, b.latest_observation_date), b.latest_observation_date),
            interval '1 day'
        ) AS generated_day
        WHERE greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date))
              <= least(coalesce(p_end_date, b.latest_observation_date), b.latest_observation_date)
    ),
    latest_priced_candidates AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            tcv.card_id,
            tcv.is_hit_eligible,
            latest_price.market_price,
            tcv.universe_source
        FROM set_dates sd
        JOIN tracked_card_variants tcv
          ON tcv.set_id = sd.set_id
        JOIN LATERAL (
            SELECT o.market_price
            FROM public.card_variant_price_observations o
            WHERE o.card_variant_id = tcv.card_variant_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL
              AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < ((sd.snapshot_date + interval '1 day') AT TIME ZONE 'UTC')
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) latest_price ON true
    ),
    priced_cards AS (
        SELECT
            set_id,
            snapshot_date,
            card_id,
            bool_or(is_hit_eligible)::boolean AS is_hit_eligible,
            max(market_price) AS card_price,
            min(universe_source) AS universe_source
        FROM latest_priced_candidates
        GROUP BY set_id, snapshot_date, card_id
    ),
    tracked_counts AS (
        SELECT
            set_id,
            count(DISTINCT card_id)::integer AS total_card_count,
            count(DISTINCT card_id) FILTER (WHERE is_hit_eligible)::integer AS hit_card_count
        FROM tracked_cards
        GROUP BY set_id
    ),
    standard_aggregated AS (
        SELECT
            pc.set_id,
            pc.snapshot_date,
            'standard'::text AS value_scope,
            round(sum(pc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            max(tc.total_card_count)::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:standard:' || min(pc.universe_source) AS source
        FROM priced_cards pc
        LEFT JOIN tracked_counts tc
          ON tc.set_id = pc.set_id
        GROUP BY pc.set_id, pc.snapshot_date
    ),
    hits_aggregated AS (
        SELECT
            pc.set_id,
            pc.snapshot_date,
            'hits'::text AS value_scope,
            round(sum(pc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            max(tc.hit_card_count)::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:hits:pokemon_card_desirability_links:' ||
                min(pc.universe_source) AS source
        FROM priced_cards pc
        LEFT JOIN tracked_counts tc
          ON tc.set_id = pc.set_id
        WHERE pc.is_hit_eligible = true
        GROUP BY pc.set_id, pc.snapshot_date
    ),
    ranked_priced_cards AS (
        SELECT
            pc.*,
            row_number() OVER (
                PARTITION BY pc.set_id, pc.snapshot_date
                ORDER BY pc.card_price DESC, pc.card_id
            ) AS price_rank
        FROM priced_cards pc
    ),
    top10_aggregated AS (
        SELECT
            rpc.set_id,
            rpc.snapshot_date,
            'top10'::text AS value_scope,
            round(sum(rpc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            10::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:top10:' || min(rpc.universe_source) AS source
        FROM ranked_priced_cards rpc
        WHERE rpc.price_rank <= 10
        GROUP BY rpc.set_id, rpc.snapshot_date
    ),
    aggregated AS (
        SELECT * FROM standard_aggregated
        UNION ALL
        SELECT * FROM hits_aggregated
        UNION ALL
        SELECT * FROM top10_aggregated
    ),
    scope_candidates AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            scope.value_scope
        FROM set_dates sd
        CROSS JOIN (
            VALUES ('standard'::text), ('hits'::text), ('top10'::text)
        ) AS scope(value_scope)
    ),
    stale_deleted AS (
        DELETE FROM public.pokemon_set_value_daily_history h
        USING scope_candidates sc
        WHERE h.set_id = sc.set_id
          AND h.snapshot_date = sc.snapshot_date
          AND h.value_scope = sc.value_scope
          AND NOT EXISTS (
              SELECT 1
              FROM aggregated a
              WHERE a.set_id = h.set_id
                AND a.snapshot_date = h.snapshot_date
                AND a.value_scope = h.value_scope
          )
        RETURNING 1
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
            value_scope,
            set_value,
            priced_card_count,
            coalesce(total_card_count, 0) AS total_card_count,
            source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            source = EXCLUDED.source,
            updated_at = timezone('utc', now())
        RETURNING 1
    )
    SELECT count(*)
    INTO v_rows_upserted
    FROM upserted;

    RETURN coalesce(v_rows_upserted, 0);
END;
$$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history_for_variants(
    p_card_variant_ids UUID[],
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT timezone('utc', now())::date
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_set_id UUID;
    v_total_rows INTEGER := 0;
BEGIN
    IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 THEN
        RETURN 0;
    END IF;

    FOR v_set_id IN
        SELECT DISTINCT c.set_id
        FROM public.card_variants cv
        JOIN public.cards c
          ON c.id = cv.card_id
        WHERE cv.id = ANY(p_card_variant_ids)
          AND c.set_id IS NOT NULL
    LOOP
        v_total_rows := v_total_rows + public.refresh_pokemon_set_value_daily_history(
            v_set_id,
            p_start_date,
            p_end_date
        );
    END LOOP;

    RETURN v_total_rows;
END;
$$;

GRANT EXECUTE ON FUNCTION public.refresh_pokemon_set_value_daily_history(UUID, DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_set_value_daily_history_for_variants(UUID[], DATE, DATE) TO service_role;

COMMIT;
