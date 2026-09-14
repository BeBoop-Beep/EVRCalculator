-- Price Storage V2 serving cutover.
-- Additive V2 authority with an audited compatibility projection for existing readers.
-- No cron is attached and no release gate is enabled by this migration.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='20s';

CREATE TABLE public.price_storage_v2_legacy_set_value_backup (
  set_id uuid NOT NULL,
  snapshot_date date NOT NULL,
  value_scope text NOT NULL,
  set_value numeric,
  priced_card_count integer NOT NULL,
  total_card_count integer NOT NULL,
  source text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  canonical_card_count integer,
  linked_card_count integer,
  included_card_count integer,
  coverage_pct numeric,
  backed_up_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(set_id,snapshot_date,value_scope)
);

CREATE TABLE public.price_storage_v2_serving_transition_state (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  anchor_market_date date NOT NULL DEFAULT DATE '2026-09-08',
  anchor_applied_at timestamptz,
  root_row_count integer,
  member_row_count integer,
  compatibility_row_count integer,
  root_fingerprint text
);
INSERT INTO public.price_storage_v2_serving_transition_state(singleton)
VALUES(true)
ON CONFLICT(singleton) DO NOTHING;

CREATE TABLE public.price_storage_v2_serving_publication_receipts (
  market_date date PRIMARY KEY,
  root_count integer NOT NULL CHECK(root_count>0),
  root_fingerprint text NOT NULL,
  compatibility_row_count integer NOT NULL CHECK(compatibility_row_count>0),
  finalized_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.price_storage_v2_legacy_set_value_backup ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_storage_v2_serving_transition_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_storage_v2_serving_publication_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_storage_v2_legacy_set_value_backup,
 public.price_storage_v2_serving_transition_state,
 public.price_storage_v2_serving_publication_receipts
FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.price_storage_v2_legacy_set_value_backup TO service_role;
GRANT SELECT,INSERT,UPDATE ON public.price_storage_v2_serving_transition_state TO service_role;
GRANT SELECT,INSERT ON public.price_storage_v2_serving_publication_receipts TO service_role;

CREATE OR REPLACE FUNCTION public.guard_canonical_rollout_root_set_value_history_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
begin
    if new.value_scope not in ('standard','top10') then
        return new;
    end if;
    if coalesce(new.source,'') in (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1',
        'price_storage_v2_transition_anchor_v1',
        'price_storage_v2_serving_compatibility_v1'
    ) then
        return new;
    end if;
    if exists (
        select 1
        from public.pokemon_market_public_rollout_root_sets_v1 r
        where r.set_id = new.set_id
          and r.activated_market_date <= new.snapshot_date
          and (r.release_date is null or r.release_date <= new.snapshot_date)
          and exists (
              select 1
              from public.sets child
              where child.parent_opening_set_id = new.set_id
                and child.counts_toward_parent_set_value = true
          )
    ) then
        return null;
    end if;
    return new;
end;
$function$;

CREATE FUNCTION public.get_price_storage_v2_serving_compatibility_rows_v1(
  p_market_date date,
  p_root_set_ids uuid[]
) RETURNS TABLE(
  set_id uuid,
  snapshot_date date,
  value_scope text,
  set_value numeric,
  priced_card_count integer,
  total_card_count integer,
  coverage_pct numeric
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path=''
AS $function$
  SELECT h.set_id,h.snapshot_date,h.value_scope,h.set_value,h.priced_card_count,
         h.total_card_count,h.coverage_pct
  FROM public.pokemon_root_set_value_daily_history_v2 h
  WHERE h.snapshot_date=p_market_date
    AND h.set_id=ANY(p_root_set_ids)
    AND h.set_value IS NOT NULL
  UNION ALL
  SELECT h.set_id,h.snapshot_date,h.value_scope,h.set_value,h.priced_card_count,
         h.total_card_count,h.coverage_pct
  FROM public.pokemon_member_set_value_daily_history_v2 h
  WHERE h.snapshot_date=p_market_date
    AND h.root_set_id=ANY(p_root_set_ids)
    AND h.set_id<>h.root_set_id
    AND h.set_value IS NOT NULL
$function$;

CREATE FUNCTION public.apply_price_storage_v2_transition_anchor_v1(
  p_anchor_date date DEFAULT DATE '2026-09-08'
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_state public.price_storage_v2_serving_transition_state%rowtype;
  v_root_ids uuid[];
  v_root_rows integer;
  v_member_rows integer;
  v_expected integer;
  v_backup_rows integer;
  v_upserted integer;
  v_different integer;
  v_fingerprint text;
BEGIN
  IF p_anchor_date IS DISTINCT FROM DATE '2026-09-08' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='The serving transition anchor is fixed at 2026-09-08';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM public.price_storage_v2_scoped_release_gate WHERE singleton AND enabled) THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Scoped V2 release gate is disabled';
  END IF;
  SELECT array_agg(DISTINCT set_id ORDER BY set_id),count(*),
         md5(coalesce(string_agg(jsonb_build_array(set_id,value_scope,set_value,priced_card_count,total_card_count,basket_fingerprint)::text,'|' ORDER BY set_id,value_scope),''))
  INTO v_root_ids,v_root_rows,v_fingerprint
  FROM public.pokemon_root_set_value_daily_history_v2
  WHERE snapshot_date=p_anchor_date;
  IF v_root_rows<>318 OR cardinality(v_root_ids)<>106 THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='The frozen Sep 8 V2 root anchor is incomplete';
  END IF;
  SELECT count(*) INTO v_member_rows FROM public.pokemon_member_set_value_daily_history_v2 WHERE snapshot_date=p_anchor_date;
  IF v_member_rows<>348 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='The frozen Sep 8 V2 member anchor is incomplete'; END IF;
  SELECT * INTO v_state FROM public.price_storage_v2_serving_transition_state WHERE singleton FOR UPDATE;
  SELECT count(*) INTO v_expected FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_anchor_date,v_root_ids);
  IF v_state.anchor_applied_at IS NOT NULL THEN
    SELECT count(*) FILTER(WHERE l.set_id IS NULL OR ROW(l.set_value,l.priced_card_count,l.total_card_count,l.coverage_pct) IS DISTINCT FROM ROW(s.set_value,s.priced_card_count,s.total_card_count,s.coverage_pct))
    INTO v_different
    FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_anchor_date,v_root_ids) s
    LEFT JOIN public.pokemon_set_value_daily_history l ON l.set_id=s.set_id AND l.snapshot_date=s.snapshot_date AND l.value_scope=s.value_scope;
    IF v_different<>0 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Applied V2 transition anchor no longer matches compatibility history'; END IF;
    RETURN jsonb_build_object('status','noop','anchor_market_date',p_anchor_date,'root_rows',v_root_rows,'member_rows',v_member_rows,'compatibility_rows',v_expected,'root_fingerprint',v_fingerprint);
  END IF;
  INSERT INTO public.price_storage_v2_legacy_set_value_backup(set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,source,created_at,updated_at,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  SELECT l.set_id,l.snapshot_date,l.value_scope,l.set_value,l.priced_card_count,l.total_card_count,l.source,l.created_at,l.updated_at,l.canonical_card_count,l.linked_card_count,l.included_card_count,l.coverage_pct
  FROM public.pokemon_set_value_daily_history l
  JOIN public.get_price_storage_v2_serving_compatibility_rows_v1(p_anchor_date,v_root_ids) s ON s.set_id=l.set_id AND s.snapshot_date=l.snapshot_date AND s.value_scope=l.value_scope
  ON CONFLICT(set_id,snapshot_date,value_scope) DO NOTHING;
  GET DIAGNOSTICS v_backup_rows=ROW_COUNT;
  INSERT INTO public.pokemon_set_value_daily_history(set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,source,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  SELECT s.set_id,s.snapshot_date,s.value_scope,s.set_value,s.priced_card_count,s.total_card_count,'price_storage_v2_transition_anchor_v1',s.total_card_count,s.priced_card_count,s.priced_card_count,s.coverage_pct
  FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_anchor_date,v_root_ids) s
  ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE SET set_value=EXCLUDED.set_value,priced_card_count=EXCLUDED.priced_card_count,total_card_count=EXCLUDED.total_card_count,source=EXCLUDED.source,canonical_card_count=EXCLUDED.canonical_card_count,linked_card_count=EXCLUDED.linked_card_count,included_card_count=EXCLUDED.included_card_count,coverage_pct=EXCLUDED.coverage_pct;
  GET DIAGNOSTICS v_upserted=ROW_COUNT;
  SELECT count(*) FILTER(WHERE l.set_id IS NULL OR ROW(l.set_value,l.priced_card_count,l.total_card_count,l.coverage_pct,l.source) IS DISTINCT FROM ROW(s.set_value,s.priced_card_count,s.total_card_count,s.coverage_pct,'price_storage_v2_transition_anchor_v1'::text))
  INTO v_different
  FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_anchor_date,v_root_ids) s
  LEFT JOIN public.pokemon_set_value_daily_history l ON l.set_id=s.set_id AND l.snapshot_date=s.snapshot_date AND l.value_scope=s.value_scope;
  IF v_different<>0 OR v_upserted<>v_expected THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='V2 transition anchor failed exact compatibility reconciliation'; END IF;
  UPDATE public.price_storage_v2_serving_transition_state SET anchor_market_date=p_anchor_date,anchor_applied_at=now(),root_row_count=v_root_rows,member_row_count=v_member_rows,compatibility_row_count=v_expected,root_fingerprint=v_fingerprint WHERE singleton;
  RETURN jsonb_build_object('status','complete','anchor_market_date',p_anchor_date,'root_rows',v_root_rows,'member_rows',v_member_rows,'legacy_rows_backed_up',v_backup_rows,'compatibility_rows',v_upserted,'root_fingerprint',v_fingerprint);
