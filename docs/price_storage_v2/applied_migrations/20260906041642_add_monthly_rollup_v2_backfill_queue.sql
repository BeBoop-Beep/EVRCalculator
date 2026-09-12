CREATE TABLE IF NOT EXISTS public.price_storage_v2_monthly_rollup_backfill_sets (
    set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    rollup_month date NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0,
    row_count bigint,
    started_at timestamptz,
    completed_at timestamptz,
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(set_id,rollup_month)
);
ALTER TABLE public.price_storage_v2_monthly_rollup_backfill_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_storage_v2_monthly_rollup_backfill_sets FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.price_storage_v2_monthly_rollup_backfill_sets TO service_role;

INSERT INTO public.price_storage_v2_monthly_rollup_backfill_sets(set_id,rollup_month,status)
SELECT b.set_id,'2026-08-01'::date,'pending'
FROM public.price_storage_v2_backfill_sets b
WHERE b.status='complete'
ON CONFLICT (set_id,rollup_month) DO NOTHING;

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_monthly_rollup_backfill_sets(p_limit integer DEFAULT 5)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_job record;
    v_result jsonb;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>10 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 10';
    END IF;
    FOR v_job IN
        SELECT q.set_id,q.rollup_month
        FROM public.price_storage_v2_monthly_rollup_backfill_sets q
        WHERE q.status IN ('pending','failed') AND q.attempts<5
        ORDER BY q.rollup_month,q.set_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed:=v_processed+1;
        UPDATE public.price_storage_v2_monthly_rollup_backfill_sets
        SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
        WHERE set_id=v_job.set_id AND rollup_month=v_job.rollup_month;
        BEGIN
            v_result:=public.rebuild_card_variant_price_monthly_rollups_v2_shadow_for_set(v_job.set_id,v_job.rollup_month);
            UPDATE public.price_storage_v2_monthly_rollup_backfill_sets
            SET status='complete',row_count=coalesce((v_result->>'rows')::bigint,0),completed_at=now(),last_error=NULL,updated_at=now()
            WHERE set_id=v_job.set_id AND rollup_month=v_job.rollup_month;
            v_completed:=v_completed+1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_monthly_rollup_backfill_sets
            SET status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now()
            WHERE set_id=v_job.set_id AND rollup_month=v_job.rollup_month;
            v_failed:=v_failed+1;
        END;
    END LOOP;
    RETURN jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed);
END;
$function$;
REVOKE ALL ON FUNCTION public.process_price_storage_v2_monthly_rollup_backfill_sets(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_monthly_rollup_backfill_sets(integer) TO service_role;