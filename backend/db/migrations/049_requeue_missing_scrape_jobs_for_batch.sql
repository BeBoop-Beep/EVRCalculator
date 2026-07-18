-- Phase 6 — Automatic cohort repair: requeue only the sets that are missing a
-- valid Near Mint observation for the batch's market date, respecting per-set
-- attempt limits so the queue cannot loop forever.
--
-- Apply manually in the Supabase SQL editor.

BEGIN;

CREATE OR REPLACE FUNCTION public.requeue_missing_scrape_jobs_for_batch(
    p_batch_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_batch public.pokemon_scrape_batches%ROWTYPE;
    v_requeued INTEGER := 0;
    v_inserted INTEGER := 0;
    v_missing INTEGER := 0;
BEGIN
    SELECT * INTO v_batch FROM public.pokemon_scrape_batches WHERE id = p_batch_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 0;
    END IF;

    -- Sets in this batch's cohort that lack a valid observation for the market day.
    CREATE TEMP TABLE _missing_sets ON COMMIT DROP AS
    SELECT m.set_id
    FROM public.pokemon_scrape_missing_sets(v_batch.market_date) m;

    GET DIAGNOSTICS v_missing = ROW_COUNT;

    -- 1. Re-open failed jobs for missing sets that still have attempts remaining.
    WITH reopened AS (
        UPDATE public.scrape_jobs j
        SET status = 'pending',
            completed_at = NULL,
            worker_id = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            error_message = 'requeued_by_cohort_repair',
            next_attempt_at = now() + make_interval(secs => LEAST(60 * power(2, GREATEST(j.attempts, 0))::integer, 1800))
        FROM _missing_sets ms
        WHERE j.batch_id = p_batch_id
          AND j.set_id = ms.set_id
          AND j.status = 'failed'
          AND j.attempts < j.max_attempts
          -- Never reopen a set that already has another active job.
          AND NOT EXISTS (
              SELECT 1 FROM public.scrape_jobs a
              WHERE a.set_id = j.set_id AND a.status IN ('pending', 'running')
          )
        RETURNING j.id
    )
    SELECT COUNT(*) INTO v_requeued FROM reopened;

    -- 2. Insert fresh jobs for missing cohort sets that have no job in this batch
    --    and no active job elsewhere.
    WITH inserted AS (
        INSERT INTO public.scrape_jobs (
            set_id, status, attempts, max_attempts, priority,
            batch_id, market_date, next_attempt_at, created_at
        )
        SELECT
            c.set_id, 'pending', 0, 3, c.priority,
            p_batch_id, v_batch.market_date, now(), timezone('utc', now())
        FROM public.pokemon_scrape_ready_cohort() c
        JOIN _missing_sets ms ON ms.set_id = c.set_id
        WHERE NOT EXISTS (
            SELECT 1 FROM public.scrape_jobs j
            WHERE j.batch_id = p_batch_id AND j.set_id = c.set_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.scrape_jobs a
            WHERE a.set_id = c.set_id AND a.status IN ('pending', 'running')
        )
        ON CONFLICT (batch_id, set_id) WHERE batch_id IS NOT NULL DO NOTHING
        RETURNING id
    )
    SELECT COUNT(*) INTO v_inserted FROM inserted;

    UPDATE public.pokemon_scrape_batches
    SET missing_set_count = v_missing,
        queued_set_count = (SELECT COUNT(*) FROM public.scrape_jobs j WHERE j.batch_id = p_batch_id),
        updated_at = timezone('utc', now())
    WHERE id = p_batch_id;

    RETURN v_requeued + v_inserted;
END;
$$;

GRANT EXECUTE ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(BIGINT) TO service_role;

COMMIT;
