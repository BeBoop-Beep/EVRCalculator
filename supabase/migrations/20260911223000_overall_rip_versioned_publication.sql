-- Generic, append-only Overall RIP publication authority. Inert until promoted.
create table if not exists public.pokemon_overall_rip_publication_runs (
  id uuid primary key default gen_random_uuid(),
  model_version text not null,
  market_date date not null,
  status text not null check (status in ('staged','validated','published','superseded')),
  financial_version text not null,
  chase_version text not null,
  collector_version text not null,
  collector_run_id uuid,
  formula_fingerprint text not null,
  cohort_fingerprint text not null,
  expected_row_count integer not null check (expected_row_count >= 0),
  validation_json jsonb not null default '{}'::jsonb,
  previous_publication_run_id uuid references public.pokemon_overall_rip_publication_runs(id),
  created_at timestamptz not null default timezone('utc',now()),
  validated_at timestamptz,
  published_at timestamptz,
  unique(model_version,market_date,cohort_fingerprint)
);

create table if not exists public.pokemon_overall_rip_publication_rows (
  publication_run_id uuid not null references public.pokemon_overall_rip_publication_runs(id),
  source_result_id uuid not null,
  sealed_product_id uuid not null,
  set_id uuid not null,
  calculation_run_id uuid not null,
  score numeric,
  rank integer,
  tier text,
  eligibility_state text not null,
  financial_run_id uuid,
  chase_run_id uuid,
  collector_run_id uuid,
  component_lineage jsonb not null,
  authority_json jsonb not null,
  created_at timestamptz not null default timezone('utc',now()),
  primary key(publication_run_id,source_result_id),
  check ((eligibility_state='ready' and score is not null and rank is not null and tier is not null)
      or (eligibility_state<>'ready' and score is null and rank is null and tier is null))
);

create table if not exists public.pokemon_overall_rip_publication_generations (
  id uuid primary key default gen_random_uuid(),
  publication_run_id uuid not null references public.pokemon_overall_rip_publication_runs(id),
  generation_kind text not null check (generation_kind in ('rankings','set_page')),
  status text not null check(status in ('building','validated','published','superseded')),
  expected_row_count integer not null,
  validation_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc',now()),
  validated_at timestamptz,
  published_at timestamptz,
  unique(publication_run_id,generation_kind)
);

create table if not exists public.pokemon_overall_rip_publication_generation_rows (
  generation_id uuid not null references public.pokemon_overall_rip_publication_generations(id),
  entity_id uuid not null,
  projection_json jsonb not null,
  primary key(generation_id,entity_id)
);

create table if not exists public.pokemon_overall_rip_current_publication (
  scope text primary key check(scope='pokemon'),
  publication_run_id uuid not null references public.pokemon_overall_rip_publication_runs(id),
  rankings_generation_id uuid not null references public.pokemon_overall_rip_publication_generations(id),
  set_page_generation_id uuid not null references public.pokemon_overall_rip_publication_generations(id),
  activated_at timestamptz not null default timezone('utc',now())
);

alter table public.pokemon_overall_rip_publication_runs enable row level security;
alter table public.pokemon_overall_rip_publication_rows enable row level security;
alter table public.pokemon_overall_rip_publication_generations enable row level security;
alter table public.pokemon_overall_rip_publication_generation_rows enable row level security;
alter table public.pokemon_overall_rip_current_publication enable row level security;

revoke all on public.pokemon_overall_rip_publication_runs,public.pokemon_overall_rip_publication_rows,
 public.pokemon_overall_rip_publication_generations,public.pokemon_overall_rip_publication_generation_rows,
 public.pokemon_overall_rip_current_publication from public,anon,authenticated;
grant select,insert,update on public.pokemon_overall_rip_publication_runs,public.pokemon_overall_rip_publication_rows,
 public.pokemon_overall_rip_publication_generations,public.pokemon_overall_rip_publication_generation_rows,
 public.pokemon_overall_rip_current_publication to service_role;

