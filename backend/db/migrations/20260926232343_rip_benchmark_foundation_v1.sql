-- RIP Benchmarking V1: additive private storage. No model/scoring transform or serving-pointer writes.
-- Backend proves source compatibility and owns the versioned calibration. NULL is never imputed to zero.
set local lock_timeout = '2s';
set local statement_timeout = '20s';

create domain public.rip_benchmark_finite_v1 as numeric
  check (value > '-Infinity'::numeric and value < 'Infinity'::numeric);

create table public.pokemon_rip_benchmark_publications_v1 (
  id uuid primary key,
  market_date date not null check (isfinite(market_date)),
  benchmark_key text not null check (length(benchmark_key) between 1 and 100),
  calibration_version text not null check (length(calibration_version) between 1 and 160),
  publication_status text not null default 'staged' check (publication_status in ('staged','published','superseded')),
  expected_entity_count integer not null check (expected_entity_count between 1 and 1250),
  expected_row_count integer not null check (expected_row_count = expected_entity_count * 4),
  cohort_fingerprint text not null check (cohort_fingerprint ~ '^[0-9a-f]{64}$'),
  source_fingerprint text not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
  request_fingerprint text not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  overall_model_version text not null check (length(overall_model_version) between 1 and 240),
  financial_model_version text not null check (length(financial_model_version) between 1 and 240),
  chase_model_version text not null check (length(chase_model_version) between 1 and 240),
  collector_model_version text not null check (length(collector_model_version) between 1 and 240),
  collector_run_id uuid,
  collector_lineage_status text not null check (collector_lineage_status in ('exact_run','embedded_source','unavailable')),
  active_overall_publication_id uuid not null,
  active_overall_market_date date not null,
  active_overall_model_version text not null,
  active_rankings_generation_id uuid not null,
  active_set_page_generation_id uuid not null,
  active_release_lineage jsonb not null check (jsonb_typeof(active_release_lineage)='object' and octet_length(active_release_lineage::text)<=16384),
  opening_economics_snapshot_id uuid,
  opening_economics_contract_version text,
  opening_economics_basis text,
  source_manifest jsonb not null check (jsonb_typeof(source_manifest)='object' and octet_length(source_manifest::text)<=65536),
  previous_publication_id uuid references public.pokemon_rip_benchmark_publications_v1(id),
  created_at timestamptz not null default clock_timestamp(),
  published_at timestamptz,
  superseded_at timestamptz,
  unique(id,market_date),
  check (collector_lineage_status<>'exact_run' or collector_run_id is not null),
  check ((publication_status='staged' and published_at is null and superseded_at is null)
      or (publication_status='published' and published_at is not null and superseded_at is null)
      or (publication_status='superseded' and published_at is not null and superseded_at is not null))
);
create unique index rip_benchmark_pub_daily_v1 on public.pokemon_rip_benchmark_publications_v1
  (benchmark_key,calibration_version,market_date desc) where publication_status='published';
create index rip_benchmark_pub_previous_v1 on public.pokemon_rip_benchmark_publications_v1(previous_publication_id)
  where previous_publication_id is not null;