END;
$function$;

CREATE FUNCTION public.publish_price_storage_v2_scoped_run_atomic_v2(p_run_id bigint,p_root_set_id uuid,p_market_date date) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path='' SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_run public.price_storage_v2_scope_stage_runs%rowtype;
  v_preview jsonb; v_candidates jsonb;
  v_member_expected integer; v_root_expected integer;
  v_member_inserted integer; v_root_inserted integer;
  v_member_count integer; v_root_count integer; v_different integer;
BEGIN
  IF p_run_id IS NULL OR p_root_set_id IS NULL OR p_market_date IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Explicit run, root and market date are required'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.price_storage_v2_scoped_release_gate WHERE singleton AND enabled) THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Scoped V2 release gate is disabled'; END IF;
  SELECT * INTO v_run FROM public.price_storage_v2_scope_stage_runs WHERE id=p_run_id;
  IF NOT FOUND OR v_run.root_set_id IS DISTINCT FROM p_root_set_id OR v_run.market_date IS DISTINCT FROM p_market_date OR v_run.status<>'parity_passed' OR v_run.definition_version IS DISTINCT FROM 'canonical_asof_scope_split_v2' THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Staged run/root/date is absent, blocked, or not date-safe v2 evidence';
  END IF;
  v_preview:=public.preview_price_storage_v2_scoped_values_v2(p_root_set_id,p_market_date);
  IF v_preview->>'status' IS DISTINCT FROM 'parity_passed' OR md5(v_preview::text) IS DISTINCT FROM v_run.evidence_signature THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Staged acceptance is stale; restage against current source evidence'; END IF;
  SELECT jsonb_agg(to_jsonb(c)-'run_id' ORDER BY c.universe_scope,c.set_id,c.value_scope) INTO v_candidates FROM public.price_storage_v2_scoped_value_candidates c WHERE c.run_id=p_run_id;
  IF v_candidates IS DISTINCT FROM v_preview->'candidate_values' THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Stored candidates differ from the independently recomputed basket'; END IF;
  SELECT count(*) FILTER(WHERE universe_scope='member'),count(*) FILTER(WHERE universe_scope='root') INTO v_member_expected,v_root_expected FROM public.price_storage_v2_scoped_value_candidates WHERE run_id=p_run_id AND market_scope='standard';
  IF v_member_expected=0 OR v_member_expected%3<>0 OR v_root_expected<>3 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Standard/Hits/Top10 candidates are incomplete'; END IF;
  INSERT INTO public.pokemon_member_set_value_daily_history_v2(set_id,root_set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,coverage_pct,fresh_card_count,basket_fingerprint,run_id,source)
  SELECT c.set_id,p_root_set_id,p_market_date,c.value_scope,c.set_value,c.priced_card_count,c.expected_card_count,c.coverage_pct,c.fresh_card_count,c.basket_fingerprint,c.run_id,'price_storage_v2_member_scope_v1'
  FROM public.price_storage_v2_scoped_value_candidates c WHERE c.run_id=p_run_id AND c.universe_scope='member' AND c.market_scope='standard'
  ON CONFLICT(set_id,snapshot_date,value_scope) DO NOTHING;
  GET DIAGNOSTICS v_member_inserted=ROW_COUNT;
  INSERT INTO public.pokemon_root_set_value_daily_history_v2(set_id,root_set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,coverage_pct,fresh_card_count,basket_fingerprint,run_id,source)
  SELECT c.set_id,p_root_set_id,p_market_date,c.value_scope,c.set_value,c.priced_card_count,c.expected_card_count,c.coverage_pct,c.fresh_card_count,c.basket_fingerprint,c.run_id,'price_storage_v2_root_scope_v1'
  FROM public.price_storage_v2_scoped_value_candidates c WHERE c.run_id=p_run_id AND c.universe_scope='root' AND c.market_scope='standard'
  ON CONFLICT(set_id,snapshot_date,value_scope) DO NOTHING;
  GET DIAGNOSTICS v_root_inserted=ROW_COUNT;
  SELECT count(h.set_id),count(*) FILTER(WHERE ROW(h.root_set_id,h.set_value,h.priced_card_count,h.total_card_count,h.coverage_pct,h.fresh_card_count,h.basket_fingerprint,h.run_id,h.source) IS DISTINCT FROM ROW(p_root_set_id,c.set_value,c.priced_card_count,c.expected_card_count,c.coverage_pct,c.fresh_card_count,c.basket_fingerprint,p_run_id,'price_storage_v2_member_scope_v1'::text))
  INTO v_member_count,v_different
  FROM public.price_storage_v2_scoped_value_candidates c LEFT JOIN public.pokemon_member_set_value_daily_history_v2 h ON h.set_id=c.set_id AND h.snapshot_date=p_market_date AND h.value_scope=c.value_scope
  WHERE c.run_id=p_run_id AND c.universe_scope='member' AND c.market_scope='standard';
  IF v_member_count<>v_member_expected OR v_different<>0 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Conflicting member V2 publication requires explicit correction/version policy'; END IF;
  SELECT count(h.set_id),count(*) FILTER(WHERE ROW(h.root_set_id,h.set_value,h.priced_card_count,h.total_card_count,h.coverage_pct,h.fresh_card_count,h.basket_fingerprint,h.run_id,h.source) IS DISTINCT FROM ROW(p_root_set_id,c.set_value,c.priced_card_count,c.expected_card_count,c.coverage_pct,c.fresh_card_count,c.basket_fingerprint,p_run_id,'price_storage_v2_root_scope_v1'::text))
  INTO v_root_count,v_different
  FROM public.price_storage_v2_scoped_value_candidates c LEFT JOIN public.pokemon_root_set_value_daily_history_v2 h ON h.set_id=c.set_id AND h.snapshot_date=p_market_date AND h.value_scope=c.value_scope
  WHERE c.run_id=p_run_id AND c.universe_scope='root' AND c.market_scope='standard';
  IF v_root_count<>v_root_expected OR v_different<>0 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Conflicting root V2 publication requires explicit correction/version policy'; END IF;
  RETURN jsonb_build_object('status',CASE WHEN v_member_inserted+v_root_inserted=0 THEN 'noop' ELSE 'complete' END,'run_id',p_run_id,'root_set_id',p_root_set_id,'market_date',p_market_date,'member_rows_inserted',v_member_inserted,'member_rows_verified',v_member_count,'root_rows_inserted',v_root_inserted,'root_rows_verified',v_root_count,'public_routing_changed',false,'scheduler_attached',false);
