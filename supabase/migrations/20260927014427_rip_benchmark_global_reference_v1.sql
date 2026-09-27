-- Additive publication-level Opening Economics reference. No scoring/model/pointer changes.
-- Reuses the exact snapshot ID, contract and basis already on the benchmark header.
-- One indexed source lookup at INSERT; current/history reads use only frozen typed columns.
set local lock_timeout = '2s';
set local statement_timeout = '20s';

alter table public.pokemon_rip_benchmark_publications_v1
  add column global_financial_reference_status text not null default 'unavailable',
  add column global_financial_reference_reason text default 'not_captured_before_reference_v1',
  add column global_cost_per_pack public.rip_benchmark_finite_v1,
  add column global_expected_value_per_pack public.rip_benchmark_finite_v1,
  add column global_modeled_return_on_spend public.rip_benchmark_finite_v1,
  add column global_mean_outcome_retention public.rip_benchmark_finite_v1,
  add column opening_economics_source_market_date date,
  add column opening_economics_source_fingerprint text,
  add column opening_economics_input_fingerprint text,
  add column opening_economics_global_fingerprint text,
  add constraint rip_benchmark_global_reference_values_v1 check (
    (global_cost_per_pack is null or global_cost_per_pack > 0)
    and (global_expected_value_per_pack is null or global_expected_value_per_pack >= 0)
    and (global_modeled_return_on_spend is null or global_modeled_return_on_spend >= 0)
    and (global_mean_outcome_retention is null or global_mean_outcome_retention >= 0)
    and (opening_economics_source_market_date is null or
      (isfinite(opening_economics_source_market_date) and opening_economics_source_market_date = market_date))
    and (opening_economics_source_fingerprint is null or opening_economics_source_fingerprint ~ '^[0-9a-f]{64}$')
    and (opening_economics_input_fingerprint is null or opening_economics_input_fingerprint ~ '^[0-9a-f]{64}$')
    and (opening_economics_global_fingerprint is null or opening_economics_global_fingerprint ~ '^[0-9a-f]{64}$')
  ),
  add constraint rip_benchmark_global_reference_status_v1 check (
    (global_financial_reference_status = 'available'
      and global_financial_reference_reason is null
      and global_cost_per_pack is not null and global_expected_value_per_pack is not null
      and global_modeled_return_on_spend is not null
      and opening_economics_snapshot_id is not null
      and opening_economics_contract_version is not null and opening_economics_contract_version = 'pokemon-rip-stats-v3'
      and opening_economics_basis is not null and opening_economics_basis = 'all_modeled_products_per_pack_equivalent'
      and opening_economics_source_market_date is not null
      and opening_economics_source_fingerprint is not null and opening_economics_global_fingerprint is not null)
    or (global_financial_reference_status = 'unavailable'
      and coalesce(length(btrim(global_financial_reference_reason)),0) between 1 and 160
      and global_cost_per_pack is null and global_expected_value_per_pack is null
      and global_modeled_return_on_spend is null and global_mean_outcome_retention is null)
  );