create table public.pokemon_rip_benchmark_rows_v1 (
  publication_id uuid not null,
  market_date date not null,
  entity_type text not null check (entity_type in ('set','era','sealed_product')),
  entity_id uuid not null,
  metric_key text not null check (metric_key in ('financial','chase','collector','overall')),
  parent_set_id uuid,
  model_status text not null check (model_status in ('available','inherited','unavailable')),
  model_reason text check (length(model_reason)<=500),
  benchmark_status text not null check (benchmark_status in ('available','unavailable')),
  benchmark_reason text check (length(benchmark_reason)<=500),
  raw_model_value public.rip_benchmark_finite_v1,
  benchmark_raw_value public.rip_benchmark_finite_v1,
  benchmark_score public.rip_benchmark_finite_v1 check (benchmark_score between 0 and 10),
  raw_delta numeric generated always as (raw_model_value-benchmark_raw_value) stored,
  score_delta numeric generated always as (benchmark_score-5) stored,
  rank integer,
  cohort_size integer,
  source_model_version text check (length(source_model_version) between 1 and 240),
  source_market_date date check (isfinite(source_market_date)),
  source_entity_type text check (source_entity_type in ('set','era','sealed_product')),
  source_entity_id uuid,
  source_publication_id uuid,
  calculation_run_id uuid,
  source_result_id uuid,
  collector_run_id uuid,
  source_fingerprint text not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
  benchmark_source_fingerprint text check (benchmark_source_fingerprint ~ '^[0-9a-f]{64}$'),
  reconstruction_status text not null check (reconstruction_status in ('persisted_exact','reconstructed_compatible','inherited_parent_set','unavailable')),
  source_lineage jsonb not null check (jsonb_typeof(source_lineage)='object' and octet_length(source_lineage::text)<=8192),
  financial_evidence_status text not null check (financial_evidence_status in ('available','unavailable','not_applicable')),
  financial_evidence_reason text check (length(financial_evidence_reason)<=500),
  financial_evidence_market_date date,
  cost_per_pack public.rip_benchmark_finite_v1 check (cost_per_pack>0),
  expected_value_per_pack public.rip_benchmark_finite_v1 check (expected_value_per_pack>=0),
  p05_value_per_pack public.rip_benchmark_finite_v1 check (p05_value_per_pack>=0),
  p10_value_per_pack public.rip_benchmark_finite_v1 check (p10_value_per_pack>=0),
  p25_value_per_pack public.rip_benchmark_finite_v1 check (p25_value_per_pack>=0),
  p50_value_per_pack public.rip_benchmark_finite_v1 check (p50_value_per_pack>=0),
  p75_value_per_pack public.rip_benchmark_finite_v1 check (p75_value_per_pack>=0),
  p90_value_per_pack public.rip_benchmark_finite_v1 check (p90_value_per_pack>=0),
  p95_value_per_pack public.rip_benchmark_finite_v1 check (p95_value_per_pack>=0),
  p99_value_per_pack public.rip_benchmark_finite_v1 check (p99_value_per_pack>=0),
  top_1pct_mean_per_pack public.rip_benchmark_finite_v1 check (top_1pct_mean_per_pack>=0),
  chance_to_recover_cost public.rip_benchmark_finite_v1 check (chance_to_recover_cost between 0 and 1),
  expected_loss_when_losing_per_pack public.rip_benchmark_finite_v1 check (expected_loss_when_losing_per_pack>=0),
  modeled_return_on_spend public.rip_benchmark_finite_v1 check (modeled_return_on_spend>=0),
  mean_outcome_retention public.rip_benchmark_finite_v1 check (mean_outcome_retention>=0),
  normalized_p10 public.rip_benchmark_finite_v1 check (normalized_p10>=0),
  normalized_p25 public.rip_benchmark_finite_v1 check (normalized_p25>=0),
  normalized_p50 public.rip_benchmark_finite_v1 check (normalized_p50>=0),
  normalized_p75 public.rip_benchmark_finite_v1 check (normalized_p75>=0),
  normalized_p90 public.rip_benchmark_finite_v1 check (normalized_p90>=0),
  normalized_p95 public.rip_benchmark_finite_v1 check (normalized_p95>=0),
  normalized_p99 public.rip_benchmark_finite_v1 check (normalized_p99>=0),
  top_1pct_ev_share public.rip_benchmark_finite_v1 check (top_1pct_ev_share between 0 and 1),
  primary key(publication_id,entity_type,entity_id,metric_key),
  foreign key(publication_id,market_date) references public.pokemon_rip_benchmark_publications_v1(id,market_date),
  check ((model_status='unavailable' and raw_model_value is null and rank is null and cohort_size is null and coalesce(length(btrim(model_reason)),0)>0)
    or (model_status in ('available','inherited') and raw_model_value is not null and source_model_version is not null
        and source_market_date is not null and source_entity_type is not null and source_entity_id is not null
        and reconstruction_status<>'unavailable')),
  check ((benchmark_status='unavailable' and benchmark_score is null and coalesce(length(btrim(benchmark_reason)),0)>0)
    or (benchmark_status='available' and model_status<>'unavailable' and benchmark_score is not null
        and benchmark_raw_value is not null and benchmark_source_fingerprint is not null)),
  check (benchmark_score is null or (raw_model_value=benchmark_raw_value and benchmark_score=5)
    or (raw_model_value>benchmark_raw_value and benchmark_score>5)
    or (raw_model_value<benchmark_raw_value and benchmark_score<5)),
  check ((rank is null and cohort_size is null) or (rank is not null and cohort_size is not null and rank>=1 and rank<=cohort_size)),
  check (entity_type<>'sealed_product' or parent_set_id is not null),
  check (model_status<>'inherited' or (entity_type='sealed_product' and metric_key in ('chase','collector')
    and source_entity_type='set' and source_entity_id=parent_set_id and reconstruction_status='inherited_parent_set' and rank is null)),
  check (entity_type<>'sealed_product' or metric_key not in ('chase','collector') or model_status in ('inherited','unavailable')),
  check (model_status<>'available' or (source_entity_type=entity_type and source_entity_id=entity_id)),
  check ((metric_key='financial' and financial_evidence_status in ('available','unavailable'))
    or (metric_key<>'financial' and financial_evidence_status='not_applicable')),
  check (financial_evidence_status<>'available' or (cost_per_pack is not null and expected_value_per_pack is not null
    and financial_evidence_market_date is not null and financial_evidence_market_date=market_date)),
  check (financial_evidence_status<>'unavailable' or coalesce(length(btrim(financial_evidence_reason)),0)>0),
  check (p05_value_per_pack<=p10_value_per_pack and p10_value_per_pack<=p25_value_per_pack
    and p25_value_per_pack<=p50_value_per_pack and p50_value_per_pack<=p75_value_per_pack
    and p75_value_per_pack<=p90_value_per_pack and p90_value_per_pack<=p95_value_per_pack and p95_value_per_pack<=p99_value_per_pack),
  check (normalized_p10<=normalized_p25 and normalized_p25<=normalized_p50 and normalized_p50<=normalized_p75
    and normalized_p75<=normalized_p90 and normalized_p90<=normalized_p95 and normalized_p95<=normalized_p99)
);
create index rip_benchmark_row_history_v1 on public.pokemon_rip_benchmark_rows_v1
  (entity_type,entity_id,market_date,metric_key,publication_id);

