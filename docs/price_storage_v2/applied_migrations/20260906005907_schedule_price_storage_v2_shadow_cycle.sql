BEGIN;

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_shadow_queue(
    p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_job record;
    v_processed integer := 0;
    v_completed integer := 0;
    v_failed integer := 0;
    v_result jsonb;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 20 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 20';
    END IF;

    FOR v_job IN
        SELECT q.id, q.set_id, q.market_date
        FROM public.price_storage_v2_shadow_queue q
        WHERE q.status IN ('pending','failed')
          AND q.attempts < 5
        ORDER BY q.market_date, q.id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed := v_processed + 1;

        UPDATE public.price_storage_v2_shadow_queue
        SET status = 'processing',
            attempts = attempts + 1,
            started_at = now(),
            completed_at = NULL,
            last_error = NULL,
            updated_at = now()
        WHERE id = v_job.id;

        BEGIN
            v_result := public.sync_price_storage_v2_set_date(v_job.set_id, v_job.market_date);

            UPDATE public.price_storage_v2_shadow_queue
            SET status = 'complete',
                completed_at = now(),
                last_error = NULL,
                updated_at = now()
            WHERE id = v_job.id;
            v_completed := v_completed + 1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_shadow_queue
            SET status = 'failed',
                completed_at = now(),
                last_error = left(SQLERRM, 2000),
                updated_at = now()
            WHERE id = v_job.id;
            v_failed := v_failed + 1;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'processed', v_processed,
        'completed', v_completed,
        'failed', v_failed
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.run_price_storage_v2_shadow_cycle()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_market_date date := timezone('America/Phoenix', now())::date;
    v_previous jsonb;
    v_current jsonb;
    v_processed jsonb;
BEGIN
    v_previous := public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date - 1, 1000);
    v_current := public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date, 1000);
    v_processed := public.process_price_storage_v2_shadow_queue(20);

    RETURN jsonb_build_object(
        'phoenix_market_date', v_market_date,
        'previous_date_enqueue', v_previous,
        'current_date_enqueue', v_current,
        'queue_processing', v_processed
    );
END;
$$;

REVOKE ALL ON FUNCTION public.run_price_storage_v2_shadow_cycle() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.run_price_storage_v2_shadow_cycle() TO service_role;

DO $$
DECLARE
    v_jobid bigint;
BEGIN
    SELECT jobid INTO v_jobid
    FROM cron.job
    WHERE jobname = 'price-storage-v2-shadow-cycle'
    LIMIT 1;

    IF v_jobid IS NOT NULL THEN
        PERFORM cron.unschedule(v_jobid);
    END IF;
END;
$$;

SELECT cron.schedule(
    'price-storage-v2-shadow-cycle',
    '*/15 * * * *',
    'select public.run_price_storage_v2_shadow_cycle();'
);

COMMIT;