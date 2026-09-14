BEGIN;

CREATE TABLE IF NOT EXISTS public.price_storage_v2_shadow_runs (
    scrape_batch_id bigint PRIMARY KEY REFERENCES public.pokemon_scrape_batches(id) ON DELETE CASCADE,
    market_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('running','succeeded','failed')),
    raw_rows bigint NOT NULL DEFAULT 0,
    event_rows_upserted bigint NOT NULL DEFAULT 0,
    current_rows_upserted bigint NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error_message text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE public.price_storage_v2_shadow_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_storage_v2_shadow_runs FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.price_storage_v2_shadow_runs TO service_role;

CREATE INDEX IF NOT EXISTS price_storage_v2_shadow_runs_market_date_idx
    ON public.price_storage_v2_shadow_runs (market_date DESC);

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_market_date(p_market_date date)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_batch_id bigint;
    v_raw_rows bigint := 0;
    v_event_rows bigint := 0;
    v_current_rows bigint := 0;
    v_result jsonb;
BEGIN
    SELECT batch.id
      INTO v_batch_id
      FROM public.pokemon_scrape_batches batch
     WHERE batch.market_date = p_market_date
       AND batch.status = 'complete'
       AND batch.promoted_at IS NOT NULL
     ORDER BY batch.id DESC
     LIMIT 1;

    IF v_batch_id IS NULL THEN
        RETURN jsonb_build_object(
            'status', 'skipped',
            'reason', 'no_promoted_complete_batch',
            'market_date', p_market_date
        );
    END IF;

    INSERT INTO public.price_storage_v2_shadow_runs (
        scrape_batch_id, market_date, status, started_at, completed_at, error_message
    )
    VALUES (v_batch_id, p_market_date, 'running', now(), NULL, NULL)
    ON CONFLICT (scrape_batch_id) DO UPDATE
       SET status = 'running',
           started_at = now(),
           completed_at = NULL,
           error_message = NULL;

    BEGIN
        WITH normalized AS MATERIALIZED (
            SELECT DISTINCT ON (
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD')
            )
                observation.id AS source_observation_id,
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN') AS source,
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD') AS currency,
                observation.captured_at AS observed_date,
                observation.market_price,
                observation.high_price,
                observation.low_price,
                observation.created_at AS source_created_at
            FROM public.card_variant_price_observations observation
            WHERE observation.captured_at = p_market_date
              AND observation.market_price IS NOT NULL
            ORDER BY
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD'),
                observation.created_at DESC,
                observation.id DESC
        )
        SELECT count(*) INTO v_raw_rows FROM normalized;

        WITH normalized AS MATERIALIZED (
            SELECT DISTINCT ON (
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD')
            )
                observation.id AS source_observation_id,
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN') AS source,
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD') AS currency,
                observation.captured_at AS observed_date,
                observation.market_price,
                observation.high_price,
                observation.low_price,
                observation.created_at AS source_created_at
            FROM public.card_variant_price_observations observation
            WHERE observation.captured_at = p_market_date
              AND observation.market_price IS NOT NULL
            ORDER BY
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD'),
                observation.created_at DESC,
                observation.id DESC
        ), changed AS (
            SELECT n.*
            FROM normalized n
            LEFT JOIN public.card_variant_price_current_v2 current_row
              ON current_row.card_variant_id = n.card_variant_id
             AND current_row.condition_id = n.condition_id
             AND current_row.source = n.source
             AND current_row.currency = n.currency
            WHERE current_row.card_variant_id IS NULL
               OR n.market_price IS DISTINCT FROM current_row.market_price
               OR n.high_price IS DISTINCT FROM current_row.high_price
               OR n.low_price IS DISTINCT FROM current_row.low_price
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
            changed.card_variant_id,
            changed.condition_id,
            changed.source,
            changed.currency,
            changed.observed_date,
            'PRICE',
            changed.market_price,
            changed.high_price,
            changed.low_price,
            changed.source_observation_id,
            changed.source_created_at
        FROM changed
        ON CONFLICT (card_variant_id, condition_id, source, currency, effective_date)
        DO UPDATE SET
            event_type = EXCLUDED.event_type,
            market_price = EXCLUDED.market_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            source_observation_id = EXCLUDED.source_observation_id,
            source_created_at = EXCLUDED.source_created_at;

        GET DIAGNOSTICS v_event_rows = ROW_COUNT;

        WITH normalized AS MATERIALIZED (
            SELECT DISTINCT ON (
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD')
            )
                observation.id AS source_observation_id,
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN') AS source,
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD') AS currency,
                observation.captured_at AS observed_date,
                observation.created_at AS source_created_at
            FROM public.card_variant_price_observations observation
            WHERE observation.captured_at = p_market_date
              AND observation.market_price IS NOT NULL
            ORDER BY
                observation.card_variant_id,
                observation.condition_id,
                COALESCE(NULLIF(trim(observation.source), ''), 'UNKNOWN'),
                COALESCE(NULLIF(trim(both '"' from upper(trim(observation.currency))), ''), 'USD'),
                observation.created_at DESC,
                observation.id DESC
        ), resolved AS MATERIALIZED (
            SELECT
                n.card_variant_id,
                n.condition_id,
                n.source,
                n.currency,
                n.observed_date,
                n.source_observation_id AS last_observation_id,
                n.source_created_at AS last_observation_created_at,
                latest_event.id AS event_id,
                latest_event.effective_date,
                latest_event.event_type,
                latest_event.market_price,
                latest_event.high_price,
                latest_event.low_price,
                latest_event.source_observation_id
            FROM normalized n
            JOIN LATERAL (
                SELECT event_row.*
                FROM public.card_variant_price_events_v2 event_row
                WHERE event_row.card_variant_id = n.card_variant_id
                  AND event_row.condition_id = n.condition_id
                  AND event_row.source = n.source
                  AND event_row.currency = n.currency
                  AND event_row.effective_date <= n.observed_date
                ORDER BY event_row.effective_date DESC, event_row.id DESC
                LIMIT 1
            ) latest_event ON true
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
            resolved.card_variant_id,
            resolved.condition_id,
            resolved.source,
            resolved.currency,
            resolved.event_id,
            resolved.effective_date,
            resolved.event_type,
            resolved.market_price,
            resolved.high_price,
            resolved.low_price,
            resolved.source_observation_id,
            resolved.observed_date,
            resolved.last_observation_id,
            resolved.last_observation_created_at,
            now()
        FROM resolved
        ON CONFLICT (card_variant_id, condition_id, source, currency)
        DO UPDATE SET
            event_id = EXCLUDED.event_id,
            effective_date = EXCLUDED.effective_date,
            state = EXCLUDED.state,
            market_price = EXCLUDED.market_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            source_observation_id = EXCLUDED.source_observation_id,
            last_observed_date = EXCLUDED.last_observed_date,
            last_observation_id = EXCLUDED.last_observation_id,
            last_observation_created_at = EXCLUDED.last_observation_created_at,
            updated_at = now()
        WHERE public.card_variant_price_current_v2.last_observed_date IS NULL
           OR EXCLUDED.last_observed_date >= public.card_variant_price_current_v2.last_observed_date;

        GET DIAGNOSTICS v_current_rows = ROW_COUNT;

        v_result := jsonb_build_object(
            'status', 'succeeded',
            'scrape_batch_id', v_batch_id,
            'market_date', p_market_date,
            'raw_rows', v_raw_rows,
            'event_rows_upserted', v_event_rows,
            'current_rows_upserted', v_current_rows
        );

        UPDATE public.price_storage_v2_shadow_runs
           SET status = 'succeeded',
               raw_rows = v_raw_rows,
               event_rows_upserted = v_event_rows,
               current_rows_upserted = v_current_rows,
               completed_at = now(),
               details = v_result,
               error_message = NULL
         WHERE scrape_batch_id = v_batch_id;

        RETURN v_result;
    EXCEPTION WHEN OTHERS THEN
        UPDATE public.price_storage_v2_shadow_runs
           SET status = 'failed',
               completed_at = now(),
               error_message = SQLERRM,
               details = jsonb_build_object(
                   'status', 'failed',
                   'scrape_batch_id', v_batch_id,
                   'market_date', p_market_date,
                   'sqlstate', SQLSTATE,
                   'error', SQLERRM
               )
         WHERE scrape_batch_id = v_batch_id;

        RETURN jsonb_build_object(
            'status', 'failed',
            'scrape_batch_id', v_batch_id,
            'market_date', p_market_date,
            'sqlstate', SQLSTATE,
            'error', SQLERRM
        );
    END;
END;
$function$;

REVOKE ALL ON FUNCTION public.process_price_storage_v2_market_date(date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_market_date(date) TO service_role;

CREATE OR REPLACE FUNCTION public.process_latest_promoted_price_storage_v2_shadow()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_batch record;
BEGIN
    SELECT batch.id, batch.market_date
      INTO v_batch
      FROM public.pokemon_scrape_batches batch
      LEFT JOIN public.price_storage_v2_shadow_runs shadow_run
        ON shadow_run.scrape_batch_id = batch.id
       AND shadow_run.status = 'succeeded'
     WHERE batch.status = 'complete'
       AND batch.promoted_at IS NOT NULL
       AND shadow_run.scrape_batch_id IS NULL
     ORDER BY batch.market_date DESC, batch.id DESC
     LIMIT 1;

    IF v_batch.id IS NULL THEN
        RETURN jsonb_build_object('status', 'noop', 'reason', 'no_unprocessed_promoted_batch');
    END IF;

    RETURN public.process_price_storage_v2_market_date(v_batch.market_date);
END;
$function$;

REVOKE ALL ON FUNCTION public.process_latest_promoted_price_storage_v2_shadow() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.process_latest_promoted_price_storage_v2_shadow() TO service_role;

-- Run well after the normal early-morning scrape window. This is shadow-only and
-- has no dependency relationship with publication.
SELECT cron.schedule(
    'price-storage-v2-shadow-promoted-batch',
    '17 * * * *',
    'select public.process_latest_promoted_price_storage_v2_shadow();'
)
WHERE NOT EXISTS (
    SELECT 1 FROM cron.job WHERE jobname = 'price-storage-v2-shadow-promoted-batch'
);

COMMIT;