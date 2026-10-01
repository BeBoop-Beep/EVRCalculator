BEGIN;

CREATE OR REPLACE FUNCTION public.reconcile_pokemon_market_standard_history_setbased_v2(
  p_limit integer DEFAULT 25
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path='pg_catalog','pg_temp'
SET statement_timeout='60s'
SET lock_timeout='2s'
AS $function$
DECLARE
  v_roots integer:=0;
  v_rows integer:=0;
  v_remaining integer:=0;
BEGIN
  IF p_limit IS NULL OR p_limit<1 OR p_limit>50 THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_SETBASED_LIMIT_MUST_BE_1_TO_50';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-standard-history-reconcile-setbased-v2',0)
  ) THEN
    RETURN jsonb_build_object(
      'status','BLOCKED',
      'errorClass','reconcile_already_running'
    );
  END IF;

  CREATE TEMP TABLE _standard_reconcile_roots ON COMMIT DROP AS
  SELECT DISTINCT v.set_id
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
  JOIN public.pokemon_set_value_daily_history h
    ON h.set_id=v.set_id
   AND h.snapshot_date=v.market_date
   AND h.value_scope='standard'
  WHERE v.market_scope='standard'
    AND v.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1 FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=v.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=v.set_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_set_value_daily_history sub
      WHERE sub.set_id=v.set_id
        AND sub.snapshot_date=v.market_date
        AND sub.value_scope IN ('hits','top10')
        AND coalesce(sub.set_value,0)>coalesce(v.set_value,0)
    )
    AND (
      round(coalesce(h.set_value,0),2) IS DISTINCT FROM round(coalesce(v.set_value,0),2)
      OR coalesce(h.included_card_count,h.priced_card_count,0) IS DISTINCT FROM v.priced_card_count
      OR coalesce(h.total_card_count,0) IS DISTINCT FROM v.expected_card_count
    )
  ORDER BY v.set_id
  LIMIT p_limit;

  SELECT count(*)::integer INTO v_roots FROM _standard_reconcile_roots;

  IF v_roots=0 THEN
    RETURN jsonb_build_object(
      'status','COMPLETE',
      'rootsProcessed',0,
      'rowsUpdated',0,
      'rootsRemaining',0
    );
  END IF;

  CREATE TEMP TABLE _standard_reconcile_rows ON COMMIT DROP AS
  SELECT
    v.set_id,
    v.market_date,
    v.set_value,
    v.priced_card_count,
    v.expected_card_count,
    v.coverage_pct
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
  JOIN _standard_reconcile_roots r ON r.set_id=v.set_id
  WHERE v.market_scope='standard'
    AND v.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1 FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=v.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_set_value_daily_history sub
      WHERE sub.set_id=v.set_id
        AND sub.snapshot_date=v.market_date
        AND sub.value_scope IN ('hits','top10')
        AND coalesce(sub.set_value,0)>coalesce(v.set_value,0)
    );

  CREATE UNIQUE INDEX ON _standard_reconcile_rows(set_id,market_date);
  ANALYZE _standard_reconcile_rows;

  UPDATE public.pokemon_set_value_daily_history h
  SET set_value=r.set_value,
      priced_card_count=r.priced_card_count,
      total_card_count=r.expected_card_count,
      canonical_card_count=r.expected_card_count,
      linked_card_count=r.expected_card_count,
      included_card_count=r.priced_card_count,
      coverage_pct=r.coverage_pct,
      source='canonical_root_standard_history_v2_reconciled_setbased_v2',
      updated_at=clock_timestamp()
  FROM _standard_reconcile_rows r
  WHERE h.set_id=r.set_id
    AND h.snapshot_date=r.market_date
    AND h.value_scope='standard'
    AND (
      round(coalesce(h.set_value,0),2) IS DISTINCT FROM round(coalesce(r.set_value,0),2)
      OR coalesce(h.included_card_count,h.priced_card_count,0) IS DISTINCT FROM r.priced_card_count
      OR coalesce(h.total_card_count,0) IS DISTINCT FROM r.expected_card_count
    );
  GET DIAGNOSTICS v_rows=ROW_COUNT;

  SELECT count(DISTINCT v.set_id)::integer INTO v_remaining
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
  JOIN public.pokemon_set_value_daily_history h
    ON h.set_id=v.set_id
   AND h.snapshot_date=v.market_date
   AND h.value_scope='standard'
  WHERE v.market_scope='standard'
    AND v.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1 FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=v.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=v.set_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_set_value_daily_history sub
      WHERE sub.set_id=v.set_id
        AND sub.snapshot_date=v.market_date
        AND sub.value_scope IN ('hits','top10')
        AND coalesce(sub.set_value,0)>coalesce(v.set_value,0)
    )
    AND (
      round(coalesce(h.set_value,0),2) IS DISTINCT FROM round(coalesce(v.set_value,0),2)
      OR coalesce(h.included_card_count,h.priced_card_count,0) IS DISTINCT FROM v.priced_card_count
      OR coalesce(h.total_card_count,0) IS DISTINCT FROM v.expected_card_count
    );

  RETURN jsonb_build_object(
    'status',CASE WHEN v_remaining=0 THEN 'COMPLETE' ELSE 'PARTIAL' END,
    'rootsProcessed',v_roots,
    'rowsUpdated',v_rows,
    'rootsRemaining',v_remaining
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.reconcile_pokemon_market_standard_history_setbased_v2(integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_pokemon_market_standard_history_setbased_v2(integer)
TO service_role;

COMMIT;