create function public.guard_rip_benchmark_v1() returns trigger
language plpgsql security invoker set search_path='' as $$
declare h public.pokemon_rip_benchmark_publications_v1%rowtype; n integer;
begin
  if tg_table_name='pokemon_rip_benchmark_rows_v1' then
    if tg_op<>'INSERT' then raise exception 'benchmark rows are append-only'; end if;
    select * into strict h from public.pokemon_rip_benchmark_publications_v1 where id=new.publication_id for update;
    if h.publication_status<>'staged' then raise exception 'publication is immutable'; end if;
    if new.source_market_date>new.market_date then raise exception 'future source date'; end if;
    if new.model_status<>'unavailable' and new.source_model_version is distinct from
      (case new.metric_key when 'financial' then h.financial_model_version when 'chase' then h.chase_model_version
      when 'collector' then h.collector_model_version else h.overall_model_version end) then raise exception 'source model mismatch'; end if;
    if new.model_status<>'unavailable' and new.source_market_date<>new.market_date
       and not (new.metric_key='collector' and new.collector_run_id is not null
         and coalesce((new.source_lineage->>'effective_from')::date<=new.market_date,false)
         and coalesce((new.source_lineage->>'effective_until')::date>=new.market_date,false))
      then raise exception 'source date mismatch: unavailable or proven Collector interval required'; end if;
    if new.model_status<>'unavailable' and new.metric_key='collector' and h.collector_lineage_status='exact_run'
       and new.collector_run_id is distinct from h.collector_run_id then raise exception 'Collector run mismatch'; end if;
    if new.financial_evidence_status='available' and new.entity_type='sealed_product'
       and (new.calculation_run_id is null or new.source_result_id is null) then raise exception 'product financial evidence requires exact run/result'; end if;
    if exists (select 1 from (select v,lag(v) over(order by ord) prev from unnest(array[
         new.p05_value_per_pack::numeric,new.p10_value_per_pack::numeric,new.p25_value_per_pack::numeric,new.p50_value_per_pack::numeric,
         new.p75_value_per_pack::numeric,new.p90_value_per_pack::numeric,new.p95_value_per_pack::numeric,new.p99_value_per_pack::numeric])
         with ordinality a(v,ord) where v is not null) q where prev>v)
       or exists (select 1 from (select v,lag(v) over(order by ord) prev from unnest(array[
         new.normalized_p10::numeric,new.normalized_p25::numeric,new.normalized_p50::numeric,new.normalized_p75::numeric,
         new.normalized_p90::numeric,new.normalized_p95::numeric,new.normalized_p99::numeric])
         with ordinality a(v,ord) where v is not null) q where prev>v)
       then raise exception 'nonmonotone supplied financial quantiles'; end if;
    if new.financial_evidence_status='available' and new.entity_type in ('set','era')
       and (h.opening_economics_snapshot_id is null or h.opening_economics_contract_version is distinct from 'pokemon-rip-stats-v3'
         or h.opening_economics_basis is distinct from 'all_modeled_products_per_pack_equivalent')
      then raise exception 'set/era evidence requires compatible V3 snapshot'; end if;
    if new.financial_evidence_status<>'available' and exists (
      select 1 from jsonb_each(to_jsonb(new)) e where (e.key in ('cost_per_pack','expected_value_per_pack','chance_to_recover_cost',
      'modeled_return_on_spend','mean_outcome_retention','top_1pct_ev_share') or e.key like '%_per_pack' or e.key like 'normalized_p%')
      and e.value<>'null'::jsonb) then raise exception 'unavailable financial evidence must remain null'; end if;
    return new;
  end if;
  if tg_op='INSERT' then
    if new.publication_status<>'staged' then raise exception 'publication must start staged'; end if;
    return new;
  end if;
  if tg_op='DELETE' then raise exception 'publication history is append-only'; end if;
  if (to_jsonb(new)-array['publication_status','published_at','superseded_at']) is distinct from
     (to_jsonb(old)-array['publication_status','published_at','superseded_at']) then raise exception 'publication lineage is immutable'; end if;
  if old.publication_status='staged' and new.publication_status='published' then
    select count(*) into n from public.pokemon_rip_benchmark_rows_v1 where publication_id=new.id;
    if n<>new.expected_row_count or exists (select 1 from public.pokemon_rip_benchmark_rows_v1 where publication_id=new.id
        group by entity_type,entity_id having count(*)<>4) then raise exception 'incomplete publication'; end if;
  elsif not (old.publication_status='published' and new.publication_status='superseded' and new.published_at=old.published_at)
    then raise exception 'invalid publication transition'; end if;
  return new;
