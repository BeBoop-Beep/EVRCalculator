
BEGIN;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_root_standard_current_batch_v2(
  p_market_date date,
  p_after_set_id uuid DEFAULT NULL,
  p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog','pg_temp'
SET statement_timeout TO '60s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  r record;
  v_processed integer:=0;
  v_root_rows integer:=0;
  v_legacy_rows integer:=0;
  v_skipped_invariant integer:=0;
  v_last uuid:=p_after_set_id;
  v_remaining integer:=0;
BEGIN
  IF p_market_date IS NULL THEN
    RAISE EXCEPTION 'ROOT_STANDARD_CURRENT_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>25 THEN
    RAISE EXCEPTION 'ROOT_STANDARD_CURRENT_LIMIT_MUST_BE_1_TO_25';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon' AND q.market_date=p_market_date
      AND q.status IN ('READY','LEGACY_VERIFIED')
  ) THEN
    RAISE EXCEPTION 'ROOT_STANDARD_CURRENT_DATE_NOT_ACCEPTED';
  END IF;

  FOR r IN
    SELECT a.set_id
    FROM public.pokemon_market_root_authority a
    JOIN public.sets s ON s.id=a.set_id
    WHERE a.activated_market_date<=p_market_date
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
      AND s.parent_opening_set_id IS NULL
      AND coalesce(s.catalog_only,false)=false
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=a.set_id
      )
      AND (p_after_set_id IS NULL OR a.set_id>p_after_set_id)
    ORDER BY a.set_id
    LIMIT p_limit
  LOOP
    INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
      set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
      coverage_pct,certified_on_date,source,updated_at
    )
    SELECT
      x.set_id,'standard',x.market_date,x.set_value,x.expected_card_count,x.priced_card_count,
      x.coverage_pct,x.certified_on_date,
      'canonical_price_events_v2_root_standard_current_v2',
      clock_timestamp()
    FROM public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shad(
      r.set_id,p_market_date,p_market_date
    ) x
    WHERE x.set_value>0 AND x.priced_card_count>0
    ON CONFLICT(set_id,market_scope,market_date) DO UPDATE
    SET set_value=excluded.set_value,
        expected_card_count=excluded.expected_card_count,
        priced_card_count=excluded.priced_card_count,
        coverage_pct=excluded.coverage_pct,
        certified_on_date=excluded.certified_on_date,
        source=excluded.source,
        updated_at=excluded.updated_at;
    v_root_rows:=v_root_rows+1;

    INSERT INTO public.pokemon_set_value_daily_history(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,updated_at
    )
    SELECT
      v.set_id,v.market_date,'standard',v.set_value,v.priced_card_count,v.expected_card_count,
      v.expected_card_count,v.expected_card_count,v.priced_card_count,v.coverage_pct,
      'canonical_price_events_v2_root_standard_current_v2',
      clock_timestamp()
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
    WHERE v.set_id=r.set_id
      AND v.market_scope='standard'
      AND v.market_date=p_market_date
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_set_value_daily_history sub
        WHERE sub.set_id=v.set_id AND sub.snapshot_date=v.market_date
          AND sub.value_scope IN ('hits','top10')
          AND coalesce(sub.set_value,0)>coalesce(v.set_value,0)
      )
    ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE
    SET set_value=excluded.set_value,
        priced_card_count=excluded.priced_card_count,
        total_card_count=excluded.total_card_count,
        canonical_card_count=excluded.canonical_card_count,
        linked_card_count=excluded.linked_card_count,
        included_card_count=excluded.included_card_count,
        coverage_pct=excluded.coverage_pct,
        source=excluded.source,
        updated_at=excluded.updated_at;
    IF FOUND THEN
      v_legacy_rows:=v_legacy_rows+1;
    ELSE
      v_skipped_invariant:=v_skipped_invariant+1;
    END IF;

    v_processed:=v_processed+1;
    v_last:=r.set_id;
  END LOOP;

  SELECT count(*)::integer INTO v_remaining
  FROM public.pokemon_market_root_authority a
  JOIN public.sets s ON s.id=a.set_id
  WHERE a.activated_market_date<=p_market_date
    AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only,false)=false
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=a.set_id
    )
    AND (v_last IS NULL OR a.set_id>v_last);

  RETURN jsonb_build_object(
    'marketDate',p_market_date,
    'processed',v_processed,
    'rootRowsWritten',v_root_rows,
    'legacyRowsWritten',v_legacy_rows,
    'legacyRowsSkippedInvariant',v_skipped_invariant,
    'lastSetId',v_last,
    'remaining',v_remaining,
    'status',CASE WHEN v_remaining=0 THEN 'COMPLETE' ELSE 'PARTIAL' END
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_market_root_standard_current_batch_v2(date,uuid,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_market_root_standard_current_batch_v2(date,uuid,integer)
  TO service_role;

COMMIT;
