BEGIN;

CREATE OR REPLACE FUNCTION public.enqueue_missing_scrape_jobs_for_ready_sets()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_inserted_count integer := 0;
    v_cycle_start timestamptz := date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
    v_cycle_end timestamptz := (date_trunc('day', now() AT TIME ZONE 'UTC') + interval '1 day') AT TIME ZONE 'UTC';
BEGIN
    WITH inserted_jobs AS (
        INSERT INTO public.scrape_jobs (set_id, status, attempts, created_at)
        SELECT
            s.id,
            'pending',
            0,
            timezone('utc', now())
        FROM public.sets AS s
        WHERE COALESCE(s.ready_for_daily_scrape, FALSE) = TRUE
          AND COALESCE(s.has_card_details_url, FALSE) = TRUE
          AND s.card_details_url IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM public.scrape_jobs AS jobs
              WHERE jobs.set_id = s.id
                AND jobs.status IN ('pending', 'running', 'completed', 'failed')
                AND jobs.created_at >= v_cycle_start
                AND jobs.created_at < v_cycle_end
          )
        ORDER BY s.release_date ASC NULLS LAST, s.name ASC
        ON CONFLICT (set_id) WHERE status IN ('pending', 'running') DO NOTHING
        RETURNING 1
    )
    SELECT COUNT(*)
    INTO v_inserted_count
    FROM inserted_jobs;

    RETURN v_inserted_count;
END;
$$;

GRANT EXECUTE ON FUNCTION public.enqueue_missing_scrape_jobs_for_ready_sets() TO service_role;

COMMIT;
