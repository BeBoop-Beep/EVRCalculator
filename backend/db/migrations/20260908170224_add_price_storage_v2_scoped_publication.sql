BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='20s';

CREATE TABLE public.price_storage_v2_scoped_release_gate (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  enabled boolean NOT NULL DEFAULT false
);
INSERT INTO public.price_storage_v2_scoped_release_gate(singleton,enabled) VALUES(true,false);

CREATE TABLE public.pokemon_member_set_value_daily_history_v2 (
  set_id uuid NOT NULL,
  root_set_id uuid NOT NULL,
  snapshot_date date NOT NULL,
  value_scope text NOT NULL CHECK(value_scope IN ('standard','hits','top10')),
  set_value numeric,
  priced_card_count integer NOT NULL CHECK(priced_card_count>=0),
  total_card_count integer NOT NULL CHECK(total_card_count>=priced_card_count),
  coverage_pct numeric CHECK(coverage_pct BETWEEN 0 AND 100),
  fresh_card_count integer NOT NULL CHECK(fresh_card_count BETWEEN 0 AND priced_card_count),
  basket_fingerprint text NOT NULL,
  run_id bigint NOT NULL REFERENCES public.price_storage_v2_scope_stage_runs(id),
  source text NOT NULL CHECK(source='price_storage_v2_member_scope_v1'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(set_id,snapshot_date,value_scope),
  CHECK(value_scope<>'top10' OR total_card_count<=10)
);
CREATE TABLE public.pokemon_root_set_value_daily_history_v2 (
  set_id uuid NOT NULL,
  root_set_id uuid NOT NULL CHECK(root_set_id=set_id),
  snapshot_date date NOT NULL,
  value_scope text NOT NULL CHECK(value_scope IN ('standard','hits','top10')),
  set_value numeric,
  priced_card_count integer NOT NULL CHECK(priced_card_count>=0),
  total_card_count integer NOT NULL CHECK(total_card_count>=priced_card_count),
  coverage_pct numeric CHECK(coverage_pct BETWEEN 0 AND 100),
  fresh_card_count integer NOT NULL CHECK(fresh_card_count BETWEEN 0 AND priced_card_count),
  basket_fingerprint text NOT NULL,
  run_id bigint NOT NULL REFERENCES public.price_storage_v2_scope_stage_runs(id),
  source text NOT NULL CHECK(source='price_storage_v2_root_scope_v1'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(set_id,snapshot_date,value_scope),
  CHECK(value_scope<>'top10' OR total_card_count<=10)
);
ALTER TABLE public.price_storage_v2_scoped_release_gate ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_member_set_value_daily_history_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_root_set_value_daily_history_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.price_storage_v2_scoped_release_gate,
 public.pokemon_member_set_value_daily_history_v2,
 public.pokemon_root_set_value_daily_history_v2 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.price_storage_v2_scoped_release_gate TO service_role;
GRANT SELECT,INSERT ON public.pokemon_member_set_value_daily_history_v2,
 public.pokemon_root_set_value_daily_history_v2 TO service_role;

CREATE FUNCTION public.write_price_storage_v2_scoped_run(
 p_run_id bigint,p_root_set_id uuid,p_market_date date,p_universe_scope text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path='' SET "TimeZone"='America/Phoenix'
AS $function$
DECLARE
 v_run public.price_storage_v2_scope_stage_runs%rowtype;
 v_preview jsonb; v_candidates jsonb; v_table text; v_source text;
 v_expected integer; v_inserted integer; v_count integer; v_different integer;
BEGIN
 IF p_universe_scope IS NULL OR p_universe_scope NOT IN ('member','root')
    OR p_run_id IS NULL OR p_root_set_id IS NULL OR p_market_date IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Explicit run, root, date and member/root universe required';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.price_storage_v2_scoped_release_gate WHERE singleton AND enabled) THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Scoped publication is disabled pending integration acceptance';
 END IF;
 SELECT * INTO v_run FROM public.price_storage_v2_scope_stage_runs WHERE id=p_run_id;
 IF NOT FOUND OR v_run.root_set_id IS DISTINCT FROM p_root_set_id
    OR v_run.market_date IS DISTINCT FROM p_market_date OR v_run.status<>'parity_passed'
    OR v_run.definition_version IS DISTINCT FROM 'canonical_asof_scope_split_v2' THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Staged run/root/date is absent, not accepted, or not date-safe v2 evidence';
 END IF;
 v_preview:=public.preview_price_storage_v2_scoped_values_v2(p_root_set_id,p_market_date);
 IF v_preview->>'status' IS DISTINCT FROM 'parity_passed'
    OR md5(v_preview::text) IS DISTINCT FROM v_run.evidence_signature THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Staged acceptance is stale; restage against current source evidence';
 END IF;
 SELECT jsonb_agg(to_jsonb(c)-'run_id' ORDER BY c.universe_scope,c.set_id,c.value_scope)
 INTO v_candidates FROM public.price_storage_v2_scoped_value_candidates c WHERE c.run_id=p_run_id;
 IF v_candidates IS DISTINCT FROM v_preview->'candidate_values' THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Stored candidates differ from the independently recomputed basket';
 END IF;
 SELECT count(*) INTO v_expected FROM public.price_storage_v2_scoped_value_candidates
 WHERE run_id=p_run_id AND universe_scope=p_universe_scope AND market_scope='standard';
 IF v_expected=0 OR v_expected % 3<>0 THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Standard/Hits/Top10 candidate scopes are incomplete';
 END IF;
 v_table:=CASE p_universe_scope WHEN 'member' THEN 'pokemon_member_set_value_daily_history_v2'
                              ELSE 'pokemon_root_set_value_daily_history_v2' END;
 v_source:=CASE p_universe_scope WHEN 'member' THEN 'price_storage_v2_member_scope_v1'
                               ELSE 'price_storage_v2_root_scope_v1' END;
 EXECUTE format($sql$
  INSERT INTO public.%I(set_id,root_set_id,snapshot_date,value_scope,set_value,
   priced_card_count,total_card_count,coverage_pct,fresh_card_count,basket_fingerprint,run_id,source)
  SELECT c.set_id,$2,$3,c.value_scope,c.set_value,c.priced_card_count,c.expected_card_count,
   c.coverage_pct,c.fresh_card_count,c.basket_fingerprint,c.run_id,$5
  FROM public.price_storage_v2_scoped_value_candidates c
  WHERE c.run_id=$1 AND c.universe_scope=$4 AND c.market_scope='standard'
  ON CONFLICT(set_id,snapshot_date,value_scope) DO NOTHING
 $sql$,v_table) USING p_run_id,p_root_set_id,p_market_date,p_universe_scope,v_source;
 GET DIAGNOSTICS v_inserted=ROW_COUNT;
 EXECUTE format($sql$
  SELECT count(h.set_id),count(*) FILTER(WHERE
   ROW(h.root_set_id,h.set_value,h.priced_card_count,h.total_card_count,h.coverage_pct,
       h.fresh_card_count,h.basket_fingerprint,h.run_id,h.source)
   IS DISTINCT FROM
   ROW($2,c.set_value,c.priced_card_count,c.expected_card_count,c.coverage_pct,
       c.fresh_card_count,c.basket_fingerprint,$1,$5))
  FROM public.price_storage_v2_scoped_value_candidates c
  LEFT JOIN public.%I h ON h.set_id=c.set_id AND h.snapshot_date=$3 AND h.value_scope=c.value_scope
  WHERE c.run_id=$1 AND c.universe_scope=$4 AND c.market_scope='standard'
 $sql$,v_table) INTO v_count,v_different
 USING p_run_id,p_root_set_id,p_market_date,p_universe_scope,v_source;
 IF v_count<>v_expected OR v_different<>0 THEN
  RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Conflicting scoped publication requires an explicit correction/version policy';
 END IF;
 RETURN jsonb_build_object('status',CASE WHEN v_inserted=0 THEN 'noop' ELSE 'complete' END,
  'universe_scope',p_universe_scope,'rows_inserted',v_inserted,'rows_verified',v_count,
  'run_id',p_run_id,'public_routing_changed',false);
END;
$function$;

CREATE FUNCTION public.publish_price_storage_v2_member_run(
 p_run_id bigint,p_root_set_id uuid,p_market_date date
) RETURNS jsonb LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=''
AS $function$
 SELECT public.write_price_storage_v2_scoped_run(p_run_id,p_root_set_id,p_market_date,'member');
$function$;
CREATE FUNCTION public.publish_price_storage_v2_root_run(
 p_run_id bigint,p_root_set_id uuid,p_market_date date
) RETURNS jsonb LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=''
AS $function$
 SELECT public.write_price_storage_v2_scoped_run(p_run_id,p_root_set_id,p_market_date,'root');
$function$;
REVOKE ALL ON FUNCTION public.write_price_storage_v2_scoped_run(bigint,uuid,date,text),
 public.publish_price_storage_v2_member_run(bigint,uuid,date),
 public.publish_price_storage_v2_root_run(bigint,uuid,date) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.write_price_storage_v2_scoped_run(bigint,uuid,date,text),
 public.publish_price_storage_v2_member_run(bigint,uuid,date),
 public.publish_price_storage_v2_root_run(bigint,uuid,date) TO service_role;
COMMIT;