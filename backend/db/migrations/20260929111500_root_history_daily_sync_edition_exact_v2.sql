BEGIN;

CREATE OR REPLACE FUNCTION public.sync_price_storage_v2_root_history_latest()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
SET lock_timeout = '2s'
SET statement_timeout = '120s'
AS $function$
DECLARE
    v_date date;
    v_source_count integer:=0;
    v_source_latest timestamptz;
    v_shadow_count integer:=0;
    v_missing_shadow integer:=0;
    v_existing public.price_storage_v2_root_history_sync_state%rowtype;
    v_rows integer:=0;
    v_snapshot_rows integer:=0;
    v_edition_roots integer:=0;
    v_receipt jsonb;
    r record;
BEGIN
    SELECT max(q.market_date) INTO v_date
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED');

    IF v_date IS NULL THEN
      RETURN jsonb_build_object('status','skipped','reason','no_approved_market_date');
    END IF;

    SELECT count(distinct j.set_id)::integer,max(j.completed_at)
    INTO v_source_count,v_source_latest
    FROM public.scrape_jobs j
    WHERE j.market_date=v_date AND j.status='completed';

    SELECT count(distinct q.set_id)::integer
    INTO v_shadow_count
    FROM public.price_storage_v2_shadow_queue q
    JOIN public.scrape_jobs j
      ON j.set_id=q.set_id AND j.market_date=q.market_date AND j.status='completed'
    WHERE q.market_date=v_date AND q.status='complete';

    SELECT count(*)::integer
    INTO v_missing_shadow
    FROM public.scrape_jobs j
    WHERE j.market_date=v_date AND j.status='completed'
      AND NOT EXISTS (
        SELECT 1
        FROM public.price_storage_v2_shadow_queue q
        WHERE q.set_id=j.set_id
          AND q.market_date=j.market_date
          AND q.status='complete'
      );

    IF v_source_count=0 OR v_missing_shadow>0 OR v_shadow_count<>v_source_count THEN
      INSERT INTO public.price_storage_v2_root_history_sync_state(
        market_date,status,source_completed_set_count,source_latest_completed_at,
        shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at
      ) VALUES(
        v_date,'skipped',v_source_count,v_source_latest,v_shadow_count,0,now(),
        format('waiting_for_v2_shadow: source_completed=%s shadow_completed=%s missing=%s',
               v_source_count,v_shadow_count,v_missing_shadow),
        now()
      )
      ON CONFLICT(market_date) DO UPDATE SET
        status=excluded.status,
        source_completed_set_count=excluded.source_completed_set_count,
        source_latest_completed_at=excluded.source_latest_completed_at,
        shadow_completed_set_count=excluded.shadow_completed_set_count,
        synced_row_count=excluded.synced_row_count,
        completed_at=excluded.completed_at,
        last_error=excluded.last_error,
        updated_at=excluded.updated_at;

      RETURN jsonb_build_object(
        'status','skipped',
        'market_date',v_date,
        'source_completed',v_source_count,
        'shadow_completed',v_shadow_count,
        'missing_shadow',v_missing_shadow
      );
    END IF;

    SELECT * INTO v_existing
    FROM public.price_storage_v2_root_history_sync_state s
    WHERE s.market_date=v_date;

    IF found
       AND v_existing.status='complete'
       AND v_existing.source_completed_set_count=v_source_count
       AND v_existing.shadow_completed_set_count=v_shadow_count
       AND v_existing.source_latest_completed_at IS NOT DISTINCT FROM v_source_latest
       AND NOT EXISTS (
         SELECT 1
         FROM public.pokemon_edition_split_root_sets_v2 e
         JOIN public.pokemon_edition_history_refresh_state_v1 rs
           ON rs.set_id=e.set_id AND rs.market_date=v_date
         WHERE rs.raw_v2_equal IS DISTINCT FROM true
       )
       AND (
         SELECT count(*)
         FROM public.pokemon_edition_split_root_sets_v2 e
         JOIN public.pokemon_market_root_authority a
           ON a.set_id=e.set_id AND a.deactivated_market_date IS NULL
       ) = (
         SELECT count(*)
         FROM public.pokemon_edition_split_root_sets_v2 e
         JOIN public.pokemon_market_root_authority a
           ON a.set_id=e.set_id AND a.deactivated_market_date IS NULL
         JOIN public.pokemon_edition_history_refresh_state_v1 rs
           ON rs.set_id=e.set_id AND rs.market_date=v_date AND rs.raw_v2_equal
       )
    THEN
      RETURN jsonb_build_object(
        'status','noop',
        'market_date',v_date,
        'synced_rows',v_existing.synced_row_count,
        'edition_exact_verified',true
      );
    END IF;

    DELETE FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_date=v_date;

    INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
      set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
      coverage_pct,certified_on_date,source,updated_at
    )
    SELECT
      v.set_id,v.market_scope,v_date,v.set_value,v.expected_card_count,
      v.priced_card_count,v.coverage_pct,v.publishable_100pct,
      'root_latest_v2_snapshot'::text,now()
    FROM public.pokemon_market_root_set_value_latest_v1 v;
    GET DIAGNOSTICS v_snapshot_rows=ROW_COUNT;

    -- The generic latest snapshot is not authoritative for split-printing roots.
    -- Replace every vintage scope for this exact date using the edition-aware,
    -- raw/V2-parity-verified writer before the day can be marked complete.
    FOR r IN
      SELECT e.set_id
      FROM public.pokemon_edition_split_root_sets_v2 e
      JOIN public.pokemon_market_root_authority a
        ON a.set_id=e.set_id AND a.deactivated_market_date IS NULL
      ORDER BY e.set_id
    LOOP
      v_receipt := public.refresh_pokemon_edition_history_day_v1(
        r.set_id,v_date,false
      );

      IF coalesce(v_receipt->>'status','') NOT IN ('complete','noop') THEN
        RAISE EXCEPTION 'EDITION_EXACT_DAILY_REFRESH_NOT_COMPLETE: set % receipt %',
          r.set_id,v_receipt;
      END IF;

      IF coalesce((v_receipt->>'raw_v2_equal')::boolean,true) IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'EDITION_EXACT_DAILY_REFRESH_PARITY_FAILED: set % receipt %',
          r.set_id,v_receipt;
      END IF;

      v_edition_roots := v_edition_roots + 1;
    END LOOP;

    SELECT count(*)::integer INTO v_rows
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_date=v_date;

    INSERT INTO public.price_storage_v2_root_history_sync_state(
      market_date,status,source_completed_set_count,source_latest_completed_at,
      shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at
    ) VALUES(
      v_date,'complete',v_source_count,v_source_latest,v_shadow_count,
      v_rows,now(),null,now()
    )
    ON CONFLICT(market_date) DO UPDATE SET
      status=excluded.status,
      source_completed_set_count=excluded.source_completed_set_count,
      source_latest_completed_at=excluded.source_latest_completed_at,
      shadow_completed_set_count=excluded.shadow_completed_set_count,
      synced_row_count=excluded.synced_row_count,
      completed_at=excluded.completed_at,
      last_error=null,
      updated_at=excluded.updated_at;

    RETURN jsonb_build_object(
      'status','complete',
      'market_date',v_date,
      'source_completed',v_source_count,
      'shadow_completed',v_shadow_count,
      'snapshot_rows',v_snapshot_rows,
      'synced_rows',v_rows,
      'edition_roots_refreshed',v_edition_roots,
      'edition_exact_verified',true
    );
EXCEPTION WHEN OTHERS THEN
    IF v_date IS NOT NULL THEN
      INSERT INTO public.price_storage_v2_root_history_sync_state(
        market_date,status,source_completed_set_count,source_latest_completed_at,
        shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at
      )
      VALUES(
        v_date,'failed',v_source_count,v_source_latest,v_shadow_count,0,
        now(),left(SQLERRM,2000),now()
      )
      ON CONFLICT(market_date) DO UPDATE SET
        status='failed',
        last_error=excluded.last_error,
        completed_at=excluded.completed_at,
        updated_at=excluded.updated_at;
    END IF;
    RAISE;
END;
$function$;

REVOKE ALL ON FUNCTION public.sync_price_storage_v2_root_history_latest()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sync_price_storage_v2_root_history_latest()
  TO postgres, service_role;

COMMIT;