end $$;
create trigger rip_benchmark_header_guard_v1 before insert or update or delete on public.pokemon_rip_benchmark_publications_v1
  for each row execute function public.guard_rip_benchmark_v1();
create trigger rip_benchmark_row_guard_v1 before insert or update or delete on public.pokemon_rip_benchmark_rows_v1
  for each row execute function public.guard_rip_benchmark_v1();

-- One transaction: validate immutable input, insert the complete cohort, then replace only this benchmark/date revision.
create function public.publish_pokemon_rip_benchmark_v1(p_header jsonb,p_rows jsonb,p_expected_previous_id uuid default null)
returns uuid language plpgsql security invoker set search_path='' set statement_timeout='15s' set lock_timeout='2s' as $$
declare h public.pokemon_rip_benchmark_publications_v1%rowtype; a record; s record; prior uuid; fp text; existing record; k text;
begin
  if jsonb_typeof(p_header) is distinct from 'object' or jsonb_typeof(p_rows) is distinct from 'array'
     or octet_length(p_header::text)>100000 or octet_length(p_rows::text)>8388608 then raise exception 'invalid or oversized publication'; end if;
  if jsonb_array_length(p_rows) not between 4 and 5000 then raise exception 'publication rows must be 4..5000'; end if;
  if exists(select 1 from jsonb_array_elements(p_rows) x where jsonb_typeof(x)<>'object') then raise exception 'rows must be objects'; end if;
  for k in select jsonb_object_keys(p_header) loop
    if k not in ('id','market_date','benchmark_key','calibration_version','expected_entity_count','expected_row_count','cohort_fingerprint',
      'source_fingerprint','overall_model_version','financial_model_version','chase_model_version','collector_model_version','collector_run_id',
      'collector_lineage_status','active_overall_publication_id','opening_economics_snapshot_id','opening_economics_contract_version',
      'opening_economics_basis','source_manifest') then raise exception 'unknown header field: %',k; end if;
  end loop;
  if exists(select 1 from jsonb_array_elements(p_rows) x cross join lateral jsonb_object_keys(x) keys(field_name)
     where keys.field_name in ('publication_id','market_date','raw_delta','score_delta') or not exists(select 1 from pg_catalog.pg_attribute a
       where a.attrelid='public.pokemon_rip_benchmark_rows_v1'::regclass and a.attnum>0 and not a.attisdropped and a.attname=keys.field_name))
    then raise exception 'unknown or server-owned row field'; end if;
  h:=jsonb_populate_record(null::public.pokemon_rip_benchmark_publications_v1,p_header);
  if h.id is null or h.market_date is null or h.benchmark_key is null or h.calibration_version is null then raise exception 'publication identity required'; end if;
  fp:=encode(sha256(convert_to(jsonb_build_object('header',p_header,'rows',p_rows)::text,'UTF8')),'hex');
  perform pg_advisory_xact_lock(hashtextextended('rip-benchmark-v1/'||h.benchmark_key||'/'||h.calibration_version||'/'||h.market_date::text,0));
  select id,request_fingerprint,publication_status into existing from public.pokemon_rip_benchmark_publications_v1 where id=h.id;
  if found then
    if existing.request_fingerprint<>fp or existing.publication_status<>'published' then raise exception 'idempotency conflict or superseded publication'; end if;
    return existing.id;
  end if;
  select id into prior from public.pokemon_rip_benchmark_publications_v1 where benchmark_key=h.benchmark_key
    and calibration_version=h.calibration_version and market_date=h.market_date and publication_status='published' for update;
  if prior is distinct from p_expected_previous_id then raise exception 'benchmark revision conflict'; end if;
  select c.publication_run_id,c.rankings_generation_id,c.set_page_generation_id,r.market_date,r.model_version,to_jsonb(r)-'validation_json' as lineage
    into strict a from public.pokemon_overall_rip_current_publication c join public.pokemon_overall_rip_publication_runs r on r.id=c.publication_run_id
    where c.scope='pokemon' and r.status='published';
  if a.publication_run_id is distinct from h.active_overall_publication_id then raise exception 'active Overall authority changed'; end if;
  if h.opening_economics_snapshot_id is not null then
    select market_date,publication_status,contract_version,methodology_version,weighting_version into strict s
      from public.pokemon_rip_stats_snapshots where id=h.opening_economics_snapshot_id;
    if s.market_date<>h.market_date or s.publication_status<>'published' or s.contract_version<>'pokemon-rip-stats-v3'
      or s.methodology_version<>'hierarchical_product_per_pack_empirical_v1' or s.weighting_version<>'equal-set_equal-family_equal-sku-v1'
      or h.opening_economics_contract_version is distinct from s.contract_version
      or h.opening_economics_basis is distinct from 'all_modeled_products_per_pack_equivalent' then raise exception 'incompatible Opening Economics authority'; end if;
  end if;
  h.publication_status:='staged'; h.request_fingerprint:=fp; h.previous_publication_id:=prior;
  h.active_overall_market_date:=a.market_date; h.active_overall_model_version:=a.model_version;
  h.active_rankings_generation_id:=a.rankings_generation_id; h.active_set_page_generation_id:=a.set_page_generation_id;
  h.active_release_lineage:=a.lineage; h.created_at:=clock_timestamp(); h.published_at:=null; h.superseded_at:=null;
  insert into public.pokemon_rip_benchmark_publications_v1 select h.*;
  -- Generated delta columns are excluded explicitly; JSON parsing is ingestion-only, never a source-artifact read.
  insert into public.pokemon_rip_benchmark_rows_v1 (publication_id,market_date,entity_type,entity_id,metric_key,parent_set_id,model_status,model_reason,benchmark_status,benchmark_reason,raw_model_value,benchmark_raw_value,benchmark_score,rank,cohort_size,source_model_version,source_market_date,source_entity_type,source_entity_id,source_publication_id,calculation_run_id,source_result_id,collector_run_id,source_fingerprint,benchmark_source_fingerprint,reconstruction_status,source_lineage,financial_evidence_status,financial_evidence_reason,financial_evidence_market_date,cost_per_pack,expected_value_per_pack,p05_value_per_pack,p10_value_per_pack,p25_value_per_pack,p50_value_per_pack,p75_value_per_pack,p90_value_per_pack,p95_value_per_pack,p99_value_per_pack,top_1pct_mean_per_pack,chance_to_recover_cost,expected_loss_when_losing_per_pack,modeled_return_on_spend,mean_outcome_retention,normalized_p10,normalized_p25,normalized_p50,normalized_p75,normalized_p90,normalized_p95,normalized_p99,top_1pct_ev_share)
  select h.id,h.market_date,x.entity_type,x.entity_id,x.metric_key,x.parent_set_id,x.model_status,x.model_reason,x.benchmark_status,x.benchmark_reason,x.raw_model_value,x.benchmark_raw_value,x.benchmark_score,x.rank,x.cohort_size,x.source_model_version,x.source_market_date,x.source_entity_type,x.source_entity_id,x.source_publication_id,x.calculation_run_id,x.source_result_id,x.collector_run_id,x.source_fingerprint,x.benchmark_source_fingerprint,x.reconstruction_status,x.source_lineage,x.financial_evidence_status,x.financial_evidence_reason,x.financial_evidence_market_date,x.cost_per_pack,x.expected_value_per_pack,x.p05_value_per_pack,x.p10_value_per_pack,x.p25_value_per_pack,x.p50_value_per_pack,x.p75_value_per_pack,x.p90_value_per_pack,x.p95_value_per_pack,x.p99_value_per_pack,x.top_1pct_mean_per_pack,x.chance_to_recover_cost,x.expected_loss_when_losing_per_pack,x.modeled_return_on_spend,x.mean_outcome_retention,x.normalized_p10,x.normalized_p25,x.normalized_p50,x.normalized_p75,x.normalized_p90,x.normalized_p95,x.normalized_p99,x.top_1pct_ev_share
  from jsonb_populate_recordset(null::public.pokemon_rip_benchmark_rows_v1,p_rows) x;
  if prior is not null then update public.pokemon_rip_benchmark_publications_v1 set publication_status='superseded',superseded_at=clock_timestamp() where id=prior; end if;
  update public.pokemon_rip_benchmark_publications_v1 set publication_status='published',published_at=clock_timestamp() where id=h.id;
  return h.id;
