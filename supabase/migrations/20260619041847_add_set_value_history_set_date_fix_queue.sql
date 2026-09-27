CREATE TABLE IF NOT EXISTS public.pokemon_set_value_daily_history_set_date_fix_queue (
    id BIGSERIAL PRIMARY KEY,
    set_id UUID NOT NULL,
    snapshot_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    rows_upserted INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (set_id, snapshot_date)
);

CREATE OR REPLACE FUNCTION public.process_pokemon_set_value_daily_history_set_date_fix_queue(p_limit INTEGER DEFAULT 10)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_job public.pokemon_set_value_daily_history_set_date_fix_queue%ROWTYPE;
    v_rows INTEGER := 0;
    v_processed INTEGER := 0;
BEGIN
    FOR v_job IN
        SELECT *
        FROM public.pokemon_set_value_daily_history_set_date_fix_queue
        WHERE status IN ('pending', 'failed')
          AND attempts < 5
        ORDER BY snapshot_date, id
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 10), 25))
    LOOP
        UPDATE public.pokemon_set_value_daily_history_set_date_fix_queue
        SET status = 'running',
            attempts = attempts + 1,
            started_at = now(),
            updated_at = now(),
            error_message = NULL
        WHERE id = v_job.id;

        BEGIN
            v_rows := public.refresh_pokemon_set_value_daily_history(
                v_job.set_id,
                v_job.snapshot_date,
                v_job.snapshot_date
            );

            UPDATE public.pokemon_set_value_daily_history_set_date_fix_queue
            SET status = 'done',
                rows_upserted = v_rows,
                finished_at = now(),
                updated_at = now(),
                error_message = NULL
            WHERE id = v_job.id;

            v_processed := v_processed + 1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.pokemon_set_value_daily_history_set_date_fix_queue
            SET status = 'failed',
                error_message = SQLERRM,
                finished_at = now(),
                updated_at = now()
            WHERE id = v_job.id;
        END;
    END LOOP;

    RETURN v_processed;
END;
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_set_value_daily_history_set_date_fix_queue TO service_role;
GRANT SELECT ON public.pokemon_set_value_daily_history_set_date_fix_queue TO authenticated;
GRANT EXECUTE ON FUNCTION public.process_pokemon_set_value_daily_history_set_date_fix_queue(INTEGER) TO service_role;
