BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';

CREATE OR REPLACE FUNCTION public.preview_price_storage_v2_scoped_values_v2(
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
  v_members uuid[];
  v_context jsonb;
  v_data jsonb;
  v_root_name text;
  v_bad_sources integer;
  v_reason text;
  v_raw_hash text;
  v_v2_hash text;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='root set and market date are required';
  END IF;

  IF NOT EXISTS(
    SELECT 1
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon'
      AND q.market_date=p_market_date
      AND q.status IN ('READY','LEGACY_VERIFIED')
  ) THEN
    RAISE EXCEPTION USING ERRCODE='22023',
      MESSAGE='Scope staging requires an explicitly approved market date';
  END IF;

  SELECT s.name INTO v_root_name
  FROM public.sets s
  WHERE s.id=p_root_set_id
    AND s.parent_opening_set_id IS NULL
    AND s.catalog_only=false;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE='22023',
      MESSAGE='A non-catalog root set is required; a subset cannot be treated as its own parent';
  END IF;

  SELECT array_agg(s.id ORDER BY s.id) INTO v_members
  FROM public.sets s
  WHERE s.id=p_root_set_id
     OR (s.parent_opening_set_id=p_root_set_id AND s.counts_toward_parent_set_value=true);

  v_raw_hash:=md5(pg_get_functiondef(
    'public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(uuid,date)'::regprocedure
  ));
  v_v2_hash:=md5(pg_get_functiondef(
    'public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(uuid,date)'::regprocedure
  ));

  WITH source_members AS (
    SELECT s.id AS set_id,s.name,j.id AS job_id,j.status AS job_status,
           j.completed_at AS source_completed_at,
           q.id AS shadow_job_id,q.status AS shadow_status,
           q.source_completed_at AS shadow_source_completed_at,
           q.completed_at AS shadow_completed_at,
           coalesce(
             j.status='completed'
             AND j.completed_at IS NOT NULL
             AND q.status='complete'
             AND q.source_completed_at=j.completed_at
             AND q.completed_at>=j.completed_at,
             false
           ) AS source_ready
    FROM public.sets s
    LEFT JOIN LATERAL(
      SELECT j.*
      FROM public.scrape_jobs j
      WHERE j.set_id=s.id AND j.market_date=p_market_date
      ORDER BY j.created_at DESC,j.id DESC
      LIMIT 1
    ) j ON true
    LEFT JOIN public.price_storage_v2_shadow_queue q
      ON q.set_id=s.id AND q.market_date=p_market_date
    WHERE s.id=ANY(v_members)
  )
  SELECT jsonb_build_object(
           'root_set_id',p_root_set_id,
           'root_name',v_root_name,
           'market_date',p_market_date,
           'member_set_ids',to_jsonb(v_members),
           'definition_version','canonical_asof_scope_split_v2',
           'raw_definition_hash',v_raw_hash,
           'v2_definition_hash',v_v2_hash,
           'source_evidence',jsonb_agg(to_jsonb(m) ORDER BY m.set_id)
         ),
         count(*) FILTER(WHERE NOT m.source_ready)::integer
  INTO v_context,v_bad_sources
  FROM source_members m;

  IF EXISTS(
    SELECT 1
    FROM public.pokemon_edition_split_root_sets_v2 e
    WHERE e.set_id=ANY(v_members)
  ) THEN
    v_reason:='edition_scope_requires_separate_acceptance';
  ELSIF v_raw_hash<>'f7b3b05bb7c492dddc4a26abd5cb4fb7'
     OR v_v2_hash<>'93d1ad2c21373db0662ad984ecdfee98' THEN
    v_reason:='pricing_definition_changed';
  ELSIF v_bad_sources>0 THEN
    v_reason:='source_or_shadow_not_complete';
  END IF;

  IF v_reason IS NOT NULL THEN
    RETURN jsonb_build_object(
      'status','blocked',
      'reason',v_reason,
      'context',v_context,
      'comparison','{}'::jsonb,
      'publication_authorized',false,
      'candidate_values','[]'::jsonb
    );
  END IF;

  WITH checklist AS MATERIALIZED (
    SELECT c.id AS canonical_card_id,c.set_id AS member_set_id,c.canonical_review_status,
           EXISTS(
             SELECT 1
             FROM public.pokemon_card_desirability_links l
             WHERE l.pokemon_canonical_card_id=c.id AND l.is_hit_eligible=true
           ) AS is_hit
    FROM public.pokemon_canonical_cards c
    WHERE c.set_id=ANY(v_members) AND c.set_value_eligible=true
  ),
  raw_prices AS MATERIALIZED (
    SELECT r.*
    FROM unnest(v_members) m(id)
    CROSS JOIN LATERAL
      public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(m.id,p_market_date) r
  ),
  v2_prices AS MATERIALIZED (
    SELECT r.*
    FROM unnest(v_members) m(id)
    CROSS JOIN LATERAL
      public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(m.id,p_market_date) r
  ),
  raw_only AS (
    SELECT * FROM raw_prices
    EXCEPT ALL
    SELECT * FROM v2_prices
  ),
  v2_only AS (
    SELECT * FROM v2_prices
    EXCEPT ALL
    SELECT * FROM raw_prices
  ),
  joined AS MATERIALIZED (
    SELECT c.*,v.card_variant_id,v.market_price,v.captured_at,v.source
    FROM checklist c
    LEFT JOIN v2_prices v
      ON v.canonical_card_id=c.canonical_card_id
     AND v.set_id=c.member_set_id
  ),
  live_root AS MATERIALIZED (
    SELECT r.canonical_card_id,r.member_set_id,r.card_variant_id,
           r.market_price,r.captured_at
    FROM public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) r
    WHERE r.market_scope='standard'
  ),
  proposed_identity AS MATERIALIZED (
    SELECT canonical_card_id,member_set_id
    FROM checklist
  ),
  live_identity AS MATERIALIZED (
    SELECT canonical_card_id,member_set_id
    FROM live_root
  ),
  proposed_root AS MATERIALIZED (
    SELECT canonical_card_id,member_set_id,card_variant_id,market_price,captured_at
    FROM joined
  ),
  live_identity_only AS (
    SELECT * FROM live_identity
    EXCEPT ALL
    SELECT * FROM proposed_identity
  ),
  proposed_identity_only AS (
    SELECT * FROM proposed_identity
    EXCEPT ALL
    SELECT * FROM live_identity
  ),
  live_economic_only AS (
    SELECT * FROM live_root
    EXCEPT ALL
    SELECT * FROM proposed_root
  ),
  proposed_economic_only AS (
    SELECT * FROM proposed_root
    EXCEPT ALL
    SELECT * FROM live_root
  ),
  expanded AS MATERIALIZED (
    SELECT 'member'::text AS universe_scope,j.member_set_id AS value_set_id,j.*
    FROM joined j
    UNION ALL
    SELECT 'root'::text,p_root_set_id,j.*
    FROM joined j
  ),
  ranked AS MATERIALIZED (
    SELECT e.*,
           row_number() OVER(
             PARTITION BY e.universe_scope,e.value_set_id
             ORDER BY e.market_price DESC NULLS LAST,e.canonical_card_id
           ) AS price_rank
    FROM expanded e
  ),
  scoped AS MATERIALIZED (
    SELECT r.*,sc.value_scope
    FROM ranked r
    CROSS JOIN (VALUES('standard'::text),('hits'),('top10')) sc(value_scope)
    WHERE sc.value_scope='standard'
       OR (sc.value_scope='hits' AND r.is_hit)
       OR (sc.value_scope='top10' AND r.price_rank<=10)
  ),
  groups AS (
    SELECT 'member'::text AS universe_scope,m.id AS value_set_id
    FROM unnest(v_members)m(id)
    UNION ALL
    SELECT 'root',p_root_set_id
  ),
  grid AS (
    SELECT g.*,s.value_scope
    FROM groups g
    CROSS JOIN (VALUES('standard'::text),('hits'),('top10')) s(value_scope)
  ),
  values_out AS MATERIALIZED (
    SELECT g.universe_scope,g.value_set_id AS set_id,
           'standard'::text AS market_scope,g.value_scope,
           round(sum(s.market_price),2) AS set_value,
           count(s.canonical_card_id)::integer AS expected_card_count,
           count(s.market_price)::integer AS priced_card_count,
           count(*) FILTER(
             WHERE s.market_price IS NOT NULL AND s.member_set_id<>p_root_set_id
           )::integer AS subset_priced_card_count,
           count(*) FILTER(
             WHERE s.market_price IS NOT NULL AND s.captured_at=p_market_date
           )::integer AS fresh_card_count,
           round(
             100*count(s.market_price)::numeric/nullif(count(s.canonical_card_id),0),2
           ) AS coverage_pct,
           min(s.captured_at) AS oldest_observed_date,
           max(s.captured_at) AS newest_observed_date,
           md5(coalesce(string_agg(
             jsonb_build_array(
               s.canonical_card_id,s.member_set_id,s.card_variant_id,
               s.market_price,s.captured_at,s.source
             )::text,
             '|' ORDER BY s.market_price DESC,s.canonical_card_id
           ) FILTER(WHERE s.market_price IS NOT NULL),'')) AS basket_fingerprint
    FROM grid g
    LEFT JOIN scoped s
      ON s.universe_scope=g.universe_scope
     AND s.value_set_id=g.value_set_id
     AND s.value_scope=g.value_scope
    GROUP BY g.universe_scope,g.value_set_id,g.value_scope
  )
  SELECT jsonb_build_object(
    'expected_cards',(SELECT count(*) FROM checklist),
    'checklist_fingerprint',(
      SELECT md5(coalesce(string_agg(to_jsonb(c)::text,'|' ORDER BY c.canonical_card_id),''))
      FROM checklist c
    ),
    'raw_rows',(SELECT count(*) FROM raw_prices),
    'v2_rows',(SELECT count(*) FROM v2_prices),
    'raw_only_rows',(SELECT count(*) FROM raw_only),
    'v2_only_rows',(SELECT count(*) FROM v2_only),
    'duplicate_raw_keys',(
      SELECT count(*)-count(DISTINCT canonical_card_id) FROM raw_prices
    ),
    'duplicate_v2_keys',(
      SELECT count(*)-count(DISTINCT canonical_card_id) FROM v2_prices
    ),
    'missing_prices',(SELECT count(*) FROM joined WHERE market_price IS NULL),
    'needs_review_cards',(
      SELECT count(*) FROM checklist WHERE canonical_review_status='needs_review'
    ),
    'root_identity_live_only_rows',(SELECT count(*) FROM live_identity_only),
    'root_identity_proposed_only_rows',(SELECT count(*) FROM proposed_identity_only),
    'root_economic_live_only_rows',(SELECT count(*) FROM live_economic_only),
    'root_economic_proposed_only_rows',(SELECT count(*) FROM proposed_economic_only),
    'live_root_max_captured_at',(SELECT max(captured_at) FROM live_root),
    'live_root_future_rows',(
      SELECT count(*)::integer FROM live_root WHERE captured_at>p_market_date
    ),
    'live_root_economic_comparison_applicable',
      coalesce((SELECT max(captured_at) FROM live_root),p_market_date)<=p_market_date,
    'latest_root_storage_provenance_ignored',true,
    'candidate_values',(
      SELECT jsonb_agg(
        to_jsonb(v) ORDER BY v.universe_scope,v.set_id,v.value_scope
      )
      FROM values_out v
    )
  )
  INTO v_data;

  v_reason:=CASE
    WHEN (v_data->>'expected_cards')::integer=0
      THEN 'no_eligible_cards'
    WHEN (v_data->>'duplicate_raw_keys')::integer<>0
      OR (v_data->>'duplicate_v2_keys')::integer<>0
      THEN 'duplicate_price_identity'
    WHEN (v_data->>'raw_only_rows')::integer<>0
      OR (v_data->>'v2_only_rows')::integer<>0
      THEN 'raw_v2_price_contract_mismatch'
    WHEN (v_data->>'missing_prices')::integer<>0
      THEN 'incomplete_price_coverage'
    WHEN (v_data->>'needs_review_cards')::integer<>0
      THEN 'canonical_review_required'
    WHEN (v_data->>'root_identity_live_only_rows')::integer<>0
      OR (v_data->>'root_identity_proposed_only_rows')::integer<>0
      THEN 'live_root_identity_mismatch'
    WHEN (v_data->>'live_root_economic_comparison_applicable')::boolean
      AND (
        (v_data->>'root_economic_live_only_rows')::integer<>0
        OR (v_data->>'root_economic_proposed_only_rows')::integer<>0
      )
      THEN 'live_root_economic_mismatch'
    ELSE 'exact_source_gated_scope_parity_v2'
  END;

  RETURN jsonb_build_object(
    'status',CASE
      WHEN v_reason='exact_source_gated_scope_parity_v2' THEN 'parity_passed'
      ELSE 'blocked'
    END,
    'reason',v_reason,
    'context',v_context,
    'comparison',v_data-'candidate_values',
    'publication_authorized',false,
    'candidate_values',coalesce(v_data->'candidate_values','[]'::jsonb)
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.stage_price_storage_v2_scoped_values_v2(
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
IS 'Date-safe scoped validation for any explicitly approved market date. Recomputes raw/V2/source/coverage evidence as-of that date, validates latest root identity, and compares latest economics only when latest has not advanced beyond the requested date.';
COMMENT ON FUNCTION public.stage_price_storage_v2_scoped_values_v2(uuid[],date)
IS 'Append-only staging for canonical_asof_scope_split_v2; writes unpublished candidates only and never changes public routing.';

COMMIT;