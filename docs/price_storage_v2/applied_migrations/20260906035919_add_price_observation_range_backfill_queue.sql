CREATE TABLE IF NOT EXISTS public.price_storage_v2_observation_range_backfill_sets (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0,
    range_rows bigint,
    started_at timestamptz,
    completed_at timestamptz,
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.price_storage_v2_observation_range_backfill_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_storage_v2_observation_range_backfill_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.price_storage_v2_observation_range_backfill_sets TO service_role;

INSERT INTO public.price_storage_v2_observation_range_backfill_sets(set_id,status)
SELECT b.set_id,'pending'
FROM public.price_storage_v2_backfill_sets b
WHERE b.status='complete'
ON CONFLICT (set_id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_observation_range_backfill_sets(p_limit integer DEFAULT 5)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_job record;
    v_ids uuid[];
    v_result jsonb;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>10 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 10';
    END IF;

    FOR v_job IN
        SELECT q.set_id
        FROM public.price_storage_v2_observation_range_backfill_sets q
        WHERE q.status IN ('pending','failed') AND q.attempts<5
        ORDER BY q.set_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed:=v_processed+1;
        UPDATE public.price_storage_v2_observation_range_backfill_sets
        SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
        WHERE set_id=v_job.set_id;
        BEGIN
            SELECT array_agg(cv.id ORDER BY cv.id)
              INTO v_ids
            FROM public.card_variants cv
            JOIN public.cards c ON c.id=cv.card_id
            WHERE c.set_id=v_job.set_id;

            IF v_ids IS NULL OR cardinality(v_ids)=0 THEN
                v_result:=jsonb_build_object('scopeVariants',0,'rangeRows',0);
            ELSE
                v_result:=public.rebuild_card_variant_price_observation_ranges_v2_from_raw_scope(v_ids);
            END IF;

            UPDATE public.price_storage_v2_observation_range_backfill_sets
            SET status='complete',range_rows=coalesce((v_result->>'rangeRows')::bigint,0),completed_at=now(),last_error=NULL,updated_at=now()
            WHERE set_id=v_job.set_id;
            v_completed:=v_completed+1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_observation_range_backfill_sets
            SET status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now()
            WHERE set_id=v_job.set_id;
            v_failed:=v_failed+1;
        END;
    END LOOP;

    RETURN jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed);
END;
$function$;

REVOKE ALL ON FUNCTION public.process_price_storage_v2_observation_range_backfill_sets(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_observation_range_backfill_sets(integer) TO service_role;