create function public.capture_rip_benchmark_global_reference_v1() returns trigger
language plpgsql security invoker set search_path='' as $$
declare src record; economics jsonb; global_scope jsonb; field_name text;
begin
  -- Server-owned, not supplied by the backend. The existing publisher allowlist stays unchanged.
  new.global_financial_reference_status := 'unavailable';
  new.global_financial_reference_reason := 'opening_economics_snapshot_missing';
  new.global_cost_per_pack := null; new.global_expected_value_per_pack := null;
  new.global_modeled_return_on_spend := null; new.global_mean_outcome_retention := null;
  new.opening_economics_source_market_date := null;
  new.opening_economics_source_fingerprint := null;
  new.opening_economics_input_fingerprint := null;
  new.opening_economics_global_fingerprint := null;
  if new.opening_economics_snapshot_id is null then return new; end if;

  select s.market_date,s.publication_status,s.contract_version,s.methodology_version,s.weighting_version,
    s.source_run_fingerprint,s.payload_json->'contractVersion' as payload_contract,
    s.payload_json->'marketDate' as payload_date,s.payload_json->'openingEconomics' as economics
  into strict src from public.pokemon_rip_stats_snapshots s where s.id=new.opening_economics_snapshot_id;
  if src.market_date is distinct from new.market_date or src.publication_status is distinct from 'published'
    or src.contract_version is distinct from 'pokemon-rip-stats-v3'
    or src.methodology_version is distinct from 'hierarchical_product_per_pack_empirical_v1'
    or src.weighting_version is distinct from 'equal-set_equal-family_equal-sku-v1'
    or new.opening_economics_contract_version is distinct from src.contract_version
    or new.opening_economics_basis is distinct from 'all_modeled_products_per_pack_equivalent' then
    raise exception 'incompatible or differently dated Opening Economics reference';
  end if;
  new.opening_economics_source_market_date := src.market_date;
  if src.source_run_fingerprint is null then
    new.global_financial_reference_reason := 'opening_economics_source_fingerprint_missing'; return new;
  end if;
  if src.source_run_fingerprint !~ '^[0-9a-f]{64}$' then raise exception 'invalid Opening Economics source fingerprint'; end if;
  new.opening_economics_source_fingerprint := src.source_run_fingerprint;
  economics := src.economics;
  if economics is null or economics='null'::jsonb then
    new.global_financial_reference_reason := 'opening_economics_scope_missing'; return new;
  end if;
  if jsonb_typeof(economics) is distinct from 'object'
    or src.payload_contract is distinct from to_jsonb('pokemon-rip-stats-v3'::text)
    or src.payload_date is distinct from to_jsonb(new.market_date::text)
    or economics->>'contractVersion' is distinct from 'pokemon-rip-stats-v3'
    or economics->>'basis' is distinct from 'all_modeled_products_per_pack_equivalent'
    or economics->>'marketDate' is distinct from new.market_date::text
    or economics#>>'{methodology,version}' is distinct from 'hierarchical_product_per_pack_empirical_v1'
    or economics#>>'{methodology,weightingVersion}' is distinct from 'equal-set_equal-family_equal-sku-v1' then
    raise exception 'incompatible V3 global reference payload';
  end if;
  if economics->>'status' is distinct from 'available' then
    new.global_financial_reference_reason := 'opening_economics_unavailable'; return new;
  end if;
  new.opening_economics_input_fingerprint := economics->>'inputFingerprint';
  if new.opening_economics_input_fingerprint is not null
    and new.opening_economics_input_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid Opening Economics input fingerprint';
  end if;
  global_scope := economics->'global';
  if global_scope is null or global_scope='null'::jsonb then
    new.global_financial_reference_reason := 'opening_economics_global_scope_missing'; return new;
  end if;
  if jsonb_typeof(global_scope) is distinct from 'object'
    or global_scope->>'methodologyVersion' is distinct from 'hierarchical_product_per_pack_empirical_v1'
    or global_scope->>'weightingVersion' is distinct from 'equal-set_equal-family_equal-sku-v1' then
    raise exception 'incompatible V3 global reference scope';
  end if;
  if global_scope->>'coverageStatus' is distinct from 'complete' then
    new.global_financial_reference_reason := 'opening_economics_global_coverage_incomplete'; return new;
  end if;
  foreach field_name in array array['averageCostPerPack','averageModelBreakEvenPerPack','modeledReturnOnSpend'] loop
    if global_scope->field_name is null or global_scope->field_name='null'::jsonb then
      new.global_financial_reference_reason := 'opening_economics_global_values_missing'; return new;
    end if;
    if jsonb_typeof(global_scope->field_name) is distinct from 'number' then
      raise exception 'invalid numeric global reference field: %',field_name;
    end if;
  end loop;
  if global_scope->'meanOutcomeRetention' is not null and global_scope->'meanOutcomeRetention'<>'null'::jsonb
    and jsonb_typeof(global_scope->'meanOutcomeRetention') is distinct from 'number' then
    raise exception 'invalid numeric global reference field: meanOutcomeRetention';
  end if;
  -- Copy each published global statistic verbatim. No averaging, recomputation or replacement.
  new.global_cost_per_pack := (global_scope->>'averageCostPerPack')::numeric;
  new.global_expected_value_per_pack := (global_scope->>'averageModelBreakEvenPerPack')::numeric;
  new.global_modeled_return_on_spend := (global_scope->>'modeledReturnOnSpend')::numeric;
  new.global_mean_outcome_retention := (global_scope->>'meanOutcomeRetention')::numeric;
  new.opening_economics_global_fingerprint := encode(sha256(convert_to(jsonb_build_object(
    'snapshot_id',new.opening_economics_snapshot_id,'market_date',src.market_date,
    'contract_version',src.contract_version,'basis',new.opening_economics_basis,
    'source_fingerprint',src.source_run_fingerprint,'input_fingerprint',new.opening_economics_input_fingerprint,
    'global',global_scope)::text,'UTF8')),'hex');
  new.global_financial_reference_status := 'available'; new.global_financial_reference_reason := null;
  return new;
end $$;
create trigger rip_benchmark_global_reference_capture_v1
  before insert on public.pokemon_rip_benchmark_publications_v1
  for each row execute function public.capture_rip_benchmark_global_reference_v1();