end $$;

create function public.assert_rip_benchmark_entities_v1(p_entities jsonb) returns void
language plpgsql immutable security invoker set search_path='' as $$
begin
  if jsonb_typeof(p_entities) is distinct from 'array' or octet_length(p_entities::text)>4096 then raise exception 'entities must be a bounded array'; end if;
  if jsonb_array_length(p_entities) not between 1 and 10 then raise exception 'request 1..10 entities'; end if;
  if exists(select 1 from jsonb_array_elements(p_entities) x where jsonb_typeof(x)<>'object') then raise exception 'entity must be an object'; end if;
  if exists(select 1 from jsonb_array_elements(p_entities) x cross join lateral jsonb_object_keys(x) k where k not in ('entity_type','entity_id'))
    or exists(select 1 from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid) where e.entity_type is null
      or e.entity_type not in ('set','era','sealed_product') or e.entity_id is null)
    or (select count(distinct (e.entity_type,e.entity_id)) from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid))<>jsonb_array_length(p_entities)
    then raise exception 'invalid or duplicate entity'; end if;
end $$;

create function public.get_pokemon_rip_benchmark_history_v1(
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
  ), page as materialized (select * from matches order by market_date,entity_type,entity_id,metric_key limit p_limit)
  select jsonb_build_object('contract_version','rip-benchmark-read-v1','benchmark_key',p_benchmark_key,'calibration_version',p_calibration_version,
    'start_date',p_start_date,'end_date',p_end_date,'rows',coalesce((select jsonb_agg(to_jsonb(x)-'source_lineage' order by market_date,entity_type,entity_id,metric_key) from page x),'[]'::jsonb),
    'has_more',(select count(*)>p_limit from matches),'next_cursor',case when (select count(*)>p_limit from matches) then
      (select jsonb_build_object('market_date',market_date,'entity_type',entity_type,'entity_id',entity_id,'metric_key',metric_key,
        'publication_signature',pubsig,'query_signature',querysig) from page order by market_date desc,entity_type desc,entity_id desc,metric_key desc limit 1) else null end)
  into result;
  return result;
