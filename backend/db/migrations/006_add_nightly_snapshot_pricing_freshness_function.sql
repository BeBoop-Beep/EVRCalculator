BEGIN;

CREATE OR REPLACE FUNCTION public.get_nightly_snapshot_pricing_freshness(
    p_snapshot_date date DEFAULT NULL,
    p_sample_limit integer DEFAULT 25
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_snapshot_date date := COALESCE(p_snapshot_date, timezone('utc', now())::date);
    v_sample_limit integer := GREATEST(COALESCE(p_sample_limit, 25), 0);
    v_day_start timestamptz := (v_snapshot_date::text || ' 00:00:00+00')::timestamptz;
    v_day_end timestamptz := ((v_snapshot_date + 1)::text || ' 00:00:00+00')::timestamptz;
    v_total_started timestamptz := clock_timestamp();
    v_step_started timestamptz;
    v_held_asset_load_ms numeric := 0;
    v_card_freshness_check_ms numeric := 0;
    v_sealed_freshness_check_ms numeric := 0;
    v_graded_freshness_check_ms numeric := 0;
    v_total_ms numeric := 0;
    v_card_held_count integer := 0;
    v_sealed_held_count integer := 0;
    v_graded_held_count integer := 0;
    v_invalid_card_count integer := 0;
    v_invalid_sealed_count integer := 0;
    v_invalid_graded_count integer := 0;
    v_fresh_card_count integer := 0;
    v_fresh_sealed_count integer := 0;
    v_fresh_graded_count integer := 0;
    v_missing_card_count integer := 0;
    v_missing_sealed_count integer := 0;
    v_missing_graded_count integer := 0;
    v_missing_total integer := 0;
    v_missing_assets_sample jsonb := '[]'::jsonb;
BEGIN
    v_step_started := clock_timestamp();

    WITH held_cards AS (
        SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
        FROM public.user_card_holdings
        WHERE COALESCE(user_card_holdings.quantity, 0) > 0
          AND user_card_holdings.card_variant_id IS NOT NULL
          AND user_card_holdings.condition_id IS NOT NULL
    ), held_sealed AS (
        SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
        FROM public.user_sealed_product_holdings
        WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
          AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
    ), held_graded AS (
        SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
        FROM public.user_graded_card_holdings
        WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
          AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
    )
    SELECT
        (SELECT COUNT(*) FROM held_cards),
        (SELECT COUNT(*) FROM held_sealed),
        (SELECT COUNT(*) FROM held_graded),
        (SELECT COUNT(*) FROM public.user_card_holdings WHERE COALESCE(quantity, 0) > 0 AND (card_variant_id IS NULL OR condition_id IS NULL)),
        (SELECT COUNT(*) FROM public.user_sealed_product_holdings WHERE COALESCE(quantity, 0) > 0 AND sealed_product_id IS NULL),
        (SELECT COUNT(*) FROM public.user_graded_card_holdings WHERE COALESCE(quantity, 0) > 0 AND graded_card_variant_id IS NULL)
    INTO
        v_card_held_count,
        v_sealed_held_count,
        v_graded_held_count,
        v_invalid_card_count,
        v_invalid_sealed_count,
        v_invalid_graded_count;

    v_held_asset_load_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_cards AS (
        SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
        FROM public.user_card_holdings
        WHERE COALESCE(user_card_holdings.quantity, 0) > 0
          AND user_card_holdings.card_variant_id IS NOT NULL
          AND user_card_holdings.condition_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_card_count
    FROM held_cards h
    WHERE EXISTS (
        SELECT 1
        FROM public.card_variant_price_observations o
        WHERE o.card_variant_id = h.card_variant_id
          AND o.condition_id = h.condition_id
          AND o.captured_at >= v_day_start
          AND o.captured_at < v_day_end
    );

    v_card_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_sealed AS (
        SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
        FROM public.user_sealed_product_holdings
        WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
          AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_sealed_count
    FROM held_sealed h
    WHERE EXISTS (
        SELECT 1
        FROM public.sealed_product_price_observations o
        WHERE o.sealed_product_id = h.sealed_product_id
          AND o.captured_at >= v_day_start
          AND o.captured_at < v_day_end
    );

    v_sealed_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_step_started := clock_timestamp();
    WITH held_graded AS (
        SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
        FROM public.user_graded_card_holdings
        WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
          AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
    )
    SELECT COUNT(*)
    INTO v_fresh_graded_count
    FROM held_graded h
    WHERE EXISTS (
        SELECT 1
        FROM public.graded_card_market_latest g
        WHERE g.graded_card_variant_id = h.graded_card_variant_id
          AND g.captured_at >= v_day_start
          AND g.captured_at < v_day_end
    );

    v_graded_freshness_check_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_step_started))::numeric * 1000, 3);

    v_missing_card_count := v_card_held_count - v_fresh_card_count + v_invalid_card_count;
    v_missing_sealed_count := v_sealed_held_count - v_fresh_sealed_count + v_invalid_sealed_count;
    v_missing_graded_count := v_graded_held_count - v_fresh_graded_count + v_invalid_graded_count;
    v_missing_total := v_missing_card_count + v_missing_sealed_count + v_missing_graded_count;

    IF v_missing_total > 0 AND v_sample_limit > 0 THEN
        WITH invalid_card_sample AS (
            SELECT 0 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'card',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_card_count, v_sample_limit)) AS gs
        ), invalid_sealed_sample AS (
            SELECT 1 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'sealed',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_sealed_count, v_sample_limit)) AS gs
        ), invalid_graded_sample AS (
            SELECT 2 AS ord, gs AS seq,
                   jsonb_build_object(
                       'asset_type', 'graded',
                       'reason', 'missing_lookup_key',
                       'snapshot_date', v_snapshot_date::text
                   ) AS payload
            FROM generate_series(1, LEAST(v_invalid_graded_count, v_sample_limit)) AS gs
        ), missing_card_sample AS (
            SELECT 3 AS ord,
                   row_number() OVER (ORDER BY h.card_variant_id, h.condition_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'card',
                       'card_variant_id', h.card_variant_id,
                       'condition_id', h.condition_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_card_holdings.card_variant_id, user_card_holdings.condition_id
                FROM public.user_card_holdings
                WHERE COALESCE(user_card_holdings.quantity, 0) > 0
                  AND user_card_holdings.card_variant_id IS NOT NULL
                  AND user_card_holdings.condition_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.card_variant_price_observations o
                      WHERE o.card_variant_id = user_card_holdings.card_variant_id
                        AND o.condition_id = user_card_holdings.condition_id
                        AND o.captured_at >= v_day_start
                        AND o.captured_at < v_day_end
                  )
            ) h
            LEFT JOIN public.card_market_usd_latest_by_condition l
              ON l.variant_id = h.card_variant_id
             AND l.condition_id = h.condition_id
        ), missing_sealed_sample AS (
            SELECT 4 AS ord,
                   row_number() OVER (ORDER BY h.sealed_product_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'sealed',
                       'sealed_product_id', h.sealed_product_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_sealed_product_holdings.sealed_product_id
                FROM public.user_sealed_product_holdings
                WHERE COALESCE(user_sealed_product_holdings.quantity, 0) > 0
                  AND user_sealed_product_holdings.sealed_product_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.sealed_product_price_observations o
                      WHERE o.sealed_product_id = user_sealed_product_holdings.sealed_product_id
                        AND o.captured_at >= v_day_start
                        AND o.captured_at < v_day_end
                  )
            ) h
            LEFT JOIN public.sealed_product_market_usd_latest l
              ON l.sealed_product_id = h.sealed_product_id
        ), missing_graded_sample AS (
            SELECT 5 AS ord,
                   row_number() OVER (ORDER BY h.graded_card_variant_id) AS seq,
                   jsonb_build_object(
                       'asset_type', 'graded',
                       'graded_card_variant_id', h.graded_card_variant_id,
                       'reason', 'missing_snapshot_date_price',
                       'snapshot_date', v_snapshot_date::text,
                       'latest_captured_at', CASE WHEN l.captured_at IS NULL THEN NULL ELSE (l.captured_at AT TIME ZONE 'utc')::date::text END
                   ) AS payload
            FROM (
                SELECT DISTINCT user_graded_card_holdings.graded_card_variant_id
                FROM public.user_graded_card_holdings
                WHERE COALESCE(user_graded_card_holdings.quantity, 0) > 0
                  AND user_graded_card_holdings.graded_card_variant_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.graded_card_market_latest g
                      WHERE g.graded_card_variant_id = user_graded_card_holdings.graded_card_variant_id
                        AND g.captured_at >= v_day_start
                        AND g.captured_at < v_day_end
                  )
            ) h
            LEFT JOIN public.graded_card_market_latest l
              ON l.graded_card_variant_id = h.graded_card_variant_id
        ), combined AS (
            SELECT ord, seq, payload FROM invalid_card_sample
            UNION ALL
            SELECT ord, seq, payload FROM invalid_sealed_sample
            UNION ALL
            SELECT ord, seq, payload FROM invalid_graded_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_card_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_sealed_sample
            UNION ALL
            SELECT ord, seq, payload FROM missing_graded_sample
        )
        SELECT COALESCE(jsonb_agg(payload ORDER BY ord, seq), '[]'::jsonb)
        INTO v_missing_assets_sample
        FROM (
            SELECT ord, seq, payload
            FROM combined
            ORDER BY ord, seq
            LIMIT v_sample_limit
        ) limited_sample;
    END IF;

    v_total_ms := ROUND(EXTRACT(EPOCH FROM (clock_timestamp() - v_total_started))::numeric * 1000, 3);

    RETURN jsonb_build_object(
        'snapshot_date', v_snapshot_date::text,
        'status', CASE WHEN v_missing_total = 0 THEN 'ok' ELSE 'skipped' END,
        'check_completed', true,
        'is_fresh', v_missing_total = 0,
        'held_asset_counts', jsonb_build_object(
            'cards', v_card_held_count + v_invalid_card_count,
            'sealed', v_sealed_held_count + v_invalid_sealed_count,
            'graded', v_graded_held_count + v_invalid_graded_count
        ),
        'fresh_asset_counts', jsonb_build_object(
            'cards', v_fresh_card_count,
            'sealed', v_fresh_sealed_count,
            'graded', v_fresh_graded_count
        ),
        'missing_asset_counts', jsonb_build_object(
            'cards', v_missing_card_count,
            'sealed', v_missing_sealed_count,
            'graded', v_missing_graded_count,
            'total', v_missing_total
        ),
        'missing_assets_sample', v_missing_assets_sample,
        'warning', CASE
            WHEN v_missing_total = 0 THEN NULL
            ELSE format(
                'Pricing freshness incomplete for snapshot_date=%s; missing_or_stale_assets=%s. Nightly snapshot skipped.',
                v_snapshot_date::text,
                v_missing_total
            )
        END,
        'timings_ms', jsonb_build_object(
            'held_asset_load_ms', v_held_asset_load_ms,
            'card_freshness_check_ms', v_card_freshness_check_ms,
            'sealed_freshness_check_ms', v_sealed_freshness_check_ms,
            'graded_freshness_check_ms', v_graded_freshness_check_ms,
            'total_ms', v_total_ms
        ),
        'query_path', jsonb_build_object(
            'held_asset_source', jsonb_build_array(
                'user_card_holdings(quantity>0)',
                'user_sealed_product_holdings(quantity>0)',
                'user_graded_card_holdings(quantity>0)'
            ),
            'card_check_source', 'card_variant_price_observations(captured_at)',
            'sealed_check_source', 'sealed_product_price_observations(captured_at)',
            'graded_check_source', 'graded_card_market_latest(captured_at)',
            'uses_distinct_held_assets', true,
            'loads_full_holdings_rows', false,
            'loads_full_latest_views', false,
            'notes', jsonb_build_array(
                'Card and sealed freshness use EXISTS against snapshot-date pricing sources.',
                'Graded freshness falls back to graded_card_market_latest because no graded observation table was found in repo migrations.',
                'Missing asset samples are fetched only after freshness is decided and are bounded by sample limit.'
            )
        )
    );
END;
$$;

COMMIT;