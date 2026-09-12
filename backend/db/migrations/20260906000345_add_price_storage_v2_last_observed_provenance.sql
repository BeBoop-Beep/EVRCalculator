BEGIN;

ALTER TABLE public.card_variant_price_current_v2
    ADD COLUMN last_observed_date date,
    ADD COLUMN last_observation_id uuid,
    ADD COLUMN last_observation_created_at timestamptz;

COMMENT ON COLUMN public.card_variant_price_current_v2.effective_date IS
'Date the current value/state last changed.';
COMMENT ON COLUMN public.card_variant_price_current_v2.last_observed_date IS
'Most recent market date on which the source successfully observed this natural key, even when the value was unchanged.';

CREATE OR REPLACE FUNCTION public.rebuild_card_variant_price_events_v2_from_raw_scope(
    p_card_variant_ids uuid[]
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_event_rows bigint := 0;
    v_current_rows bigint := 0;
BEGIN
    IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 THEN
        RETURN jsonb_build_object('event_rows', 0, 'current_rows', 0, 'scope_variants', 0);
    END IF;

    DELETE FROM public.card_variant_price_current_v2 current_row
     WHERE current_row.card_variant_id = ANY(p_card_variant_ids);

    DELETE FROM public.card_variant_price_events_v2 event_row
     WHERE event_row.card_variant_id = ANY(p_card_variant_ids);

    WITH normalized AS MATERIALIZED (
        SELECT
            observation.id AS source_observation_id,
            observation.card_variant_id,
            observation.condition_id,
            COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN') AS source,
            COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD') AS currency,
            observation.captured_at AS effective_date,
            observation.market_price,
            observation.high_price,
            observation.low_price,
            observation.created_at AS source_created_at,
            lag(observation.market_price) OVER price_order AS previous_market_price,
            lag(observation.high_price) OVER price_order AS previous_high_price,
            lag(observation.low_price) OVER price_order AS previous_low_price,
            row_number() OVER price_order AS sequence_number
        FROM public.card_variant_price_observations observation
        WHERE observation.card_variant_id = ANY(p_card_variant_ids)
          AND observation.captured_at IS NOT NULL
        WINDOW price_order AS (
            PARTITION BY
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD')
            ORDER BY observation.captured_at, observation.created_at, observation.id
        )
    ), change_events AS (
        SELECT *
          FROM normalized
         WHERE market_price IS NOT NULL
           AND (
                sequence_number = 1
                OR market_price IS DISTINCT FROM previous_market_price
                OR high_price IS DISTINCT FROM previous_high_price
                OR low_price IS DISTINCT FROM previous_low_price
           )
    )
    INSERT INTO public.card_variant_price_events_v2 (
        card_variant_id,
        condition_id,
        source,
        currency,
        effective_date,
        event_type,
        market_price,
        high_price,
        low_price,
        source_observation_id,
        source_created_at
    )
    SELECT
        card_variant_id,
        condition_id,
        source,
        currency,
        effective_date,
        'PRICE',
        market_price,
        high_price,
        low_price,
        source_observation_id,
        source_created_at
    FROM change_events
    ORDER BY card_variant_id, condition_id, source, currency, effective_date;

    GET DIAGNOSTICS v_event_rows = ROW_COUNT;

    WITH latest_event AS MATERIALIZED (
        SELECT * FROM (
            SELECT
                event_row.*,
                row_number() OVER (
                    PARTITION BY event_row.card_variant_id, event_row.condition_id, event_row.source, event_row.currency
                    ORDER BY event_row.effective_date DESC, event_row.id DESC
                ) AS latest_rank
            FROM public.card_variant_price_events_v2 event_row
            WHERE event_row.card_variant_id = ANY(p_card_variant_ids)
        ) ranked_events
        WHERE latest_rank = 1
    ), latest_observation AS MATERIALIZED (
        SELECT * FROM (
            SELECT
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN') AS source,
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD') AS currency,
                observation.id AS last_observation_id,
                observation.captured_at AS last_observed_date,
                observation.created_at AS last_observation_created_at,
                row_number() OVER (
                    PARTITION BY observation.card_variant_id, observation.condition_id,
                        COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                        COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD')
                    ORDER BY observation.captured_at DESC, observation.created_at DESC, observation.id DESC
                ) AS latest_rank
            FROM public.card_variant_price_observations observation
            WHERE observation.card_variant_id = ANY(p_card_variant_ids)
              AND observation.captured_at IS NOT NULL
              AND observation.market_price IS NOT NULL
        ) ranked_observations
        WHERE latest_rank = 1
    )
    INSERT INTO public.card_variant_price_current_v2 (
        card_variant_id,
        condition_id,
        source,
        currency,
        event_id,
        effective_date,
        state,
        market_price,
        high_price,
        low_price,
        source_observation_id,
        last_observed_date,
        last_observation_id,
        last_observation_created_at,
        updated_at
    )
    SELECT
        e.card_variant_id,
        e.condition_id,
        e.source,
        e.currency,
        e.id,
        e.effective_date,
        e.event_type,
        e.market_price,
        e.high_price,
        e.low_price,
        e.source_observation_id,
        o.last_observed_date,
        o.last_observation_id,
        o.last_observation_created_at,
        now()
    FROM latest_event e
    JOIN latest_observation o
      ON o.card_variant_id = e.card_variant_id
     AND o.condition_id = e.condition_id
     AND o.source = e.source
     AND o.currency = e.currency;

    GET DIAGNOSTICS v_current_rows = ROW_COUNT;

    RETURN jsonb_build_object(
        'event_rows', v_event_rows,
        'current_rows', v_current_rows,
        'scope_variants', cardinality(p_card_variant_ids)
    );
END;
$$;

REVOKE ALL ON FUNCTION public.rebuild_card_variant_price_events_v2_from_raw_scope(uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_card_variant_price_events_v2_from_raw_scope(uuid[]) TO service_role;

COMMIT;