BEGIN;

CREATE OR REPLACE FUNCTION public.sync_pokemon_market_price_intervals_v2_shadow_set_from_date(
    p_set_id uuid,
    p_start_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_deleted bigint := 0;
    v_reopened bigint := 0;
    v_inserted bigint := 0;
    v_closed_baselines bigint := 0;
BEGIN
    IF p_set_id IS NULL OR p_start_date IS NULL THEN
        RAISE EXCEPTION 'set_id and start_date are required';
    END IF;

    DELETE FROM public.pokemon_market_price_intervals_v2_shadow interval_row
    WHERE interval_row.set_id = p_set_id
      AND interval_row.valid_from >= p_start_date;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    UPDATE public.pokemon_market_price_intervals_v2_shadow interval_row
    SET valid_to = NULL
    WHERE interval_row.set_id = p_set_id
      AND interval_row.valid_from < p_start_date
      AND interval_row.valid_to IS NOT NULL
      AND interval_row.valid_to >= p_start_date;
    GET DIAGNOSTICS v_reopened = ROW_COUNT;

    WITH scoped_metadata AS MATERIALIZED (
        SELECT metadata.card_variant_id, metadata.set_id
        FROM public.pokemon_market_explorer_card_current_metadata metadata
        WHERE metadata.set_id = p_set_id
    ), ordered AS MATERIALIZED (
        SELECT
            event_row.card_variant_id,
            metadata.set_id,
            event_row.effective_date,
            event_row.market_price,
            lag(event_row.market_price) OVER (
                PARTITION BY event_row.card_variant_id
                ORDER BY event_row.effective_date, event_row.id
            ) AS previous_market_price,
            row_number() OVER (
                PARTITION BY event_row.card_variant_id
                ORDER BY event_row.effective_date, event_row.id
            ) AS sequence_number
        FROM public.card_variant_price_events_v2 event_row
        JOIN scoped_metadata metadata
          ON metadata.card_variant_id = event_row.card_variant_id
        WHERE event_row.condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
          AND event_row.source = 'TCGPlayer'
          AND event_row.currency = 'USD'
          AND event_row.market_price > 0
    ), changes AS MATERIALIZED (
        SELECT card_variant_id, set_id, effective_date, market_price
        FROM ordered
        WHERE effective_date >= p_start_date
          AND (
              sequence_number = 1
              OR market_price IS DISTINCT FROM previous_market_price
          )
    ), intervals AS (
        SELECT
            card_variant_id,
            set_id,
            effective_date AS valid_from,
            lead(effective_date) OVER (
                PARTITION BY card_variant_id
                ORDER BY effective_date
            ) AS valid_to,
            market_price
        FROM changes
    )
    INSERT INTO public.pokemon_market_price_intervals_v2_shadow (
        card_variant_id, set_id, valid_from, valid_to, market_price
    )
    SELECT card_variant_id, set_id, valid_from, valid_to, market_price
    FROM intervals;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    WITH first_new AS (
        SELECT card_variant_id, min(valid_from) AS first_valid_from
        FROM public.pokemon_market_price_intervals_v2_shadow
        WHERE set_id = p_set_id
          AND valid_from >= p_start_date
        GROUP BY card_variant_id
    )
    UPDATE public.pokemon_market_price_intervals_v2_shadow baseline
    SET valid_to = first_new.first_valid_from
    FROM first_new
    WHERE baseline.card_variant_id = first_new.card_variant_id
      AND baseline.set_id = p_set_id
      AND baseline.valid_from < p_start_date
      AND baseline.valid_to IS NULL;
    GET DIAGNOSTICS v_closed_baselines = ROW_COUNT;

    RETURN jsonb_build_object(
        'set_id', p_set_id,
        'start_date', p_start_date,
        'deleted_tail_rows', v_deleted,
        'reopened_baselines', v_reopened,
        'inserted_tail_rows', v_inserted,
        'closed_baselines', v_closed_baselines
    );
END;
$$;

REVOKE ALL ON FUNCTION public.sync_pokemon_market_price_intervals_v2_shadow_set_from_date(uuid,date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sync_pokemon_market_price_intervals_v2_shadow_set_from_date(uuid,date)
    TO service_role;

COMMENT ON FUNCTION public.sync_pokemon_market_price_intervals_v2_shadow_set_from_date(uuid,date) IS
'Idempotently rebuilds only the compact V2 Market Explorer interval tail for one set from a supplied market date forward. Used only by the shadow migration path.';

COMMIT;