END;
$function$;

CREATE FUNCTION public.finalize_price_storage_v2_serving_compatibility_v1(p_market_date date,p_root_set_ids uuid[]) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path='' SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_root_ids uuid[]; v_root_count integer; v_root_rows integer; v_member_roots integer;
  v_expected integer; v_backup_rows integer; v_upserted integer; v_different integer; v_fingerprint text;
  v_receipt public.price_storage_v2_serving_publication_receipts%rowtype;
BEGIN
  IF p_market_date IS NULL OR p_market_date<DATE '2026-09-09' OR p_root_set_ids IS NULL OR cardinality(p_root_set_ids) NOT BETWEEN 1 AND 200 OR array_position(p_root_set_ids,NULL::uuid) IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Explicit post-cutover date and one to 200 non-null root IDs are required';
  END IF;
  SELECT array_agg(DISTINCT x ORDER BY x) INTO v_root_ids FROM unnest(p_root_set_ids)x;
  IF cardinality(v_root_ids) IS DISTINCT FROM cardinality(p_root_set_ids) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Duplicate root IDs are not allowed'; END IF;
  v_root_count:=cardinality(v_root_ids); v_fingerprint:=md5(array_to_string(v_root_ids,','));
  IF NOT EXISTS(SELECT 1 FROM public.price_storage_v2_scoped_release_gate WHERE singleton AND enabled) THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Scoped V2 release gate is disabled'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.price_storage_v2_serving_transition_state WHERE singleton AND anchor_applied_at IS NOT NULL AND anchor_market_date=DATE '2026-09-08') THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Sep 8 V2 transition anchor has not been applied'; END IF;
  SELECT count(*) INTO v_root_rows FROM public.pokemon_root_set_value_daily_history_v2 WHERE snapshot_date=p_market_date AND set_id=ANY(v_root_ids);
  IF v_root_rows<>v_root_count*3 OR EXISTS(SELECT set_id FROM public.pokemon_root_set_value_daily_history_v2 WHERE snapshot_date=p_market_date AND set_id=ANY(v_root_ids) GROUP BY set_id HAVING count(*)<>3 OR count(DISTINCT value_scope)<>3) THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Full root V2 cohort is not complete'; END IF;
  SELECT count(DISTINCT root_set_id) INTO v_member_roots FROM public.pokemon_member_set_value_daily_history_v2 WHERE snapshot_date=p_market_date AND root_set_id=ANY(v_root_ids);
  IF v_member_roots<>v_root_count THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Full member V2 cohort is not complete'; END IF;
  SELECT * INTO v_receipt FROM public.price_storage_v2_serving_publication_receipts WHERE market_date=p_market_date;
  IF FOUND THEN
    IF v_receipt.root_count<>v_root_count OR v_receipt.root_fingerprint<>v_fingerprint THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Existing V2 serving receipt has a different root authority'; END IF;
    SELECT count(*) FILTER(WHERE l.set_id IS NULL OR ROW(l.set_value,l.priced_card_count,l.total_card_count,l.coverage_pct,l.source) IS DISTINCT FROM ROW(s.set_value,s.priced_card_count,s.total_card_count,s.coverage_pct,'price_storage_v2_serving_compatibility_v1'::text)) INTO v_different
    FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_market_date,v_root_ids) s LEFT JOIN public.pokemon_set_value_daily_history l ON l.set_id=s.set_id AND l.snapshot_date=s.snapshot_date AND l.value_scope=s.value_scope;
    IF v_different<>0 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Finalized V2 compatibility rows no longer match isolated authority'; END IF;
    RETURN jsonb_build_object('status','noop','market_date',p_market_date,'root_count',v_root_count,'root_fingerprint',v_fingerprint,'compatibility_rows',v_receipt.compatibility_row_count,'finalized_at',v_receipt.finalized_at);
  END IF;
  SELECT count(*) INTO v_expected FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_market_date,v_root_ids);
  IF v_expected<v_root_count*2 THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='V2 compatibility projection is unexpectedly sparse'; END IF;
  INSERT INTO public.price_storage_v2_legacy_set_value_backup(set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,source,created_at,updated_at,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  SELECT l.set_id,l.snapshot_date,l.value_scope,l.set_value,l.priced_card_count,l.total_card_count,l.source,l.created_at,l.updated_at,l.canonical_card_count,l.linked_card_count,l.included_card_count,l.coverage_pct
  FROM public.pokemon_set_value_daily_history l JOIN public.get_price_storage_v2_serving_compatibility_rows_v1(p_market_date,v_root_ids) s ON s.set_id=l.set_id AND s.snapshot_date=l.snapshot_date AND s.value_scope=l.value_scope
  ON CONFLICT(set_id,snapshot_date,value_scope) DO NOTHING;
  GET DIAGNOSTICS v_backup_rows=ROW_COUNT;
  INSERT INTO public.pokemon_set_value_daily_history(set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,source,canonical_card_count,linked_card_count,included_card_count,coverage_pct)
  SELECT s.set_id,s.snapshot_date,s.value_scope,s.set_value,s.priced_card_count,s.total_card_count,'price_storage_v2_serving_compatibility_v1',s.total_card_count,s.priced_card_count,s.priced_card_count,s.coverage_pct
  FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_market_date,v_root_ids) s
  ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE SET set_value=EXCLUDED.set_value,priced_card_count=EXCLUDED.priced_card_count,total_card_count=EXCLUDED.total_card_count,source=EXCLUDED.source,canonical_card_count=EXCLUDED.canonical_card_count,linked_card_count=EXCLUDED.linked_card_count,included_card_count=EXCLUDED.included_card_count,coverage_pct=EXCLUDED.coverage_pct;
  GET DIAGNOSTICS v_upserted=ROW_COUNT;
  SELECT count(*) FILTER(WHERE l.set_id IS NULL OR ROW(l.set_value,l.priced_card_count,l.total_card_count,l.coverage_pct,l.source) IS DISTINCT FROM ROW(s.set_value,s.priced_card_count,s.total_card_count,s.coverage_pct,'price_storage_v2_serving_compatibility_v1'::text)) INTO v_different
  FROM public.get_price_storage_v2_serving_compatibility_rows_v1(p_market_date,v_root_ids) s LEFT JOIN public.pokemon_set_value_daily_history l ON l.set_id=s.set_id AND l.snapshot_date=s.snapshot_date AND l.value_scope=s.value_scope;
  IF v_different<>0 OR v_upserted<>v_expected THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='V2 compatibility finalization failed exact reconciliation'; END IF;
  INSERT INTO public.price_storage_v2_serving_publication_receipts(market_date,root_count,root_fingerprint,compatibility_row_count) VALUES(p_market_date,v_root_count,v_fingerprint,v_expected);
  RETURN jsonb_build_object('status','complete','market_date',p_market_date,'root_count',v_root_count,'root_fingerprint',v_fingerprint,'compatibility_rows',v_upserted,'legacy_rows_backed_up',v_backup_rows,'public_routing_changed',false,'scheduler_attached',false);
