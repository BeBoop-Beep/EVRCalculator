-- REVIEW-ONLY PROPOSAL: not installed and not in an executable migration folder.
-- Forward-only successor to the already-applied canonical_asof_scope_split_v1 stage.
-- The v1 functions remain untouched for historical auditability.
--
-- v1 compares an approved-date as-of reconstruction against a moving `latest`
-- root reader, including captured_at/source. Once the latest reader advances past
-- the approved market date, economically correct as-of rows can all appear
-- different. v2 keeps raw<->V2 as-of parity fail-closed, validates root identity,
-- and only requires full latest-root economic equality when that latest reader has
-- not advanced beyond the approved date. Storage provenance (`source`) is not an
-- economic field and is intentionally excluded from the normalized comparison.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';

CREATE FUNCTION public.preview_price_storage_v2_scoped_values_v2(
  p_root_set_id uuid,
  p_market_date date
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path=''
SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_payload jsonb;
  v_members uuid[];
  v_comparison jsonb;
  v_reason text;
  v_live_max date;
  v_live_future_rows integer := 0;
  v_identity_live_only integer := 0;
  v_identity_proposed_only integer := 0;
  v_economic_live_only integer := 0;
  v_economic_proposed_only integer := 0;
  v_economic_applicable boolean := false;
BEGIN
  -- Preserve every existing v1 guard: approved date, edition exclusions,
  -- function-definition hashes, source/shadow receipts, raw<->V2 parity,
  -- coverage, review state and candidate-value construction.
  v_payload := public.preview_price_storage_v2_scoped_values(p_root_set_id,p_market_date);
  v_payload := jsonb_set(
    v_payload,
    '{context,definition_version}',
    to_jsonb('canonical_asof_scope_split_v2'::text),
    true
  );

  -- Only the moving-latest comparison is being revised. Any unrelated v1 block
  -- remains a hard block and is returned unchanged apart from definition metadata.
  IF v_payload->>'status'='blocked'
     AND v_payload->>'reason' IS DISTINCT FROM 'live_root_contract_mismatch' THEN
    RETURN v_payload;
  END IF;

  SELECT array_agg(s.id ORDER BY s.id)
    INTO v_members
  FROM public.sets s
  WHERE s.id=p_root_set_id
     OR (s.parent_opening_set_id=p_root_set_id AND s.counts_toward_parent_set_value=true);

  WITH live_root AS MATERIALIZED (
    SELECT r.canonical_card_id,
           r.member_set_id,
           r.card_variant_id,
           r.market_price,
           r.captured_at
    FROM public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) r
    WHERE r.market_scope='standard'
  ),
  proposed_identity AS MATERIALIZED (
    SELECT c.id AS canonical_card_id,c.set_id AS member_set_id
    FROM public.pokemon_canonical_cards c
    WHERE c.set_id=ANY(v_members)
      AND c.set_value_eligible=true
  ),
  live_identity AS MATERIALIZED (
    SELECT canonical_card_id,member_set_id FROM live_root
  ),
  proposed_root AS MATERIALIZED (
    SELECT r.canonical_card_id,
           r.set_id AS member_set_id,
           r.card_variant_id,
           r.market_price,
           r.captured_at
    FROM unnest(v_members) m(id)
    CROSS JOIN LATERAL public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(m.id,p_market_date) r
  ),
  live_identity_only AS (
    SELECT * FROM live_identity EXCEPT ALL SELECT * FROM proposed_identity
  ),
  proposed_identity_only AS (
    SELECT * FROM proposed_identity EXCEPT ALL SELECT * FROM live_identity
  ),
  live_economic_only AS (
    SELECT * FROM live_root EXCEPT ALL SELECT * FROM proposed_root
  ),
  proposed_economic_only AS (
    SELECT * FROM proposed_root EXCEPT ALL SELECT * FROM live_root
  )
  SELECT
    (SELECT max(captured_at) FROM live_root),
    (SELECT count(*)::integer FROM live_root WHERE captured_at>p_market_date),
    (SELECT count(*)::integer FROM live_identity_only),
    (SELECT count(*)::integer FROM proposed_identity_only),
    (SELECT count(*)::integer FROM live_economic_only),
    (SELECT count(*)::integer FROM proposed_economic_only)
  INTO v_live_max,v_live_future_rows,
       v_identity_live_only,v_identity_proposed_only,
       v_economic_live_only,v_economic_proposed_only;

  v_economic_applicable := coalesce(v_live_max,p_market_date)<=p_market_date;

  v_comparison := coalesce(v_payload->'comparison','{}'::jsonb) || jsonb_build_object(
    'v1_live_root_only_rows',coalesce((v_payload#>>'{comparison,live_root_only_rows}')::integer,0),
    'v1_proposed_root_only_rows',coalesce((v_payload#>>'{comparison,proposed_root_only_rows}')::integer,0),
    'root_identity_live_only_rows',v_identity_live_only,
    'root_identity_proposed_only_rows',v_identity_proposed_only,
    'root_economic_live_only_rows',v_economic_live_only,
    'root_economic_proposed_only_rows',v_economic_proposed_only,
    'live_root_max_captured_at',v_live_max,
    'live_root_future_rows',v_live_future_rows,
    'live_root_economic_comparison_applicable',v_economic_applicable,
    'latest_root_storage_provenance_ignored',true
  );
  v_payload := jsonb_set(v_payload,'{comparison}',v_comparison,true);

  v_reason := CASE
    WHEN coalesce((v_comparison->>'raw_only_rows')::integer,-1)<>0
      OR coalesce((v_comparison->>'v2_only_rows')::integer,-1)<>0
      THEN 'raw_v2_price_contract_mismatch'
    WHEN coalesce((v_comparison->>'duplicate_raw_keys')::integer,-1)<>0
      OR coalesce((v_comparison->>'duplicate_v2_keys')::integer,-1)<>0
      THEN 'duplicate_price_identity'
    WHEN coalesce((v_comparison->>'missing_prices')::integer,-1)<>0
      THEN 'incomplete_price_coverage'
    WHEN coalesce((v_comparison->>'needs_review_cards')::integer,-1)<>0
      THEN 'canonical_review_required'
    WHEN v_identity_live_only<>0 OR v_identity_proposed_only<>0
      THEN 'live_root_identity_mismatch'
    WHEN v_economic_applicable
      AND (v_economic_live_only<>0 OR v_economic_proposed_only<>0)
      THEN 'live_root_economic_mismatch'
    ELSE 'exact_source_gated_scope_parity_v2'
  END;

  v_payload := jsonb_set(v_payload,'{reason}',to_jsonb(v_reason),true);
  v_payload := jsonb_set(
    v_payload,
    '{status}',
    to_jsonb(CASE WHEN v_reason='exact_source_gated_scope_parity_v2' THEN 'parity_passed' ELSE 'blocked' END::text),
    true
  );
  RETURN v_payload;
END;
$function$;

CREATE FUNCTION public.stage_price_storage_v2_scoped_values_v2(
  p_root_set_ids uuid[],
  p_market_date date
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_root uuid;
  v_payload jsonb;
  v_signature text;
  v_run_id bigint;
  v_inserted integer;
  v_results jsonb:='[]'::jsonb;
BEGIN
  IF p_root_set_ids IS NULL OR cardinality(p_root_set_ids) NOT BETWEEN 1 AND 10
     OR array_position(p_root_set_ids,NULL::uuid) IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Provide one to ten non-null root set IDs';
  END IF;

  FOR v_root IN
    SELECT DISTINCT u.id FROM unnest(p_root_set_ids)u(id) ORDER BY u.id
  LOOP
    v_payload:=public.preview_price_storage_v2_scoped_values_v2(v_root,p_market_date);
    v_signature:=md5(v_payload::text);
    v_run_id:=NULL;
    v_inserted:=0;

    INSERT INTO public.price_storage_v2_scope_stage_runs(
      root_set_id,market_date,definition_version,status,reason,evidence_signature,evidence
    )
    VALUES(
      v_root,p_market_date,'canonical_asof_scope_split_v2',v_payload->>'status',
      v_payload->>'reason',v_signature,v_payload-'candidate_values'
    )
    ON CONFLICT(root_set_id,market_date,evidence_signature) DO NOTHING
    RETURNING id INTO v_run_id;

    IF v_run_id IS NOT NULL AND v_payload->>'status'='parity_passed' THEN
      INSERT INTO public.price_storage_v2_scoped_value_candidates(
        run_id,universe_scope,set_id,market_scope,value_scope,set_value,
        expected_card_count,priced_card_count,subset_priced_card_count,fresh_card_count,
        coverage_pct,oldest_observed_date,newest_observed_date,basket_fingerprint
      )
      SELECT v_run_id,r.universe_scope,r.set_id,r.market_scope,r.value_scope,r.set_value,
             r.expected_card_count,r.priced_card_count,r.subset_priced_card_count,
             r.fresh_card_count,r.coverage_pct,r.oldest_observed_date,
             r.newest_observed_date,r.basket_fingerprint
      FROM jsonb_to_recordset(v_payload->'candidate_values') AS r(
        universe_scope text,set_id uuid,market_scope text,value_scope text,
        set_value numeric,expected_card_count integer,priced_card_count integer,
        subset_priced_card_count integer,fresh_card_count integer,coverage_pct numeric,
        oldest_observed_date date,newest_observed_date date,basket_fingerprint text
      );
      GET DIAGNOSTICS v_inserted=ROW_COUNT;
    ELSIF v_run_id IS NULL THEN
      SELECT r.id INTO v_run_id
      FROM public.price_storage_v2_scope_stage_runs r
      WHERE r.root_set_id=v_root
        AND r.market_date=p_market_date
        AND r.evidence_signature=v_signature;
    END IF;

    v_results:=v_results||jsonb_build_array(jsonb_build_object(
      'root_set_id',v_root,
      'root_name',v_payload#>>'{context,root_name}',
      'run_id',v_run_id,
      'status',v_payload->>'status',
      'reason',v_payload->>'reason',
      'new_candidate_rows',v_inserted
    ));
  END LOOP;

  RETURN jsonb_build_object(
    'market_date',p_market_date,
    'definition_version','canonical_asof_scope_split_v2',
    'results',v_results,
    'publication_authorized',false
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.preview_price_storage_v2_scoped_values_v2(uuid,date)
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.stage_price_storage_v2_scoped_values_v2(uuid[],date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.preview_price_storage_v2_scoped_values_v2(uuid,date),
 public.stage_price_storage_v2_scoped_values_v2(uuid[],date)
TO service_role;

COMMENT ON FUNCTION public.preview_price_storage_v2_scoped_values_v2(uuid,date)
IS 'Date-safe successor to canonical_asof_scope_split_v1. Preserves raw/V2 as-of and source-receipt gates; validates root identity against latest contract; only requires latest-root economic equality when latest has not advanced past the approved date.';
COMMENT ON FUNCTION public.stage_price_storage_v2_scoped_values_v2(uuid[],date)
IS 'Append-only staging for canonical_asof_scope_split_v2; writes unpublished candidates only and never changes public routing.';

COMMIT;
