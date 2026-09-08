CREATE OR REPLACE FUNCTION public.sync_price_observation_ranges_v2_set_date(p_set_id uuid,p_market_date date)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_row record;
    v_cover_id bigint;
    v_prev_id bigint;
    v_prev_count integer;
    v_next_id bigint;
    v_next_count integer;
    v_next_through date;
    v_observed integer:=0;
    v_already_covered integer:=0;
    v_extended integer:=0;
    v_bridged integer:=0;
    v_inserted integer:=0;
BEGIN
    IF p_set_id IS NULL OR p_market_date IS NULL THEN
        RAISE EXCEPTION 'set_id and market_date are required';
    END IF;

    FOR v_row IN
        SELECT DISTINCT ON (
            o.card_variant_id,o.condition_id,
            coalesce(nullif(trim(o.source),''),'UNKNOWN'),
            coalesce(nullif(trim(both '"' from upper(trim(o.currency))),''),'USD')
        )
            o.card_variant_id,o.condition_id,
            coalesce(nullif(trim(o.source),''),'UNKNOWN') source,
            coalesce(nullif(trim(both '"' from upper(trim(o.currency))),''),'USD') currency
        FROM public.card_variant_price_observations o
        JOIN public.card_variants cv ON cv.id=o.card_variant_id
        JOIN public.cards c ON c.id=cv.card_id
        WHERE c.set_id=p_set_id
          AND o.captured_at=p_market_date
          AND o.market_price IS NOT NULL
          AND o.market_price>0
        ORDER BY o.card_variant_id,o.condition_id,
                 coalesce(nullif(trim(o.source),''),'UNKNOWN'),
                 coalesce(nullif(trim(both '"' from upper(trim(o.currency))),''),'USD'),
                 o.created_at DESC,o.id DESC
    LOOP
        v_observed:=v_observed+1;
        v_cover_id:=NULL; v_prev_id:=NULL; v_prev_count:=NULL;
        v_next_id:=NULL; v_next_count:=NULL; v_next_through:=NULL;

        SELECT r.id INTO v_cover_id
        FROM public.card_variant_price_observation_ranges_v2 r
        WHERE r.card_variant_id=v_row.card_variant_id
          AND r.condition_id=v_row.condition_id
          AND r.source=v_row.source
          AND r.currency=v_row.currency
          AND p_market_date BETWEEN r.observed_from AND r.observed_through
        ORDER BY r.observed_from DESC
        LIMIT 1;

        IF v_cover_id IS NOT NULL THEN
            v_already_covered:=v_already_covered+1;
            CONTINUE;
        END IF;

        SELECT r.id,r.observed_day_count
          INTO v_prev_id,v_prev_count
        FROM public.card_variant_price_observation_ranges_v2 r
        WHERE r.card_variant_id=v_row.card_variant_id
          AND r.condition_id=v_row.condition_id
          AND r.source=v_row.source
          AND r.currency=v_row.currency
          AND r.observed_through=p_market_date-1
        LIMIT 1;

        SELECT r.id,r.observed_day_count,r.observed_through
          INTO v_next_id,v_next_count,v_next_through
        FROM public.card_variant_price_observation_ranges_v2 r
        WHERE r.card_variant_id=v_row.card_variant_id
          AND r.condition_id=v_row.condition_id
          AND r.source=v_row.source
          AND r.currency=v_row.currency
          AND r.observed_from=p_market_date+1
        LIMIT 1;

        IF v_prev_id IS NOT NULL AND v_next_id IS NOT NULL THEN
            UPDATE public.card_variant_price_observation_ranges_v2
            SET observed_through=v_next_through,
                observed_day_count=v_prev_count+1+v_next_count,
                updated_at=now()
            WHERE id=v_prev_id;
            DELETE FROM public.card_variant_price_observation_ranges_v2 WHERE id=v_next_id;
            v_bridged:=v_bridged+1;
        ELSIF v_prev_id IS NOT NULL THEN
            UPDATE public.card_variant_price_observation_ranges_v2
            SET observed_through=p_market_date,
                observed_day_count=v_prev_count+1,
                updated_at=now()
            WHERE id=v_prev_id;
            v_extended:=v_extended+1;
        ELSIF v_next_id IS NOT NULL THEN
            UPDATE public.card_variant_price_observation_ranges_v2
            SET observed_from=p_market_date,
                observed_day_count=v_next_count+1,
                updated_at=now()
            WHERE id=v_next_id;
            v_extended:=v_extended+1;
        ELSE
            INSERT INTO public.card_variant_price_observation_ranges_v2(
                card_variant_id,condition_id,source,currency,observed_from,observed_through,observed_day_count
            ) VALUES (
                v_row.card_variant_id,v_row.condition_id,v_row.source,v_row.currency,p_market_date,p_market_date,1
            );
            v_inserted:=v_inserted+1;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'set_id',p_set_id,'market_date',p_market_date,'observed_rows',v_observed,
        'already_covered',v_already_covered,'extended',v_extended,'bridged',v_bridged,'inserted',v_inserted
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.sync_price_observation_ranges_v2_set_date(uuid,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sync_price_observation_ranges_v2_set_date(uuid,date) TO service_role;

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

COMMENT ON FUNCTION public.sync_price_observation_ranges_v2_set_date(uuid,date) IS
'Incrementally maintains exact positive-price observation-presence ranges for one set/date after raw ingestion. Idempotent for reruns and merges adjacent ranges.';