END;
$function$;

REVOKE ALL ON FUNCTION public.get_price_storage_v2_serving_compatibility_rows_v1(date,uuid[]), public.apply_price_storage_v2_transition_anchor_v1(date), public.publish_price_storage_v2_scoped_run_atomic_v2(bigint,uuid,date), public.finalize_price_storage_v2_serving_compatibility_v1(date,uuid[]) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_price_storage_v2_serving_compatibility_rows_v1(date,uuid[]), public.apply_price_storage_v2_transition_anchor_v1(date), public.publish_price_storage_v2_scoped_run_atomic_v2(bigint,uuid,date), public.finalize_price_storage_v2_serving_compatibility_v1(date,uuid[]) TO service_role;

COMMENT ON FUNCTION public.apply_price_storage_v2_transition_anchor_v1(date) IS 'One-time Sep 8 V2 baseline projection for transition-safe set history. Backs up overwritten legacy rows, requires the operator release gate, and never changes persisted Market index/snapshot history.';
COMMENT ON FUNCTION public.publish_price_storage_v2_scoped_run_atomic_v2(bigint,uuid,date) IS 'One-root atomic V2 publisher. Revalidates staged evidence once and writes member+root isolated V2 history together. It does not project public compatibility rows.';
COMMENT ON FUNCTION public.finalize_price_storage_v2_serving_compatibility_v1(date,uuid[]) IS 'All-roots compatibility finalizer. Requires a complete isolated V2 root/member cohort and Sep 8 transition anchor, then flips the existing history reader projection once and records an immutable cohort receipt.';

COMMIT;