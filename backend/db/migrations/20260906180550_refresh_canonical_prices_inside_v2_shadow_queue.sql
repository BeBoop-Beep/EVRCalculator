CREATE OR REPLACE FUNCTION public.process_price_storage_v2_shadow_queue(p_limit integer DEFAULT 20)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_job record;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
    v_price_result jsonb;
    v_range_result jsonb;
    v_interval_result jsonb;
    v_canonical_rows integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>20 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 20';
    END IF;

    FOR v_job IN
        SELECT q.id,q.set_id,q.market_date
        FROM public.price_storage_v2_shadow_queue q
        WHERE q.status IN ('pending','failed') AND q.attempts<5
        ORDER BY q.market_date,q.id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed:=v_processed+1;
        UPDATE public.price_storage_v2_shadow_queue
        SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
        WHERE id=v_job.id;
        BEGIN
            v_price_result:=public.sync_price_storage_v2_set_date(v_job.set_id,v_job.market_date);
            v_range_result:=public.sync_price_observation_ranges_v2_set_date(v_job.set_id,v_job.market_date);
            v_interval_result:=public.sync_pokemon_market_price_intervals_v2_shadow_set_from_date(v_job.set_id,v_job.market_date);

            v_canonical_rows:=public.refresh_pokemon_canonical_card_market_prices_latest_for_set(v_job.set_id);

            UPDATE public.price_storage_v2_shadow_queue
            SET status='complete',completed_at=now(),last_error=NULL,updated_at=now()
            WHERE id=v_job.id;
            v_completed:=v_completed+1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_shadow_queue
            SET status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now()
            WHERE id=v_job.id;
            v_failed:=v_failed+1;
        END;
    END LOOP;

    RETURN jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed);
END;
$function$;