SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='20s';
DO $precondition$
BEGIN
 IF md5(pg_get_functiondef('public.publish_pokemon_set_value_daily_history_v2_shadow(date)'::regprocedure)) <> 'd2d90f7d8a8a14b4f472511e7bd9fcdb' THEN
  RAISE EXCEPTION 'Member publisher changed concurrently; inspect before installing guard';
 END IF;
 IF to_regprocedure('public.preflight_price_storage_v2_member_publication(date)') IS NOT NULL THEN
  RAISE EXCEPTION 'Preflight already exists; do not overwrite concurrent work';
 END IF;
END;
$precondition$;

INSERT INTO public.price_storage_v2_migration_audit(phase,details)
SELECT 'member_scope_publication_guard_before',jsonb_build_object(
 'publisher_definition_before',pg_get_functiondef('public.publish_pokemon_set_value_daily_history_v2_shadow(date)'::regprocedure),
 'publisher_acl_before',(SELECT proacl::text FROM pg_proc WHERE oid='public.publish_pokemon_set_value_daily_history_v2_shadow(date)'::regprocedure),
 'reason','Member-only shadow cannot overwrite mixed member/root and historical-definition series without independent acceptance',
 'historical_rows_modified',false
);

CREATE FUNCTION public.preflight_price_storage_v2_member_publication(p_through_date date)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=''
AS $function$
DECLARE v_result jsonb;
BEGIN
 IF p_through_date IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='through date is required';
 END IF;
 WITH legacy AS MATERIALIZED (
  SELECT * FROM public.pokemon_set_value_daily_history WHERE snapshot_date<=p_through_date
 ), candidate AS MATERIALIZED (
  SELECT * FROM public.pokemon_set_value_daily_history_v2_shadow WHERE snapshot_date<=p_through_date
 ), paired AS MATERIALIZED (
  SELECT coalesce(h.set_id,v.set_id) set_id,coalesce(h.snapshot_date,v.snapshot_date) snapshot_date,
   coalesce(h.value_scope,v.value_scope) value_scope,h.set_id IS NULL candidate_only,v.set_id IS NULL legacy_only,
   h.set_id IS NOT NULL AND v.set_id IS NOT NULL AS shared,
   h.set_value IS DISTINCT FROM v.set_value AS value_diff,
   ROW(h.priced_card_count,h.total_card_count,h.canonical_card_count,h.linked_card_count,h.included_card_count,h.coverage_pct)
    IS DISTINCT FROM ROW(v.priced_card_count,v.total_card_count,v.canonical_card_count,v.linked_card_count,v.included_card_count,v.coverage_pct) AS coverage_diff,
   CASE WHEN h.set_id IS NULL THEN 'no_stored_key'
        WHEN h.source LIKE 'canonical_root_%' THEN 'combined_root_rollout'
        WHEN h.source LIKE '%card_variants_by_set%' THEN 'older_variant_universe'
        WHEN h.source LIKE 'historical_correction:%' THEN 'explicit_historical_correction'
        WHEN h.source LIKE 'card_variant_price_observations%canonical_checklist' THEN 'member_canonical_checklist'
        ELSE 'other' END AS stored_contract
  FROM legacy h FULL JOIN candidate v USING(set_id,snapshot_date,value_scope)
 ), summary AS (
  SELECT count(*) FILTER(WHERE shared) shared_keys,
   count(*) FILTER(WHERE candidate_only) candidate_only_keys,count(*) FILTER(WHERE legacy_only) legacy_only_keys,
   count(*) FILTER(WHERE shared AND (value_diff OR coverage_diff)) differing_shared_keys,
   count(*) FILTER(WHERE shared AND value_diff) value_difference_keys,
   count(*) FILTER(WHERE shared AND coverage_diff AND NOT value_diff) coverage_only_difference_keys
  FROM paired
 ), grouped AS (
  SELECT stored_contract,count(*) FILTER(WHERE shared) shared_keys,
   count(*) FILTER(WHERE shared AND (value_diff OR coverage_diff)) differing_shared_keys,
   count(*) FILTER(WHERE shared AND value_diff) value_difference_keys,
   count(*) FILTER(WHERE shared AND coverage_diff AND NOT value_diff) coverage_only_difference_keys,
   count(*) FILTER(WHERE candidate_only) candidate_only_keys,count(*) FILTER(WHERE legacy_only) legacy_only_keys
  FROM paired GROUP BY stored_contract
 ), context AS (
  SELECT (SELECT count(*) FROM candidate) candidate_rows,
   (SELECT max(q.market_date) FROM public.pokemon_market_date_quality q WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED')) latest_approved_date,
   (SELECT count(*) FROM public.pokemon_set_value_daily_history_v2_backfill_sets q WHERE q.status<>'complete' OR q.through_date<p_through_date) incomplete_backfill_sets,
   (SELECT count(DISTINCT c.set_id) FROM candidate c WHERE NOT EXISTS (
     SELECT 1 FROM public.pokemon_set_value_daily_history_v2_backfill_sets q
     WHERE q.set_id=c.set_id AND q.status='complete' AND q.through_date>=p_through_date)) unverified_candidate_sets
 )
 SELECT jsonb_build_object('through_date',p_through_date,'latest_approved_date',c.latest_approved_date,
  'candidate_rows',c.candidate_rows,'shared_keys',s.shared_keys,'candidate_only_keys',s.candidate_only_keys,
  'legacy_only_keys',s.legacy_only_keys,'differing_shared_keys',s.differing_shared_keys,
  'value_difference_keys',s.value_difference_keys,'coverage_only_difference_keys',s.coverage_only_difference_keys,
  'incomplete_backfill_sets',c.incomplete_backfill_sets,'unverified_candidate_sets',c.unverified_candidate_sets,
  'contract_breakdown',(SELECT jsonb_agg(to_jsonb(g) ORDER BY stored_contract) FROM grouped g),
  'safe_noop',coalesce(c.candidate_rows>0 AND p_through_date<=c.latest_approved_date AND c.incomplete_backfill_sets=0
   AND c.unverified_candidate_sets=0 AND s.candidate_only_keys=0 AND s.legacy_only_keys=0 AND s.differing_shared_keys=0,false),
  'publication_writes_authorized',false)
 INTO v_result FROM summary s CROSS JOIN context c;
 RETURN v_result;
END;
$function$;

CREATE OR REPLACE FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(p_through_date date)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
AS $function$
DECLARE v_preflight jsonb;
BEGIN
 v_preflight:=public.preflight_price_storage_v2_member_publication(p_through_date);
 IF NOT coalesce((v_preflight->>'safe_noop')::boolean,false) THEN
  RAISE EXCEPTION USING ERRCODE='23514',
   MESSAGE='PRICE_STORAGE_V2_MEMBER_SCOPE_NOT_ACCEPTED: publication blocked before writes',
   DETAIL=v_preflight::text,
   HINT='Preserve member/root scope and historical provenance. Use independently validated scope-specific migration, not bulk shadow overwrite.';
 END IF;
 -- Exact data needs no rewrite; retain source labels and original publication timestamps.
 RETURN v_preflight || jsonb_build_object('status','already_exact_noop','upserted_rows',0,'deleted_rows',0);
END;
$function$;

REVOKE ALL ON FUNCTION public.preflight_price_storage_v2_member_publication(date) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.preflight_price_storage_v2_member_publication(date) TO service_role;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(date) TO service_role;
COMMENT ON FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(date) IS 'Safety interlock: incompatible member-only candidate publication is rejected before DML. Exact comparison is a no-op preserving provenance. Original definition retained in migration audit.';
NOTIFY pgrst,'reload schema';