end $$;

create function public.get_pokemon_rip_benchmark_current_v1(p_entities jsonb,p_benchmark_key text,p_calibration_version text)
returns jsonb language plpgsql stable security invoker set search_path='' set statement_timeout='5s' as $$
declare h public.pokemon_rip_benchmark_publications_v1%rowtype; result jsonb;
begin
  perform public.assert_rip_benchmark_entities_v1(p_entities);
  if coalesce(length(p_benchmark_key),0) not between 1 and 100 or coalesce(length(p_calibration_version),0) not between 1 and 160 then raise exception 'explicit benchmark/version required'; end if;
  select * into h from public.pokemon_rip_benchmark_publications_v1 where benchmark_key=p_benchmark_key and calibration_version=p_calibration_version
    and publication_status='published' order by market_date desc limit 1;
  if not found then return jsonb_build_object('contract_version','rip-benchmark-read-v1','status','unavailable','reason','no_published_benchmark','rows','[]'::jsonb); end if;
  select jsonb_build_object('contract_version','rip-benchmark-read-v1','status','available','publication_id',h.id,'market_date',h.market_date,
    'benchmark_key',h.benchmark_key,'calibration_version',h.calibration_version,'source_fingerprint',h.source_fingerprint,'cohort_fingerprint',h.cohort_fingerprint,
    'active_overall_publication_id',h.active_overall_publication_id,'active_overall_market_date',h.active_overall_market_date,
    'overall_model_version',h.overall_model_version,'financial_model_version',h.financial_model_version,'chase_model_version',h.chase_model_version,
    'collector_model_version',h.collector_model_version,'collector_run_id',h.collector_run_id,'published_at',h.published_at,
    'rows',coalesce(jsonb_agg(to_jsonb(r)-'source_lineage' order by r.entity_type,r.entity_id,r.metric_key),'[]'::jsonb)) into result
  from jsonb_to_recordset(p_entities) e(entity_type text,entity_id uuid) join public.pokemon_rip_benchmark_rows_v1 r
    on r.publication_id=h.id and r.entity_type=e.entity_type and r.entity_id=e.entity_id;
  return result;
