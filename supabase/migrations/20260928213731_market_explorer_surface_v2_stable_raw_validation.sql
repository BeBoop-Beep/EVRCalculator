BEGIN;

CREATE OR REPLACE FUNCTION public.validate_pokemon_market_explorer_surface_candidate_v2(p_generation_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '60s'
AS $function$
DECLARE
  v_state text;
  v_market_date date;
  v_issues jsonb:='[]'::jsonb;
  v_n integer;
  v_raw_reconciled boolean:=false;
BEGIN
  SELECT state,market_date INTO v_state,v_market_date
  FROM public.pokemon_market_explorer_surface_generations_v2
  WHERE generation_id=p_generation_id
  FOR UPDATE;

  IF NOT FOUND OR v_state NOT IN ('BUILT','VALIDATED','REJECTED') THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_NOT_BUILT';
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id AND d.history_available
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_market_explorer_surface_history_v2 h
      WHERE h.generation_id=d.generation_id AND h.market_key=d.market_key
        AND h.market_date=v_market_date
    );
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','HISTORY_NOT_CURRENT','count',v_n));
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_constituent_totals_v2 t
  LEFT JOIN LATERAL (
    SELECT count(*)::integer n,max(rank)::integer mx,count(distinct instrument_id)::integer instruments
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    WHERE c.generation_id=t.generation_id AND c.market_key=t.market_key
  ) x ON true
  WHERE t.generation_id=p_generation_id
    AND (
      (t.availability='available' AND (x.n<>t.total_count OR x.mx<>t.total_count OR x.instruments<>t.total_count))
      OR (t.availability='empty' AND x.n<>0)
    );
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','CONSTITUENT_PAGING_INVARIANT','count',v_n));
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.composition_kind IN ('composition','index_and_composition')
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_market_explorer_surface_constituent_totals_v2 t
      WHERE t.generation_id=d.generation_id AND t.market_key=d.market_key
    );
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','MISSING_CONSTITUENT_TOTAL','count',v_n));
  END IF;

  -- V2 Raw is edition-stable. Validate the actual staged Raw surface against
  -- pokemon_market_raw_edition_stable_daily_history_v1 rather than requiring
  -- the legacy generic-vintage raw_composition_runs_v1 sidecar.
  WITH stable AS (
    SELECT h.basket_value,h.card_count
    FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
    WHERE h.market_date=v_market_date
  ),
  directory AS (
    SELECT d.current_tracked_value,d.constituent_count,d.metadata
    FROM public.pokemon_market_explorer_surface_directory_v2 d
    WHERE d.generation_id=p_generation_id AND d.market_key='raw'
  ),
  totals AS (
    SELECT t.total_count,t.availability
    FROM public.pokemon_market_explorer_surface_constituent_totals_v2 t
    WHERE t.generation_id=p_generation_id AND t.market_key='raw'
  ),
  leaves AS (
    SELECT count(*)::integer AS leaf_count,
           count(DISTINCT c.instrument_id)::integer AS unique_leaf_count,
           round(coalesce(sum(c.market_price),0),2) AS leaf_value
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    WHERE c.generation_id=p_generation_id AND c.market_key='raw'
  )
  SELECT coalesce(
    round(d.current_tracked_value,2)=round(s.basket_value,2)
    AND d.constituent_count=s.card_count
    AND t.availability='available'
    AND t.total_count=s.card_count
    AND l.leaf_count=s.card_count
    AND l.unique_leaf_count=s.card_count
    AND round(l.leaf_value,2)=round(s.basket_value,2)
    AND coalesce((d.metadata->>'editionStable')::boolean,false),
    false
  )
  INTO v_raw_reconciled
  FROM stable s
  CROSS JOIN directory d
  CROSS JOIN totals t
  CROSS JOIN leaves l;

  IF NOT v_raw_reconciled THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','RAW_COMPOSITION_NOT_RECONCILED'));
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  JOIN public.pokemon_market_explorer_card_current_metadata m
    ON c.asset='cards' AND c.instrument_id=m.card_variant_id::text
  LEFT JOIN public.card_variants cv ON cv.id=m.card_variant_id
  LEFT JOIN public.pokemon_canonical_cards cc ON cc.id=m.canonical_card_id
  WHERE c.generation_id=p_generation_id
    AND coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url) IS NOT NULL
    AND nullif(c.item->>'imageUrl','') IS NULL;
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','CARD_IMAGE_DROPPED','count',v_n));
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  WHERE c.generation_id=p_generation_id AND c.market_key='sealedMarket'
    AND (c.item->>'isBulkContainer')::boolean IS true;
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','TOTAL_SEALED_CONTAINS_BULK_CONTAINER','count',v_n));
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_history_v2 h
  WHERE h.generation_id=p_generation_id AND h.market_date>v_market_date;
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','FUTURE_LOOKAHEAD','count',v_n));
  END IF;

  UPDATE public.pokemon_market_explorer_surface_generations_v2
  SET state=CASE WHEN jsonb_array_length(v_issues)=0 THEN 'VALIDATED' ELSE 'REJECTED' END,
      validated_at=clock_timestamp(),
      diagnostics=diagnostics||jsonb_build_object(
        'validationIssues',v_issues,
        'rawValidationAuthority','pokemon_market_raw_edition_stable_daily_history_v1'
      )
  WHERE generation_id=p_generation_id;

  RETURN jsonb_build_object(
    'generationId',p_generation_id,
    'state',CASE WHEN jsonb_array_length(v_issues)=0 THEN 'VALIDATED' ELSE 'REJECTED' END,
    'issues',v_issues,
    'directoryRows',(SELECT count(*) FROM public.pokemon_market_explorer_surface_directory_v2 WHERE generation_id=p_generation_id),
    'historyRows',(SELECT count(*) FROM public.pokemon_market_explorer_surface_history_v2 WHERE generation_id=p_generation_id),
    'constituentRows',(SELECT count(*) FROM public.pokemon_market_explorer_surface_constituents_v2 WHERE generation_id=p_generation_id)
  );
END;
$function$


COMMIT;
