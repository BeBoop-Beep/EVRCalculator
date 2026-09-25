-- Applied to production as 20260925212955_bounded_composite_root_set_value_repair.
-- Repair one current-day composite root, preserving counted subsets and a frozen roster.
CREATE OR REPLACE FUNCTION public.repair_pokemon_market_composite_root_set_value_day_v1(p_root_set_id uuid, p_market_date date)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path = '' SET statement_timeout = '20s' SET lock_timeout = '2s'
AS $function$
DECLARE
  v_prices jsonb;
  v_count integer;
  v_unique integer;
  v_invalid integer;
  v_value numeric;
  v_methodology text;
  v_items jsonb;
  v_rows integer;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'An explicit root and market date are required';
  END IF;
  IF p_market_date IS DISTINCT FROM timezone('America/Phoenix', now())::date
     OR p_market_date IS DISTINCT FROM (
       SELECT max(b.market_date) FROM public.pokemon_scrape_batches b
       WHERE b.status='complete' AND b.promoted_at IS NOT NULL
         AND b.expected_set_count>0 AND b.succeeded_set_count=b.expected_set_count
         AND b.failed_set_count=0 AND b.missing_set_count=0
     ) THEN
    RAISE EXCEPTION 'Composite root repair requires the current completed promoted scrape date';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_root_authority a
    WHERE a.set_id=p_root_set_id AND a.enabled
      AND a.activated_market_date<=p_market_date
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
  ) OR NOT EXISTS (
    SELECT 1 FROM public.sets c WHERE c.parent_opening_set_id=p_root_set_id
      AND c.counts_toward_parent_set_value=true
  ) THEN
    RAISE EXCEPTION 'Requested set is not an active composite Market root';
  END IF;
  IF NOT pg_try_advisory_xact_lock(hashtextextended('composite-root-set-value:'||p_root_set_id::text||':'||p_market_date::text,0)) THEN
    RAISE EXCEPTION 'Composite root repair is already active' USING ERRCODE='55P03';
  END IF;
  IF (SELECT count(*) FROM public.pokemon_set_value_daily_history h
      WHERE h.set_id=p_root_set_id AND h.snapshot_date=p_market_date
        AND h.value_scope IN ('standard','top10') AND h.set_value>0 AND h.priced_card_count>0)=2 THEN
    RETURN jsonb_build_object('status','already_current','setId',p_root_set_id,'marketDate',p_market_date,'rowsUpserted',0);
  END IF;

  SELECT jsonb_agg(to_jsonb(p) ORDER BY p.canonical_card_id), count(*)::integer,
    count(DISTINCT p.canonical_card_id)::integer,
    count(*) FILTER (WHERE p.card_variant_id IS NULL OR p.market_price IS NULL
      OR p.market_price<=0 OR p.captured_at IS NULL OR p.captured_at>p_market_date
      OR p.canonical_review_status='needs_review' OR p.source IS DISTINCT FROM 'TCGPlayer')::integer,
    round(sum(p.market_price),2)
  INTO v_prices,v_count,v_unique,v_invalid,v_value
  FROM public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) p
  WHERE p.root_set_id=p_root_set_id AND p.market_scope='standard';
  IF v_count<10 OR v_unique<>v_count OR v_invalid<>0 OR v_value IS NULL OR v_value<=0 THEN
    RAISE EXCEPTION 'Composite root is not fully priceable: expected %, unique %, invalid %',v_count,v_unique,v_invalid;
  END IF;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
    source,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  VALUES(p_root_set_id,p_market_date,'standard',v_value,v_count,v_count,
    'canonical_root_set_public_rollout_candidate_v1',v_count,v_count,v_count,100)
  ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE SET
    set_value=excluded.set_value,priced_card_count=excluded.priced_card_count,
    total_card_count=excluded.total_card_count,source=excluded.source,
    canonical_card_count=excluded.canonical_card_count,linked_card_count=excluded.linked_card_count,
    included_card_count=excluded.included_card_count,coverage_pct=excluded.coverage_pct,updated_at=now();
  GET DIAGNOSTICS v_rows=ROW_COUNT;
  IF v_rows<>1 THEN RAISE EXCEPTION 'Canonical Standard write was not accepted'; END IF;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
    source,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  SELECT p_root_set_id,p_market_date,'top10',sum(x.market_price),10,10,
    'canonical_root_top10_public_rollout_candidate_v1',10,10,10,100
  FROM (SELECT (e->>'market_price')::numeric AS market_price
    FROM jsonb_array_elements(v_prices) e ORDER BY (e->>'market_price')::numeric DESC,e->>'canonical_card_id' LIMIT 10) x
  ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE SET
    set_value=excluded.set_value,priced_card_count=excluded.priced_card_count,
    total_card_count=excluded.total_card_count,source=excluded.source,
    canonical_card_count=excluded.canonical_card_count,linked_card_count=excluded.linked_card_count,
    included_card_count=excluded.included_card_count,coverage_pct=excluded.coverage_pct,updated_at=now();
  GET DIAGNOSTICS v_rows=ROW_COUNT;
  IF v_rows<>1 THEN RAISE EXCEPTION 'Canonical Top10 write was not accepted'; END IF;

  SELECT coalesce((SELECT h.methodology_version FROM public.pokemon_market_index_daily_history h
    WHERE h.tcg='pokemon' AND h.index_key='raw' AND h.market_date<=p_market_date
    ORDER BY h.market_date DESC,h.updated_at DESC LIMIT 1),'chain_linked_common_cohort_v1') INTO v_methodology;
  SELECT jsonb_agg(jsonb_build_object(
    'canonicalCardId',e->>'canonical_card_id','cardVariantId',e->>'card_variant_id',
    'setId',e->>'member_set_id','marketPrice',(e->>'market_price')::numeric,
    'capturedAt',e->>'captured_at','source',e->>'source','printingType',e->>'printing_type',
    'priceSelectionReason',e->>'price_selection_reason') ORDER BY e->>'canonical_card_id')
  INTO v_items FROM jsonb_array_elements(v_prices) e;
  PERFORM public.replace_pokemon_market_set_value_constituents_v1(
    p_root_set_id,p_market_date,v_methodology,v_value,v_count,
    'canonical_root_set_public_rollout_candidate_frozen_v1',v_items);
  RETURN jsonb_build_object('status','repaired','setId',p_root_set_id,'marketDate',p_market_date,
    'rowsUpserted',2,'pricedCards',v_count,'coveragePct',100,'setValue',v_value,'rosterFrozen',true);
END;
$function$;
REVOKE ALL ON FUNCTION public.repair_pokemon_market_composite_root_set_value_day_v1(uuid,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.repair_pokemon_market_composite_root_set_value_day_v1(uuid,date) TO service_role;
