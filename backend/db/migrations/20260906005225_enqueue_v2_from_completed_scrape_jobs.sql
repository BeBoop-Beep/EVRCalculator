BEGIN;

ALTER TABLE public.price_storage_v2_shadow_queue
    ADD COLUMN IF NOT EXISTS source_completed_at timestamptz;

CREATE OR REPLACE FUNCTION public.enqueue_price_storage_v2_completed_scrape_jobs(
    p_market_date date,
    p_limit integer DEFAULT 500
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_enqueued integer := 0;
BEGIN
    IF p_market_date IS NULL THEN
        RAISE EXCEPTION 'p_market_date is required';
    END IF;
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 1000';
    END IF;

    WITH completed AS MATERIALIZED (
        SELECT
            job.set_id,
            job.market_date,
            max(job.completed_at) AS source_completed_at
        FROM public.scrape_jobs job
        WHERE job.market_date = p_market_date
          AND job.status = 'completed'
          AND job.set_id IS NOT NULL
          AND job.completed_at IS NOT NULL
        GROUP BY job.set_id, job.market_date
        ORDER BY max(job.completed_at), job.set_id
        LIMIT p_limit
    ), upserted AS (
        INSERT INTO public.price_storage_v2_shadow_queue (
            set_id, market_date, status, attempts, last_error,
            enqueued_at, started_at, completed_at, updated_at,
            source_completed_at
        )
        SELECT
            c.set_id, c.market_date, 'pending', 0, NULL,
            now(), NULL, NULL, now(), c.source_completed_at
        FROM completed c
        ON CONFLICT (set_id, market_date)
        DO UPDATE SET
            status = 'pending',
            last_error = NULL,
            started_at = NULL,
            completed_at = NULL,
            updated_at = now(),
            source_completed_at = EXCLUDED.source_completed_at
        WHERE public.price_storage_v2_shadow_queue.source_completed_at IS NULL
           OR EXCLUDED.source_completed_at > public.price_storage_v2_shadow_queue.source_completed_at
           OR public.price_storage_v2_shadow_queue.status = 'failed'
        RETURNING 1
    )
    SELECT count(*) INTO v_enqueued FROM upserted;

    RETURN jsonb_build_object(
        'market_date', p_market_date,
        'enqueued', v_enqueued
    );
END;
$$;

REVOKE ALL ON FUNCTION public.enqueue_price_storage_v2_completed_scrape_jobs(date, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_price_storage_v2_completed_scrape_jobs(date, integer)
    TO service_role;

COMMENT ON FUNCTION public.enqueue_price_storage_v2_completed_scrape_jobs(date, integer) IS
'Idempotently discovers completed legacy set scrape jobs for one market date and queues them for Price Storage V2 shadow projection. Failed scrape jobs are never queued.';

COMMIT;