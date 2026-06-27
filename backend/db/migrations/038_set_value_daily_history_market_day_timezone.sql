-- Use the app market day, not the UTC calendar day, for Pokemon set value history.

BEGIN;

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
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    -- Set Value daily history uses America/Phoenix business dates so scrapes
    -- after 00:00 UTC but before local midnight remain on the intended local
    -- market day.
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
    canonical_checklist AS (
        SELECT
            pcc.set_id,
            pcc.id AS pokemon_canonical_card_id,
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        JOIN requested_sets s
          ON s.id = pcc.set_id
    ),
    canonical_counts AS (
        SELECT
            set_id,
            count(DISTINCT pokemon_canonical_card_id)::integer AS canonical_card_count
        FROM canonical_checklist
        GROUP BY set_id
    ),
    canonical_card_links AS (
        SELECT DISTINCT
            cc.set_id,
            cc.pokemon_canonical_card_id,
            c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = cc.set_id
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
            ccl.set_id,
            ccl.pokemon_canonical_card_id,
            ccl.card_id,
            cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv
          ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_counts AS (
        SELECT
            set_id,
            count(DISTINCT pokemon_canonical_card_id)::integer AS linked_card_count
        FROM canonical_variant_links
        GROUP BY set_id
    ),
    canonical_scope_flags AS (
        SELECT
            cc.set_id,
            cc.pokemon_canonical_card_id,
            EXISTS (
                SELECT 1
                FROM public.pokemon_card_desirability_links link
                WHERE link.pokemon_canonical_card_id = cc.pokemon_canonical_card_id
                  AND link.is_hit_eligible = true
            ) AS is_hit_eligible
        FROM canonical_checklist cc
    ),
    hit_counts AS (
        SELECT
            set_id,
            count(DISTINCT pokemon_canonical_card_id)::integer AS hit_card_count
        FROM canonical_scope_flags
        WHERE is_hit_eligible = true
        GROUP BY set_id
    ),
    observed_bounds AS (
        SELECT
            cvl.set_id,
            min(timezone(v_set_value_market_day_timezone, o.captured_at)::date) AS first_observation_date,
            max(timezone(v_set_value_market_day_timezone, o.captured_at)::date) AS latest_observation_date
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = cvl.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
        GROUP BY cvl.set_id
    ),
    set_dates AS (
        SELECT
            b.set_id,
            generated_day::date AS snapshot_date
        FROM observed_bounds b
        CROSS JOIN LATERAL generate_series(
            greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date)),
            least(
                coalesce(p_end_date, b.latest_observation_date),
                b.latest_observation_date,
                timezone(v_set_value_market_day_timezone, now())::date
            ),
            interval '1 day'
        ) AS generated_day
        WHERE greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date))
              <= least(
                  coalesce(p_end_date, b.latest_observation_date),
                  b.latest_observation_date,
                  timezone(v_set_value_market_day_timezone, now())::date
              )
    ),
    latest_priced_cards AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            cvl.pokemon_canonical_card_id,
            csf.is_hit_eligible,
            latest_price.market_price,
            latest_price.captured_at
        FROM set_dates sd
        JOIN (
            SELECT DISTINCT set_id, pokemon_canonical_card_id
            FROM canonical_variant_links
        ) linked_cards
          ON linked_cards.set_id = sd.set_id
        JOIN canonical_scope_flags csf
          ON csf.set_id = linked_cards.set_id
         AND csf.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        JOIN LATERAL (
            SELECT
                o.market_price,
                o.captured_at
            FROM canonical_variant_links cvl_inner
            JOIN public.card_variant_price_observations o
              ON o.card_variant_id = cvl_inner.card_variant_id
            WHERE cvl_inner.set_id = linked_cards.set_id
              AND cvl_inner.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL
              AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < ((sd.snapshot_date + interval '1 day')::timestamp AT TIME ZONE v_set_value_market_day_timezone)
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) latest_price ON true
        JOIN canonical_variant_links cvl
          ON cvl.set_id = linked_cards.set_id
         AND cvl.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        GROUP BY
            sd.set_id,
            sd.snapshot_date,
            cvl.pokemon_canonical_card_id,
            csf.is_hit_eligible,
            latest_price.market_price,
            latest_price.captured_at
    ),
    standard_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'standard'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(cc.canonical_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round(
                (count(DISTINCT lpc.pokemon_canonical_card_id)::numeric / nullif(max(cc.canonical_card_count), 0)) * 100,
                2
            ) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc
          ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc
          ON lc.set_id = lpc.set_id
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    hits_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'hits'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(hc.hit_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round(
                (count(DISTINCT lpc.pokemon_canonical_card_id)::numeric /
                    nullif(max(hc.hit_card_count), 0)) * 100,
                2
            ) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:hits:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc
          ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc
          ON lc.set_id = lpc.set_id
        LEFT JOIN hit_counts hc
          ON hc.set_id = lpc.set_id
        WHERE lpc.is_hit_eligible = true
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    ranked_priced_cards AS (
        SELECT
            lpc.*,
            row_number() OVER (
                PARTITION BY lpc.set_id, lpc.snapshot_date
                ORDER BY lpc.market_price DESC, lpc.pokemon_canonical_card_id
            ) AS price_rank
        FROM latest_priced_cards lpc
    ),
    top10_aggregated AS (
        SELECT
            rpc.set_id,
            rpc.snapshot_date,
            'top10'::text AS value_scope,
            round(sum(rpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            least(10, max(cc.canonical_card_count))::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round(
                (count(DISTINCT rpc.pokemon_canonical_card_id)::numeric / nullif(least(10, max(cc.canonical_card_count)), 0)) * 100,
                2
            ) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist' AS source
        FROM ranked_priced_cards rpc
        JOIN canonical_counts cc
          ON cc.set_id = rpc.set_id
        LEFT JOIN linked_counts lc
          ON lc.set_id = rpc.set_id
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
            canonical_card_count,
            linked_card_count,
            included_card_count,
            coverage_pct,
            source
        )
        SELECT
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            coalesce(total_card_count, 0) AS total_card_count,
            coalesce(canonical_card_count, total_card_count, 0) AS canonical_card_count,
            coalesce(linked_card_count, 0) AS linked_card_count,
            coalesce(included_card_count, priced_card_count, 0) AS included_card_count,
            coverage_pct,
            source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            canonical_card_count = EXCLUDED.canonical_card_count,
            linked_card_count = EXCLUDED.linked_card_count,
            included_card_count = EXCLUDED.included_card_count,
            coverage_pct = EXCLUDED.coverage_pct,
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
    p_end_date DATE DEFAULT timezone('America/Phoenix', now())::date
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
