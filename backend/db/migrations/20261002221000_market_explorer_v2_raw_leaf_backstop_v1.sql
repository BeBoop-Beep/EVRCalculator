BEGIN;

-- Explorer V2 consumes the edition-stable Raw leaf sidecar. If the parent Raw
-- authority advanced without its leaves, repair only that exact target date,
-- validate count/value/fingerprint parity, commit the repair, and let the next
-- bounded invocation perform the heavier candidate build.

CREATE OR REPLACE FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '300s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_target date;
  v_processed integer := 0;
  v_remaining integer := 0;
  v_failed integer := 0;
  v_failures jsonb := '[]'::jsonb;
  v_latest_sealed date;
  v_stable_card_count integer;
  v_stable_basket_value numeric;
  v_stable_fingerprint text;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_leaf_fp_ok boolean;
  v_leaf_refresh jsonb;
  r record;
BEGIN
  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'pokemon-market-explorer-surface-v2-dependency-backstop', 0
    )
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

  SELECT
    h.card_count,
    h.basket_value,
    h.source_generation_fingerprint
  INTO
    v_stable_card_count,
    v_stable_basket_value,
    v_stable_fingerprint
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
  WHERE h.market_date=v_target;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'CURRENT_V2_EDITION_STABLE_RAW_MISSING';
  END IF;

  SELECT
    count(*)::integer,
    coalesce(sum(l.market_price),0)::numeric,
    coalesce(
      bool_and(l.raw_source_generation_fingerprint=v_stable_fingerprint),
      false
    )
  INTO v_leaf_count,v_leaf_value,v_leaf_fp_ok
  FROM public.pokemon_market_raw_edition_stable_leaf_history_v1 l
  WHERE l.market_date=v_target;

  IF v_leaf_count<>v_stable_card_count
     OR round(v_leaf_value,2)<>round(v_stable_basket_value,2)
     OR NOT v_leaf_fp_ok
  THEN
    BEGIN
      v_leaf_refresh:=
        public.refresh_pokemon_market_raw_edition_stable_leaves_v1(v_target);
    EXCEPTION WHEN OTHERS THEN
      RETURN jsonb_build_object(
        'status','blocked',
        'errorClass','raw_leaf_sidecar_refresh_failed',
        'marketDate',v_target,
        'sqlState',SQLSTATE
      );
    END;

    SELECT
      count(*)::integer,
      coalesce(sum(l.market_price),0)::numeric,
      coalesce(
        bool_and(l.raw_source_generation_fingerprint=v_stable_fingerprint),
        false
      )
    INTO v_leaf_count,v_leaf_value,v_leaf_fp_ok
    FROM public.pokemon_market_raw_edition_stable_leaf_history_v1 l
    WHERE l.market_date=v_target;

    IF v_leaf_count<>v_stable_card_count
       OR round(v_leaf_value,2)<>round(v_stable_basket_value,2)
       OR NOT v_leaf_fp_ok
    THEN
      RETURN jsonb_build_object(
        'status','blocked',
        'errorClass','raw_leaf_sidecar_reconciliation_failed',
        'marketDate',v_target,
        'leafCount',v_leaf_count,
        'expectedLeafCount',v_stable_card_count,
        'leafValue',round(v_leaf_value,2),
        'expectedLeafValue',round(v_stable_basket_value,2),
        'fingerprintCurrent',v_leaf_fp_ok
      );
    END IF;

    -- Commit the sidecar independently from the expensive V2 surface build.
    RETURN jsonb_build_object(
      'status','blocked',
      'errorClass','raw_leaf_sidecar_ready_for_build',
      'marketDate',v_target,
      'leafCount',v_leaf_count,
      'leafValue',round(v_leaf_value,2),
      'refreshReceipt',v_leaf_refresh
    );
  END IF;

  RETURN public.publish_pokemon_market_explorer_surface_current_core_v2();
END;
$function$;

ALTER FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
  OWNER TO postgres;
REVOKE ALL ON FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
  TO market_explorer_publisher, service_role;

COMMENT ON FUNCTION public.publish_pokemon_market_explorer_surface_current_v2() IS
'Bounded V2 dependency backstop. Repairs stale card/sealed prerequisites and the exact edition-stable Raw leaf sidecar before delegating to the core publisher; sidecar repair commits separately from the heavy candidate build.';

COMMIT;