end $$;

alter table public.pokemon_rip_benchmark_publications_v1 enable row level security;
alter table public.pokemon_rip_benchmark_rows_v1 enable row level security;
revoke all on public.pokemon_rip_benchmark_publications_v1,public.pokemon_rip_benchmark_rows_v1 from public,anon,authenticated,service_role;
grant select,insert,update on public.pokemon_rip_benchmark_publications_v1 to service_role;
grant select,insert on public.pokemon_rip_benchmark_rows_v1 to service_role;
create policy rip_benchmark_header_service_v1 on public.pokemon_rip_benchmark_publications_v1 to service_role using(true) with check(true);
create policy rip_benchmark_row_service_v1 on public.pokemon_rip_benchmark_rows_v1 to service_role using(true) with check(true);
revoke all on domain public.rip_benchmark_finite_v1 from public,anon,authenticated;
grant usage on domain public.rip_benchmark_finite_v1 to service_role;
revoke all on function public.guard_rip_benchmark_v1(),public.assert_rip_benchmark_entities_v1(jsonb),
  public.publish_pokemon_rip_benchmark_v1(jsonb,jsonb,uuid),public.get_pokemon_rip_benchmark_history_v1(jsonb,date,date,text,text,integer,jsonb),
  public.get_pokemon_rip_benchmark_current_v1(jsonb,text,text) from public,anon,authenticated;
grant execute on function public.assert_rip_benchmark_entities_v1(jsonb),public.publish_pokemon_rip_benchmark_v1(jsonb,jsonb,uuid),
  public.get_pokemon_rip_benchmark_history_v1(jsonb,date,date,text,text,integer,jsonb),public.get_pokemon_rip_benchmark_current_v1(jsonb,text,text) to service_role;
comment on table public.pokemon_rip_benchmark_rows_v1 is 'Private four-metric entity/day projection; missing model, benchmark, and financial evidence are independent. Raw and score deltas are arithmetic only, never a scoring transform.';
comment on function public.get_pokemon_rip_benchmark_history_v1(jsonb,date,date,text,text,integer,jsonb) is 'Service-role-only: 1..10 entities, <=366 inclusive days, <=1000 rows plus keyset cursor. ALL is caller-chunked. Cursor rejects publication changes. No source artifacts or full history JSON.';