create or replace function public.promote_pokemon_overall_rip_publication(p_publication_run_id uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare r public.pokemon_overall_rip_publication_runs%rowtype; rg uuid; sg uuid; prior uuid; n integer;
begin
  if auth.role() <> 'service_role' then raise exception 'service_role required'; end if;
  select * into strict r from public.pokemon_overall_rip_publication_runs where id=p_publication_run_id for update;
  if r.status not in ('validated','superseded') or coalesce((r.validation_json->>'passed')::boolean,false)=false then
    raise exception 'publication % is not validated',p_publication_run_id;
  end if;
  select id into strict rg from public.pokemon_overall_rip_publication_generations where publication_run_id=r.id and generation_kind='rankings' and status in ('validated','superseded') and coalesce((validation_json->>'passed')::boolean,false)=true;
  select id into strict sg from public.pokemon_overall_rip_publication_generations where publication_run_id=r.id and generation_kind='set_page' and status in ('validated','superseded') and coalesce((validation_json->>'passed')::boolean,false)=true;
  select count(*) into n from public.pokemon_overall_rip_publication_rows where publication_run_id=r.id;
  if n<>r.expected_row_count then raise exception 'publication row count mismatch'; end if;
  select publication_run_id into prior from public.pokemon_overall_rip_current_publication where scope='pokemon' for update;
  if prior is not null and prior<>r.id then update public.pokemon_overall_rip_publication_runs set status='superseded' where id=prior; end if;
  update public.pokemon_overall_rip_publication_runs set status='published',published_at=timezone('utc',now()),previous_publication_run_id=coalesce(previous_publication_run_id,prior) where id=r.id;
  update public.pokemon_overall_rip_publication_generations set status='published',published_at=timezone('utc',now()) where id in(rg,sg);
  insert into public.pokemon_overall_rip_current_publication(scope,publication_run_id,rankings_generation_id,set_page_generation_id,activated_at)
  values('pokemon',r.id,rg,sg,timezone('utc',now())) on conflict(scope) do update set publication_run_id=excluded.publication_run_id,rankings_generation_id=excluded.rankings_generation_id,set_page_generation_id=excluded.set_page_generation_id,activated_at=excluded.activated_at;
  return r.id;
end $$;
revoke all on function public.promote_pokemon_overall_rip_publication(uuid) from public,anon,authenticated;
grant execute on function public.promote_pokemon_overall_rip_publication(uuid) to service_role;

create or replace view public.pokemon_overall_rip_active_v with (security_invoker=true) as
select r.model_version,r.market_date,r.formula_fingerprint,r.cohort_fingerprint,
 c.rankings_generation_id,c.set_page_generation_id,x.*
from public.pokemon_overall_rip_current_publication c
join public.pokemon_overall_rip_publication_runs r on r.id=c.publication_run_id
join public.pokemon_overall_rip_publication_rows x on x.publication_run_id=r.id
where c.scope='pokemon' and r.status='published';
revoke all on public.pokemon_overall_rip_active_v from public,anon,authenticated;
grant select on public.pokemon_overall_rip_active_v to service_role;

comment on view public.pokemon_overall_rip_active_v is 'Generic active Overall authority. Application projection only; legacy V12 readers remain unchanged until deployment.';

-- Seed the immutable current V12 authority and accepted inactive V13 authority.
do $$
declare v12 uuid; v13 uuid; v12rg uuid; v12sg uuid; v13rg uuid; v13sg uuid; cohort text; n integer;
begin
 select encode(extensions.digest(string_agg(r.sealed_product_id::text,',' order by r.sealed_product_id),'sha256'),'hex'),count(*)
 into cohort,n from public.simulation_sealed_product_results r
 where r.price_as_of=(select max(price_as_of) from public.simulation_sealed_product_results where overall_rip_v12_status='ready') and r.overall_rip_v12_status='ready';
 insert into public.pokemon_overall_rip_publication_runs(model_version,market_date,status,financial_version,chase_version,collector_version,formula_fingerprint,cohort_fingerprint,expected_row_count,validation_json,validated_at,published_at)
 values('overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5',(select max(price_as_of) from public.simulation_sealed_product_results where overall_rip_v12_status='ready'),'published','financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5','chase_accessibility_v1_hc_value_squared_modeled_probability','collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2','ff9ec20d1a952885e0eb224e90d8a84b7120f64ccf3c7c065a0b0af73c033201',cohort,n,jsonb_build_object('passed',true,'source','immutable V12 production readback'),timezone('utc',now()),timezone('utc',now())) returning id into v12;
 insert into public.pokemon_overall_rip_publication_rows
 select v12,r.id,r.sealed_product_id,r.set_id,r.calculation_run_id,r.overall_rip_v12_score,
 rank() over(order by r.overall_rip_v12_score desc,r.sealed_product_id),
 case when r.overall_rip_v12_score>=90 then 'S' when r.overall_rip_v12_score>=75 then 'A' when r.overall_rip_v12_score>=55 then 'B' when r.overall_rip_v12_score>=35 then 'C' when r.overall_rip_v12_score>=15 then 'D' else 'F' end,
 'ready',r.calculation_run_id,r.calculation_run_id,null,
 jsonb_build_object('financialVersion',r.financial_rip_v4_version,'chaseVersion','chase_accessibility_v1_hc_value_squared_modeled_probability','collectorVersion',r.collector_appeal_version),r.overall_rip_v12_payload,timezone('utc',now())
 from public.simulation_sealed_product_results r where r.price_as_of=(select max(price_as_of) from public.simulation_sealed_product_results where overall_rip_v12_status='ready') and r.overall_rip_v12_status='ready';
 insert into public.pokemon_overall_rip_publication_generations(publication_run_id,generation_kind,status,expected_row_count,validation_json,validated_at,published_at) values(v12,'rankings','published',n,jsonb_build_object('passed',true),timezone('utc',now()),timezone('utc',now())) returning id into v12rg;
 insert into public.pokemon_overall_rip_publication_generation_rows select v12rg,source_result_id,authority_json from public.pokemon_overall_rip_publication_rows where publication_run_id=v12;
 insert into public.pokemon_overall_rip_publication_generations(publication_run_id,generation_kind,status,expected_row_count,validation_json,validated_at,published_at) values(v12,'set_page','published',(select count(*) from public.pokemon_set_page_snapshot_latest),jsonb_build_object('passed',true,'legacyGeneration',(select generation_id from public.pokemon_set_page_snapshot_current_generation where scope='pokemon')),timezone('utc',now()),timezone('utc',now())) returning id into v12sg;
 insert into public.pokemon_overall_rip_publication_generation_rows select v12sg,set_id,jsonb_build_object('overallPublicationRunId',v12,'legacyPayload',payload_json) from public.pokemon_set_page_snapshot_latest;
 insert into public.pokemon_overall_rip_current_publication values('pokemon',v12,v12rg,v12sg,timezone('utc',now()));

 insert into public.pokemon_overall_rip_publication_runs(model_version,market_date,status,financial_version,chase_version,collector_version,collector_run_id,formula_fingerprint,cohort_fingerprint,expected_row_count,validation_json,previous_publication_run_id,validated_at)
 values('overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7',(select max(price_as_of) from public.simulation_sealed_product_results where overall_rip_v12_status='ready'),'validated','financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5','chase_accessibility_v1_hc_value_squared_modeled_probability','pokemon_collector_appeal_v7_expanded_price_blind_v1','e282f26e-2136-4105-b0a3-f0974c4d9d70','9e0bbcb7aa37cde8b92556fd0f008a8c2a39484e7de3f868752ac5e3f3a73497',cohort,n,jsonb_build_object('passed',true,'shadowMeanDelta',-0.278366666666666,'shadowMedianDelta',-0.6181,'shadowRankAgreement',0.982844422882093,'top10Overlap',9),v12,timezone('utc',now())) returning id into v13;
 insert into public.pokemon_overall_rip_publication_rows
 select v13,q.id,q.sealed_product_id,q.set_id,q.calculation_run_id,q.score,
 rank() over(order by q.score desc,q.sealed_product_id),case when q.score>=90 then 'S' when q.score>=75 then 'A' when q.score>=55 then 'B' when q.score>=35 then 'C' when q.score>=15 then 'D' else 'F' end,
 'ready',q.calculation_run_id,q.calculation_run_id,'e282f26e-2136-4105-b0a3-f0974c4d9d70',
 jsonb_build_object('financialVersion',q.financial_rip_v4_version,'financialRunId',q.calculation_run_id,'chaseVersion','chase_accessibility_v1_hc_value_squared_modeled_probability','chaseRunId',q.calculation_run_id,'collectorVersion','pokemon_collector_appeal_v7_expanded_price_blind_v1','collectorRunId','e282f26e-2136-4105-b0a3-f0974c4d9d70'),
 jsonb_build_object('score',q.score,'rankable',true,'version','overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7','weights',jsonb_build_object('financial_rip',.86,'chase_accessibility',.04,'collector_appeal',.10),'components',jsonb_build_object('financialRipV4',q.fin,'chaseAccessibility',q.chase,'collectorAppeal',q.v7)),timezone('utc',now())
 from (select r.*,round((.86*(r.overall_rip_v12_payload#>>'{components,financialRipV4,score}')::numeric+.04*(r.overall_rip_v12_payload#>>'{components,chaseAccessibility,score}')::numeric+.10*c.collector_appeal_score)::numeric,4) score,(r.overall_rip_v12_payload#>'{components,financialRipV4}') fin,(r.overall_rip_v12_payload#>'{components,chaseAccessibility}') chase,c.collector_appeal_score v7
 from public.simulation_sealed_product_results r join public.pokemon_set_collector_appeal_scores c on c.set_id=r.set_id and c.model_run_id='e282f26e-2136-4105-b0a3-f0974c4d9d70'
 where r.price_as_of=(select max(price_as_of) from public.simulation_sealed_product_results where overall_rip_v12_status='ready') and r.overall_rip_v12_status='ready' and c.score_status='scored') q;
 insert into public.pokemon_overall_rip_publication_generations(publication_run_id,generation_kind,status,expected_row_count,validation_json,validated_at) values(v13,'rankings','validated',n,jsonb_build_object('passed',true,'authority','V13'),timezone('utc',now())) returning id into v13rg;
 insert into public.pokemon_overall_rip_publication_generation_rows select v13rg,source_result_id,authority_json from public.pokemon_overall_rip_publication_rows where publication_run_id=v13;
 insert into public.pokemon_overall_rip_publication_generations(publication_run_id,generation_kind,status,expected_row_count,validation_json,validated_at) values(v13,'set_page','validated',(select count(*) from public.pokemon_set_page_snapshot_latest),jsonb_build_object('passed',true,'fullMembership',true,'legacyGeneration',(select generation_id from public.pokemon_set_page_snapshot_current_generation where scope='pokemon')),timezone('utc',now())) returning id into v13sg;
 insert into public.pokemon_overall_rip_publication_generation_rows select v13sg,set_id,jsonb_build_object('overallPublicationRunId',v13,'overallModelVersion','overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7','legacyPayload',payload_json) from public.pokemon_set_page_snapshot_latest;
end $$;