-- Existing immutable-header guard covers these added fields automatically, including superseded revisions.
-- The helper performs no queries and returns only the narrow typed reference, never a source artifact.
create function public.project_rip_benchmark_global_reference_v1(p public.pokemon_rip_benchmark_publications_v1)
returns jsonb language sql immutable security invoker set search_path='' as $$
  select jsonb_build_object('contract_version','rip-benchmark-global-reference-v1',
    'scope','pokemon','publication_id',p.id,'market_date',p.market_date,
    'status',p.global_financial_reference_status,'reason',p.global_financial_reference_reason,
    'snapshot_id',p.opening_economics_snapshot_id,'source_contract_version',p.opening_economics_contract_version,
    'basis',p.opening_economics_basis,'source_market_date',p.opening_economics_source_market_date,
    'source_fingerprint',p.opening_economics_source_fingerprint,'input_fingerprint',p.opening_economics_input_fingerprint,
    'global_fingerprint',p.opening_economics_global_fingerprint,
    'cost_per_pack',p.global_cost_per_pack,'expected_value_per_pack',p.global_expected_value_per_pack,
    'modeled_return_on_spend',p.global_modeled_return_on_spend,'mean_outcome_retention',p.global_mean_outcome_retention);
$$;

create or replace function public.get_pokemon_rip_benchmark_history_v1(
  p_entities jsonb,p_start_date date,p_end_date date,p_benchmark_key text,p_calibration_version text,
  p_limit integer default 500,p_after jsonb default null)
returns jsonb language plpgsql stable security invoker set search_path='' set statement_timeout='5s' as $$
declare result jsonb; pubsig text; querysig text; ad date; atype text; aid uuid; am text;
begin
  perform public.assert_rip_benchmark_entities_v1(p_entities);
  if p_start_date is null or p_end_date is null or not isfinite(p_start_date) or not isfinite(p_end_date)
    or p_end_date<p_start_date or p_end_date-p_start_date>365 then raise exception 'history window must be 1..366 inclusive days'; end if;
  if p_limit is null or p_limit not between 1 and 1000 or coalesce(length(p_benchmark_key),0) not between 1 and 100
    or coalesce(length(p_calibration_version),0) not between 1 and 160 then raise exception 'invalid read bounds or version'; end if;
  select md5(coalesce(string_agg(id::text,',' order by market_date),'')) into pubsig from public.pokemon_rip_benchmark_publications_v1
    where benchmark_key=p_benchmark_key and calibration_version=p_calibration_version and market_date between p_start_date and p_end_date and publication_status='published';
  select md5(jsonb_build_array(p_start_date,p_end_date,p_benchmark_key,p_calibration_version,
    (select jsonb_agg(to_jsonb(e) order by e.entity_type,e.entity_id) from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid)))::text) into querysig;
  if p_after is not null then
    if jsonb_typeof(p_after) is distinct from 'object' or octet_length(p_after::text)>1024 then raise exception 'invalid cursor'; end if;
    if (p_after->>'publication_signature') is distinct from pubsig then raise exception 'history publications changed; restart pagination'; end if;
    if (p_after->>'query_signature') is distinct from querysig then raise exception 'cursor belongs to another query'; end if;
    ad:=(p_after->>'market_date')::date; atype:=p_after->>'entity_type'; aid:=(p_after->>'entity_id')::uuid; am:=p_after->>'metric_key';
    if ad is null or ad not between p_start_date and p_end_date or aid is null or atype is null or atype not in ('set','era','sealed_product')
      or am is null or am not in ('financial','chase','collector','overall') then raise exception 'invalid cursor key'; end if;
  end if;
  with matches as materialized (
    select r.* from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid)
    cross join lateral (
      select r.* from public.pokemon_rip_benchmark_rows_v1 r join public.pokemon_rip_benchmark_publications_v1 p on p.id=r.publication_id
      where r.entity_type=e.entity_type and r.entity_id=e.entity_id and r.market_date between p_start_date and p_end_date
        and p.publication_status='published' and p.benchmark_key=p_benchmark_key and p.calibration_version=p_calibration_version
        and (p_after is null or (r.market_date,r.entity_type,r.entity_id,r.metric_key)>(ad,atype,aid,am))
      order by r.market_date,r.entity_type,r.entity_id,r.metric_key limit p_limit+1
    ) r order by r.market_date,r.entity_type,r.entity_id,r.metric_key limit p_limit+1
  ), page as materialized (select * from matches order by market_date,entity_type,entity_id,metric_key limit p_limit),
  refs as materialized (
    select p.id,public.project_rip_benchmark_global_reference_v1(p) as reference
    from public.pokemon_rip_benchmark_publications_v1 p join (select distinct publication_id from page) x on x.publication_id=p.id
  )
  select jsonb_build_object('contract_version','rip-benchmark-read-v1','benchmark_key',p_benchmark_key,'calibration_version',p_calibration_version,
    'start_date',p_start_date,'end_date',p_end_date,'rows',coalesce((select jsonb_agg(
      (to_jsonb(x)-'source_lineage')||jsonb_build_object('opening_economics_reference',refs.reference)
      order by x.market_date,x.entity_type,x.entity_id,x.metric_key) from page x join refs on refs.id=x.publication_id),'[]'::jsonb),
    'has_more',(select count(*)>p_limit from matches),'next_cursor',case when (select count(*)>p_limit from matches) then
      (select jsonb_build_object('market_date',market_date,'entity_type',entity_type,'entity_id',entity_id,'metric_key',metric_key,
        'publication_signature',pubsig,'query_signature',querysig) from page order by market_date desc,entity_type desc,entity_id desc,metric_key desc limit 1) else null end)
  into result;
  return result;
