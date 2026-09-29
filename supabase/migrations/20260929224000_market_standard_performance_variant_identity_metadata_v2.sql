BEGIN;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO ''
SET statement_timeout TO '180s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  v_refresh jsonb;
  v_markets integer:=0;
  v_history integer:=0;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'STANDARD_SET_PERFORMANCE_ARGUMENTS_REQUIRED';
  END IF;

  v_refresh:=public.refresh_pokemon_market_standard_performance_adjustments_v1(
    p_market_date,100
  );

  IF coalesce(v_refresh->>'status','') <> 'complete' THEN
    RAISE EXCEPTION 'STANDARD_SET_PERFORMANCE_ADJUSTMENTS_NOT_CONVERGED: %',
      coalesce(v_refresh::text,'null');
  END IF;

  DROP TABLE IF EXISTS pg_temp._mx_standard_markets;
  CREATE TEMP TABLE _mx_standard_markets ON COMMIT DROP AS
  SELECT DISTINCT d.market_key,d.set_id
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.asset='cards'
    AND d.scope_kind='set'
    AND d.set_id IS NOT NULL
    AND d.market_key='set:'||d.set_id::text
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=d.set_id
    );

  CREATE UNIQUE INDEX ON _mx_standard_markets(market_key);
  CREATE INDEX ON _mx_standard_markets(set_id);
  ANALYZE _mx_standard_markets;

  SELECT count(*)::integer INTO v_markets FROM _mx_standard_markets;

  DROP TABLE IF EXISTS pg_temp._mx_standard_perf;
  CREATE TEMP TABLE _mx_standard_perf ON COMMIT DROP AS
  SELECT
    m.market_key,m.set_id,h.market_date,h.index_value,h.tracked_value,h.priced_card_count
  FROM _mx_standard_markets m
  JOIN public.pokemon_market_standard_performance_daily_v1 h
    ON h.set_id=m.set_id
   AND h.market_date<=p_market_date;

  CREATE INDEX ON _mx_standard_perf(market_key,market_date);
  ANALYZE _mx_standard_perf;

  DELETE FROM public.pokemon_market_explorer_surface_history_v2 h
  USING _mx_standard_markets m
  WHERE h.generation_id=p_generation_id
    AND h.market_key=m.market_key;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,
    constituent_count,chain_segment_id
  )
  SELECT
    p_generation_id,h.market_key,h.market_date,h.index_value,h.tracked_value,
    h.priced_card_count,0
  FROM _mx_standard_perf h
  ORDER BY h.market_key,h.market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  WITH stats AS (
    SELECT
      h.market_key,
      min(h.market_date) AS history_start_date,
      max(h.market_date) AS history_end_date,
      count(*)::integer AS history_point_count,
      max(h.index_value) FILTER (WHERE h.market_date=p_market_date) AS current_index_value,
      max(h.tracked_value) FILTER (WHERE h.market_date=p_market_date) AS current_tracked_value
    FROM _mx_standard_perf h
    GROUP BY h.market_key
  )
  UPDATE public.pokemon_market_explorer_surface_directory_v2 d
  SET source_kind='root_standard_common_cohort_v2',
      source_as_of=p_market_date,
      current_index_value=s.current_index_value,
      current_tracked_value=coalesce(s.current_tracked_value,d.current_tracked_value),
      history_available=(s.history_point_count>0),
      history_start_date=s.history_start_date,
      history_end_date=s.history_end_date,
      history_point_count=s.history_point_count,
      definition_version='standard_common_cohort_variant_identity_v2',
      metadata=coalesce(d.metadata,'{}'::jsonb)||jsonb_build_object(
        'performanceMethodology','standard_common_cohort_variant_identity_v2',
        'cohortEntryExitNeutralized',true,
        'variantIdentityChangeNeutralized',true,
        'printIdentityStable',true,
        'staleToFreshRepriceNeutralized',true,
        'largeMoveReviewThresholdPct',5,
        'staleRepriceGapDays',30,
        'stageMaterialization','single_pass_temp_v2'
      ),
      generated_at=pg_catalog.clock_timestamp()
  FROM stats s
  WHERE d.generation_id=p_generation_id
    AND d.market_key=s.market_key;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'marketCount',v_markets,
    'historyRows',v_history,
    'adjustmentRefresh',v_refresh,
    'stageMaterialization','single_pass_temp_v2',
    'methodologyVersion','standard_common_cohort_variant_identity_v2'
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(uuid,date)
  TO service_role;

COMMIT;