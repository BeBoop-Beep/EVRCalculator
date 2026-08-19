-- Atomically claim at most one eligible scrape job for an explicit Phoenix
-- market date. The legacy claim_next_scrape_job RPC remains available for older
-- deployed workers; the continuous drain uses this stricter contract.

CREATE OR REPLACE FUNCTION public.claim_next_scrape_job_for_market_date(
    p_worker_id TEXT,
    p_lease_seconds INTEGER,
    p_expected_market_date DATE
)
RETURNS SETOF public.scrape_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    claimed_row public.scrape_jobs%ROWTYPE;
BEGIN
    IF p_expected_market_date IS NULL THEN
        RAISE EXCEPTION 'p_expected_market_date is required'
            USING ERRCODE = '22004';
    END IF;

    -- Preserve lease recovery, using the caller's explicit market-day boundary.
    PERFORM public.reconcile_stale_scrape_jobs(now(), p_expected_market_date);

    WITH next_job AS (
        SELECT id
        FROM public.scrape_jobs
        WHERE status = 'pending'
          AND market_date = p_expected_market_date
          AND (next_attempt_at IS NULL OR next_attempt_at <= now())
        ORDER BY priority ASC, created_at ASC, id ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE public.scrape_jobs AS jobs
    SET
        status = 'running',
        started_at = now(),
        completed_at = NULL,
        attempts = jobs.attempts + 1,
        worker_id = COALESCE(p_worker_id, jobs.worker_id),
        heartbeat_at = now(),
        lease_expires_at = now() + make_interval(secs => GREATEST(p_lease_seconds, 60)),
        error_message = NULL
    FROM next_job
    WHERE jobs.id = next_job.id
    RETURNING jobs.* INTO claimed_row;

    IF claimed_row.id IS NOT NULL THEN
        RETURN NEXT claimed_row;
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_next_scrape_job_for_market_date(TEXT, INTEGER, DATE)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_next_scrape_job_for_market_date(TEXT, INTEGER, DATE)
TO service_role;