end $$;

create or replace function public.get_pokemon_rip_benchmark_current_v1(p_entities jsonb,p_benchmark_key text,p_calibration_version text)
returns jsonb language plpgsql stable security invoker set search_path='' set statement_timeout='5s' as $$
declare h public.pokemon_rip_benchmark_publications_v1%rowtype; result jsonb; reference jsonb;
begin
  perform public.assert_rip_benchmark_entities_v1(p_entities);
  if coalesce(length(p_benchmark_key),0) not between 1 and 100 or coalesce(length(p_calibration_version),0) not between 1 and 160 then raise exception 'explicit benchmark/version required'; end if;
  select * into h from public.pokemon_rip_benchmark_publications_v1 where benchmark_key=p_benchmark_key and calibration_version=p_calibration_version
    and publication_status='published' order by market_date desc limit 1;
  if not found then return jsonb_build_object('contract_version','rip-benchmark-read-v1','status','unavailable','reason','no_published_benchmark','rows','[]'::jsonb,'opening_economics_reference',null); end if;
  reference := public.project_rip_benchmark_global_reference_v1(h);
  select jsonb_build_object('contract_version','rip-benchmark-read-v1','status','available','publication_id',h.id,'market_date',h.market_date,
    'benchmark_key',h.benchmark_key,'calibration_version',h.calibration_version,'source_fingerprint',h.source_fingerprint,'cohort_fingerprint',h.cohort_fingerprint,
    'active_overall_publication_id',h.active_overall_publication_id,'active_overall_market_date',h.active_overall_market_date,
    'overall_model_version',h.overall_model_version,'financial_model_version',h.financial_model_version,'chase_model_version',h.chase_model_version,
    'collector_model_version',h.collector_model_version,'collector_run_id',h.collector_run_id,'published_at',h.published_at,
    'opening_economics_reference',reference,
    'rows',coalesce(jsonb_agg((to_jsonb(r)-'source_lineage')||jsonb_build_object('opening_economics_reference',reference)
      order by r.entity_type,r.entity_id,r.metric_key),'[]'::jsonb)) into result
  from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid) join public.pokemon_rip_benchmark_rows_v1 r
    on r.publication_id=h.id and r.entity_type=e.entity_type and r.entity_id=e.entity_id;
  return result;
end $$;

revoke all on function public.capture_rip_benchmark_global_reference_v1(),
  public.project_rip_benchmark_global_reference_v1(public.pokemon_rip_benchmark_publications_v1),
  public.get_pokemon_rip_benchmark_history_v1(jsonb,date,date,text,text,integer,jsonb),
  public.get_pokemon_rip_benchmark_current_v1(jsonb,text,text) from public,anon,authenticated;
grant execute on function public.project_rip_benchmark_global_reference_v1(public.pokemon_rip_benchmark_publications_v1),
  public.get_pokemon_rip_benchmark_history_v1(jsonb,date,date,text,text,integer,jsonb),
  public.get_pokemon_rip_benchmark_current_v1(jsonb,text,text) to service_role;
comment on column public.pokemon_rip_benchmark_publications_v1.global_modeled_return_on_spend is
  'Exact same-date openingEconomics.global.modeledReturnOnSpend; not a mean of set percentages, median, or model-score benchmark.';
comment on function public.capture_rip_benchmark_global_reference_v1() is
  'INSERT-only source capture by exact snapshot primary key. No latest fallback, source mutation, model calculation, or request-time source JSON.';
comment on function public.project_rip_benchmark_global_reference_v1(public.pokemon_rip_benchmark_publications_v1) is
  'Narrow frozen publication-level global economics. Existing rows are unavailable until explicitly rebuilt as new publication revisions.';
