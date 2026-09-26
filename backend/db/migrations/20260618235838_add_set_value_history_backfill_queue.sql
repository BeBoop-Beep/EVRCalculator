CREATE TABLE IF NOT EXISTS public.pokemon_set_value_daily_history_backfill_queue (
    id BIGSERIAL PRIMARY KEY,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    rows_upserted INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (start_date, end_date)
);

CREATE OR REPLACE FUNCTION public.process_pokemon_set_value_daily_history_backfill_queue()
RETURNS TABLE(processed_job_id BIGINT, processed_start_date DATE, processed_end_date DATE, processed_rows INTEGER, processed_status TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_job public.pokemon_set_value_daily_history_backfill_queue%ROWTYPE;
    v_rows INTEGER := 0;
BEGIN
    SELECT *
    INTO v_job
    FROM public.pokemon_set_value_daily_history_backfill_queue
    WHERE status IN ('pending', 'failed')
      AND attempts < 5
    ORDER BY start_date, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE public.pokemon_set_value_daily_history_backfill_queue
    SET status = 'running',
        attempts = attempts + 1,
        started_at = now(),
        updated_at = now(),
        error_message = NULL
    WHERE id = v_job.id;

    BEGIN
        v_rows := public.refresh_pokemon_set_value_daily_history(NULL, v_job.start_date, v_job.end_date);

        UPDATE public.pokemon_set_value_daily_history_backfill_queue
        SET status = 'done',
            rows_upserted = v_rows,
            finished_at = now(),
            updated_at = now(),
            error_message = NULL
        WHERE id = v_job.id;

        processed_job_id := v_job.id;
        processed_start_date := v_job.start_date;
        processed_end_date := v_job.end_date;
        processed_rows := v_rows;
        processed_status := 'done';
        RETURN NEXT;
    EXCEPTION WHEN OTHERS THEN
        UPDATE public.pokemon_set_value_daily_history_backfill_queue
        SET status = 'failed',
            error_message = SQLERRM,
            finished_at = now(),
            updated_at = now()
        WHERE id = v_job.id;

        processed_job_id := v_job.id;
        processed_start_date := v_job.start_date;
        processed_end_date := v_job.end_date;
        processed_rows := NULL;
        processed_status := 'failed';
        RETURN NEXT;
    END;
END;
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_set_value_daily_history_backfill_queue TO service_role;
GRANT SELECT ON public.pokemon_set_value_daily_history_backfill_queue TO authenticated;
GRANT EXECUTE ON FUNCTION public.process_pokemon_set_value_daily_history_backfill_queue() TO service_role;
