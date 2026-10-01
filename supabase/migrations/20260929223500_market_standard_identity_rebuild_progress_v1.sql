BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_standard_identity_rebuild_progress_v1 (
  set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
  target_date date NOT NULL,
  rows_written integer NOT NULL DEFAULT 0 CHECK (rows_written>=0),
  completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (set_id,target_date)
);

ALTER TABLE public.pokemon_market_standard_identity_rebuild_progress_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_standard_identity_rebuild_progress_v1
  FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE
  ON public.pokemon_market_standard_identity_rebuild_progress_v1
  TO service_role;

-- Seed progress for roots already completed by the first bounded pass.
INSERT INTO public.pokemon_market_standard_identity_rebuild_progress_v1(
  set_id,target_date,rows_written
)
SELECT h.set_id,h.market_date,1
FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
WHERE h.market_scope='standard'
  AND h.market_date=(
    SELECT max(q.market_date)
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED')
  )
  AND h.source='canonical_price_events_v2_root_standard_print_identity_v3'
ON CONFLICT(set_id,target_date) DO NOTHING;

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(
  p_limit integer DEFAULT 2
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '120s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  r record;
  v_target date;
  v_processed integer:=0;
  v_failed integer:=0;
  v_rows integer:=0;
  v_remaining integer:=0;
  v_failures jsonb:='[]'::jsonb;
BEGIN
  IF p_limit IS NULL OR p_limit<1 OR p_limit>5 THEN
    RAISE EXCEPTION 'STANDARD_IDENTITY_REBUILD_LIMIT_MUST_BE_1_TO_5';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-standard-history-identity-v1',0)
  ) THEN
    RETURN jsonb_build_object('status','BLOCKED','errorClass','identity_rebuild_already_running');
  END IF;

  SELECT max(q.market_date) INTO v_target
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED');

  FOR r IN
    SELECT DISTINCT h.set_id
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_scope='standard'
      AND h.market_date>=date '2026-04-23'
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
        WHERE e.set_id=h.set_id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_market_standard_identity_rebuild_progress_v1 p
        WHERE p.set_id=h.set_id AND p.target_date=v_target
      )
    ORDER BY h.set_id
    LIMIT p_limit
  LOOP
    BEGIN
      v_rows:=0;
      INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
        set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
        coverage_pct,certified_on_date,source,updated_at
      )
      SELECT
        x.set_id,x.market_scope,x.market_date,x.set_value,x.expected_card_count,x.priced_card_count,
        x.coverage_pct,x.certified_on_date,x.source,pg_catalog.clock_timestamp()
      FROM public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(
        r.set_id,date '2026-04-23',v_target
      ) x
      ON CONFLICT(set_id,market_scope,market_date) DO UPDATE
      SET set_value=excluded.set_value,
          expected_card_count=excluded.expected_card_count,
          priced_card_count=excluded.priced_card_count,
          coverage_pct=excluded.coverage_pct,
          certified_on_date=excluded.certified_on_date,
          source=excluded.source,
          updated_at=excluded.updated_at;
      GET DIAGNOSTICS v_rows=ROW_COUNT;

      INSERT INTO public.pokemon_market_standard_identity_rebuild_progress_v1(
        set_id,target_date,rows_written,completed_at
      ) VALUES (
        r.set_id,v_target,v_rows,pg_catalog.clock_timestamp()
      )
      ON CONFLICT(set_id,target_date) DO UPDATE
      SET rows_written=excluded.rows_written,
          completed_at=excluded.completed_at;

      v_processed:=v_processed+1;
    EXCEPTION WHEN OTHERS THEN
      v_failed:=v_failed+1;
      v_failures:=v_failures||jsonb_build_array(
        jsonb_build_object('setId',r.set_id,'error',SQLERRM)
      );
    END;
  END LOOP;

  SELECT count(DISTINCT h.set_id)::integer INTO v_remaining
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.market_scope='standard'
    AND h.market_date>=date '2026-04-23'
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=h.set_id
    )
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_standard_identity_rebuild_progress_v1 p
      WHERE p.set_id=h.set_id AND p.target_date=v_target
    );

  RETURN jsonb_build_object(
    'status',CASE WHEN v_remaining=0 AND v_failed=0 THEN 'COMPLETE' ELSE 'PARTIAL' END,
    'targetDate',v_target,
    'rootsProcessed',v_processed,
    'failedRoots',v_failed,
    'remainingRoots',v_remaining,
    'lastBatchRowsTouched',v_rows,
    'failures',v_failures
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(integer)
  TO service_role;

COMMIT;
