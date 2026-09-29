BEGIN;

ALTER FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
  RENAME TO publish_pokemon_market_explorer_surface_current_core_v2;

CREATE OR REPLACE FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='300s'
SET lock_timeout='2s'
AS $function$
DECLARE
  v_target date;
  v_processed integer:=0;
  v_remaining integer:=0;
  v_failed integer:=0;
  v_failures jsonb:='[]'::jsonb;
  v_latest_sealed date;
  r record;
BEGIN
  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2-dependency-backstop',0)
  ) THEN
    RETURN jsonb_build_object(
      'status','blocked',
      'errorClass','dependency_backstop_already_running'
    );
  END IF;

  SELECT g.comparison_as_of
    INTO v_target
  FROM public.pokemon_market_explorer_prepared_serving_v1 s
  JOIN public.pokemon_market_explorer_prepared_generations_v1 g
    ON g.generation_id=s.generation_id
  WHERE s.singleton
    AND g.status='serving'
  LIMIT 1;

  IF v_target IS NULL THEN
    RAISE EXCEPTION 'CURRENT_V2_BACKSTOP_TARGET_MISSING';
  END IF;

  FOR r IN
    SELECT c.set_id
    FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
    WHERE c.computed_through IS NULL OR c.computed_through<v_target
    ORDER BY c.computed_through NULLS FIRST,c.set_id
    LIMIT 8
  LOOP
    BEGIN
      PERFORM public.publish_pokemon_market_explorer_daily_v2_for_set(
        r.set_id,v_target,100,false
      );
      v_processed:=v_processed+1;
    EXCEPTION WHEN OTHERS THEN
      v_failed:=v_failed+1;
      v_failures:=v_failures || jsonb_build_array(
        jsonb_build_object('setId',r.set_id,'error',SQLERRM)
      );
    END;
  END LOOP;

  SELECT count(*)::integer
    INTO v_remaining
  FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
  WHERE c.computed_through IS NULL OR c.computed_through<v_target;

  IF v_remaining>0 OR v_failed>0 THEN
    RETURN jsonb_build_object(
      'status','blocked',
      'errorClass','card_daily_converging',
      'marketDate',v_target,
      'advancedSets',v_processed,
      'failedSets',v_failed,
      'remainingSets',v_remaining,
      'failures',v_failures
    );
  END IF;

  SELECT max(d.market_date)
    INTO v_latest_sealed
  FROM public.pokemon_market_explorer_sealed_daily_v1 d;

  IF v_latest_sealed IS NULL OR v_latest_sealed<v_target THEN
    PERFORM public.refresh_pokemon_market_explorer_sealed_daily_v1(
      coalesce(v_latest_sealed+1,v_target),
      v_target
    );
  END IF;

  PERFORM public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();

  RETURN public.publish_pokemon_market_explorer_surface_current_core_v2();
END;
$function$;

REVOKE ALL ON FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
TO service_role;

REVOKE ALL ON FUNCTION public.publish_pokemon_market_explorer_surface_current_core_v2()
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_market_explorer_surface_current_core_v2()
TO service_role;

COMMIT;
