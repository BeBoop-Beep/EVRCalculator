-- REVIEW-ONLY PROPOSAL: not installed and deliberately NOT scheduled.
-- Requires price_storage_v2_scope_stage_v2.sql and price_storage_v2_scoped_publication.sql.
-- This coordinator is atomic per invocation: if any requested root blocks, all stage/publish
-- writes in this invocation roll back. The existing release gate must be explicitly enabled.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';

CREATE FUNCTION public.run_price_storage_v2_scoped_publication_cycle(
  p_market_date date,
  p_root_set_ids uuid[]
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
  v_stage jsonb;
  v_item jsonb;
  v_member jsonb;
  v_root jsonb;
  v_results jsonb := '[]'::jsonb;
  v_root_ids uuid[];
BEGIN
  IF p_market_date IS NULL OR p_root_set_ids IS NULL
     OR cardinality(p_root_set_ids) NOT BETWEEN 1 AND 10
     OR array_position(p_root_set_ids,NULL::uuid) IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='22023',
      MESSAGE='Explicit market date and one to ten non-null root set IDs are required';
  END IF;

  SELECT array_agg(DISTINCT x ORDER BY x) INTO v_root_ids FROM unnest(p_root_set_ids) x;
  IF cardinality(v_root_ids) IS DISTINCT FROM cardinality(p_root_set_ids) THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Duplicate root set IDs are not allowed';
  END IF;

  -- Fail closed BEFORE stage writes. service_role cannot enable this table itself.
  IF NOT EXISTS(
    SELECT 1 FROM public.price_storage_v2_scoped_release_gate
    WHERE singleton AND enabled
  ) THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE='Scoped publication cycle is disabled pending live acceptance';
  END IF;

  v_stage := public.stage_price_storage_v2_scoped_values_v2(v_root_ids,p_market_date);

  IF EXISTS(
    SELECT 1
    FROM jsonb_array_elements(coalesce(v_stage->'results','[]'::jsonb)) r(value)
    WHERE r.value->>'status' IS DISTINCT FROM 'parity_passed'
       OR r.value->>'run_id' IS NULL
  ) THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE='One or more scoped roots failed staging; no scoped publication committed',
      DETAIL=v_stage::text;
  END IF;

  FOR v_item IN
    SELECT value
    FROM jsonb_array_elements(v_stage->'results') r(value)
    ORDER BY value->>'root_set_id'
  LOOP
    v_member := public.publish_price_storage_v2_member_run(
      (v_item->>'run_id')::bigint,
      (v_item->>'root_set_id')::uuid,
      p_market_date
    );
    v_root := public.publish_price_storage_v2_root_run(
      (v_item->>'run_id')::bigint,
      (v_item->>'root_set_id')::uuid,
      p_market_date
    );

    IF coalesce(v_member->>'status','') NOT IN ('complete','noop')
       OR coalesce(v_root->>'status','') NOT IN ('complete','noop') THEN
      RAISE EXCEPTION USING ERRCODE='55000',
        MESSAGE='Scoped publisher returned a non-complete status';
    END IF;

    v_results := v_results || jsonb_build_array(jsonb_build_object(
      'root_set_id',v_item->>'root_set_id',
      'run_id',(v_item->>'run_id')::bigint,
      'member_status',v_member->>'status',
      'root_status',v_root->>'status'
    ));
  END LOOP;

  RETURN jsonb_build_object(
    'status','complete',
    'market_date',p_market_date,
    'definition_version','canonical_asof_scope_split_v2',
    'root_count',cardinality(v_root_ids),
    'results',v_results,
    'public_routing_changed',false,
    'scheduler_attached',false
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.run_price_storage_v2_scoped_publication_cycle(date,uuid[])
FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.run_price_storage_v2_scoped_publication_cycle(date,uuid[])
TO service_role;

COMMENT ON FUNCTION public.run_price_storage_v2_scoped_publication_cycle(date,uuid[])
IS 'Review-only scoped coordinator using date-safe v2 staging. Requires explicit enabled release gate; no cron attachment. Atomic invocation stages and publishes independent member/root destinations or rolls back.';

COMMIT;
