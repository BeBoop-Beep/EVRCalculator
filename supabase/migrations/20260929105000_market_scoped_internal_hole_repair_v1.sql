BEGIN;

CREATE OR REPLACE FUNCTION public.repair_pokemon_market_scoped_internal_holes_v1(
  p_market_date date,
  p_limit integer DEFAULT 5
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'pg_catalog','pg_temp'
SET statement_timeout = '45s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  r record;
  v_roots_processed integer := 0;
  v_rows integer := 0;
  v_total_rows integer := 0;
  v_remaining integer := 0;
BEGIN
  IF p_market_date IS NULL THEN
    RAISE EXCEPTION 'SCOPED_INTERNAL_HOLE_MARKET_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 5 THEN
    RAISE EXCEPTION 'SCOPED_INTERNAL_HOLE_LIMIT_MUST_BE_1_TO_5';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon'
      AND q.market_date=p_market_date
      AND q.status IN ('READY','LEGACY_VERIFIED')
  ) THEN
    RAISE EXCEPTION 'SCOPED_INTERNAL_HOLE_DATE_NOT_ACCEPTED: %',p_market_date;
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-scoped-internal-hole-v1:'||p_market_date::text,0)
  ) THEN
    RAISE EXCEPTION 'SCOPED_INTERNAL_HOLE_REPAIR_ALREADY_RUNNING' USING ERRCODE='55P03';
  END IF;

  FOR r IN
    SELECT DISTINCT e.set_id
    FROM public.pokemon_edition_split_root_sets_v2 e
    JOIN public.pokemon_market_root_authority a
      ON a.set_id=e.set_id AND a.deactivated_market_date IS NULL
    JOIN public.pokemon_market_scoped_history_market_certification_v1 c
      ON c.set_id=e.set_id AND c.history_publishable
    WHERE c.market_scope IN ('first_edition','unlimited','shadowless')
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
        WHERE h.set_id=e.set_id
          AND h.market_scope=c.market_scope
          AND h.market_date=p_market_date
          AND h.certified_on_date
          AND h.set_value>0
          AND h.priced_card_count>0
      )
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
        WHERE h.set_id=e.set_id
          AND h.market_scope=c.market_scope
          AND h.market_date<p_market_date
          AND h.certified_on_date
          AND h.set_value>0
          AND h.priced_card_count>0
      )
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
        WHERE h.set_id=e.set_id
          AND h.market_scope=c.market_scope
          AND h.market_date>p_market_date
          AND h.certified_on_date
          AND h.set_value>0
          AND h.priced_card_count>0
      )
    ORDER BY e.set_id
    LIMIT p_limit
  LOOP
    INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
      set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
      coverage_pct,certified_on_date,source,updated_at
    )
    SELECT
      x.set_id,x.market_scope,x.market_date,x.set_value,x.expected_card_count,x.priced_card_count,
      x.coverage_pct,x.certified_on_date,
      'variant_interval_edition_exact_v2_shadow_internal_hole_v1',
      clock_timestamp()
    FROM public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(
      r.set_id,p_market_date,p_market_date
    ) x
    JOIN public.pokemon_market_scoped_history_market_certification_v1 c
      ON c.set_id=x.set_id
     AND c.market_scope=x.market_scope
     AND c.history_publishable
    WHERE x.market_scope IN ('first_edition','unlimited','shadowless')
      AND x.certified_on_date
      AND x.set_value>0
      AND x.priced_card_count>0
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow before_row
        WHERE before_row.set_id=x.set_id
          AND before_row.market_scope=x.market_scope
          AND before_row.market_date<p_market_date
          AND before_row.certified_on_date
          AND before_row.set_value>0
          AND before_row.priced_card_count>0
      )
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow after_row
        WHERE after_row.set_id=x.set_id
          AND after_row.market_scope=x.market_scope
          AND after_row.market_date>p_market_date
          AND after_row.certified_on_date
          AND after_row.set_value>0
          AND after_row.priced_card_count>0
      )
    ON CONFLICT(set_id,market_scope,market_date) DO UPDATE
    SET set_value=excluded.set_value,
        expected_card_count=excluded.expected_card_count,
        priced_card_count=excluded.priced_card_count,
        coverage_pct=excluded.coverage_pct,
        certified_on_date=excluded.certified_on_date,
        source=excluded.source,
        updated_at=excluded.updated_at;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_total_rows := v_total_rows + v_rows;
    IF v_rows>0 THEN
      v_roots_processed := v_roots_processed + 1;
    END IF;
  END LOOP;

  SELECT count(DISTINCT e.set_id)::integer INTO v_remaining
  FROM public.pokemon_edition_split_root_sets_v2 e
  JOIN public.pokemon_market_root_authority a
    ON a.set_id=e.set_id AND a.deactivated_market_date IS NULL
  JOIN public.pokemon_market_scoped_history_market_certification_v1 c
    ON c.set_id=e.set_id AND c.history_publishable
  WHERE c.market_scope IN ('first_edition','unlimited','shadowless')
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.set_id=e.set_id
        AND h.market_scope=c.market_scope
        AND h.market_date=p_market_date
        AND h.certified_on_date
        AND h.set_value>0
        AND h.priced_card_count>0
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.set_id=e.set_id
        AND h.market_scope=c.market_scope
        AND h.market_date<p_market_date
        AND h.certified_on_date
        AND h.set_value>0
        AND h.priced_card_count>0
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.set_id=e.set_id
        AND h.market_scope=c.market_scope
        AND h.market_date>p_market_date
        AND h.certified_on_date
        AND h.set_value>0
        AND h.priced_card_count>0
    );

  RETURN jsonb_build_object(
    'marketDate',p_market_date,
    'rootsProcessed',v_roots_processed,
    'rowsWritten',v_total_rows,
    'rootsRemaining',v_remaining,
    'status',CASE WHEN v_remaining=0 THEN 'COMPLETE' ELSE 'PARTIAL' END
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.repair_pokemon_market_scoped_internal_holes_v1(date,integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.repair_pokemon_market_scoped_internal_holes_v1(date,integer)
  TO service_role;

COMMIT;
