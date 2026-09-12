begin;

create table public.pokemon_set_page_snapshot_generations (
 id uuid primary key default gen_random_uuid(),
 status text not null default 'building' check(status in('building','validated','published','failed')),
 expected_set_ids uuid[] not null,
 expected_set_count integer not null check(expected_set_count>=0),
 completed_set_count integer not null default 0 check(completed_set_count>=0),
 collector_model_run_id uuid references public.pokemon_collector_appeal_model_runs(id),
 collector_contract_version text,
 expected_collector_row_count integer not null default 0 check(expected_collector_row_count>=0),
 validation_passed boolean not null default false,
 validation_json jsonb not null default '{}'::jsonb,
 diagnostics_json jsonb not null default '{}'::jsonb,
 previous_generation_id uuid references public.pokemon_set_page_snapshot_generations(id),
 built_at timestamptz not null default timezone('utc',now()),
 validated_at timestamptz,
 published_at timestamptz,
 created_at timestamptz not null default timezone('utc',now()),
 constraint expected_set_identity_unique check(cardinality(expected_set_ids)=expected_set_count)
);
create unique index pokemon_set_page_one_building_generation_idx on public.pokemon_set_page_snapshot_generations((status)) where status='building';

create table public.pokemon_set_page_snapshot_generation_rows (
 generation_id uuid not null references public.pokemon_set_page_snapshot_generations(id),
 set_id uuid not null,
 set_identity_json jsonb not null, title_card_json jsonb not null,
 rip_summary_json jsonb not null, market_summary_json jsonb not null,
 risk_summary_json jsonb not null, concentration_json jsonb not null,
 desirability_summary_json jsonb not null, set_intelligence_json jsonb not null,
 payload_json jsonb not null, as_of timestamptz, source_updated_at timestamptz,
 created_at timestamptz not null, updated_at timestamptz not null,
 rip_bootstrap_json jsonb, rip_simulation_evidence_json jsonb, rip_advanced_json jsonb,
 primary key(generation_id,set_id)
);
create index pokemon_set_page_snapshot_generation_rows_set_idx on public.pokemon_set_page_snapshot_generation_rows(set_id,generation_id);

create table public.pokemon_set_page_snapshot_current_generation (
 scope text primary key check(scope='pokemon'),
 generation_id uuid not null references public.pokemon_set_page_snapshot_generations(id),
 activated_at timestamptz not null default timezone('utc',now())
);

alter table public.pokemon_set_page_snapshot_generations enable row level security;
alter table public.pokemon_set_page_snapshot_generation_rows enable row level security;
alter table public.pokemon_set_page_snapshot_current_generation enable row level security;
revoke all on public.pokemon_set_page_snapshot_generations,public.pokemon_set_page_snapshot_generation_rows,public.pokemon_set_page_snapshot_current_generation from public,anon,authenticated;
grant select,insert,update on public.pokemon_set_page_snapshot_generations to service_role;
grant select,insert,update,delete on public.pokemon_set_page_snapshot_generation_rows to service_role;
grant select,insert,update on public.pokemon_set_page_snapshot_current_generation to service_role;

-- Adopt the pre-generation compatibility table as rollback authority.
do $$ declare gid uuid; ids uuid[]; n integer;
begin
 select coalesce(array_agg(set_id order by set_id),'{}'::uuid[]),count(*) into ids,n from public.pokemon_set_page_snapshot_latest;
 insert into public.pokemon_set_page_snapshot_generations(status,expected_set_ids,expected_set_count,completed_set_count,validation_passed,validation_json,published_at,diagnostics_json)
 values('published',ids,n,n,true,jsonb_build_object('passed',true,'adoptedLegacyGeneration',true),timezone('utc',now()),jsonb_build_object('source','pre_generation_pokemon_set_page_snapshot_latest')) returning id into gid;
 insert into public.pokemon_set_page_snapshot_generation_rows select gid,s.* from public.pokemon_set_page_snapshot_latest s;
 insert into public.pokemon_set_page_snapshot_current_generation(scope,generation_id) values('pokemon',gid);
end $$;

create or replace function public.validate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare g public.pokemon_set_page_snapshot_generations%rowtype; actual_ids uuid[]; actual_count int; collector_count int; bad int; passed boolean; report jsonb;
begin
 select * into g from public.pokemon_set_page_snapshot_generations where id=p_generation_id for update;
 if not found or g.status<>'building' then raise exception 'generation % is not building',p_generation_id; end if;
 select coalesce(array_agg(set_id order by set_id),'{}'::uuid[]),count(*) into actual_ids,actual_count from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 select count(*) filter(where payload_json?'publicCollectorAppealContractV1'),count(*) filter(where payload_json is null or jsonb_typeof(payload_json)<>'object' or (payload_json?'publicCollectorAppealContractV1' and (payload_json#>>'{publicCollectorAppealContractV1,contractVersion}' is distinct from g.collector_contract_version or payload_json#>>'{publicCollectorAppealContractV1,collectorAppeal,modelRunId}' is distinct from g.collector_model_run_id::text)))
 into collector_count,bad from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 passed:=actual_count=g.expected_set_count and actual_ids=g.expected_set_ids and collector_count=g.expected_collector_row_count and bad=0;
 report:=jsonb_build_object('passed',passed,'expectedSetCount',g.expected_set_count,'actualSetCount',actual_count,'expectedCollectorRows',g.expected_collector_row_count,'actualCollectorRows',collector_count,'invalidRows',bad,'collectorModelRunId',g.collector_model_run_id,'collectorContractVersion',g.collector_contract_version);
 update public.pokemon_set_page_snapshot_generations set status=case when passed then 'validated' else 'failed' end,completed_set_count=actual_count,validation_passed=passed,validation_json=report,validated_at=timezone('utc',now()) where id=p_generation_id;
 return report;
end $$;

create or replace function public.activate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare g public.pokemon_set_page_snapshot_generations%rowtype; prior uuid; n int;
begin
 select * into g from public.pokemon_set_page_snapshot_generations where id=p_generation_id for update;
 if not found or g.status not in('validated','published') or not g.validation_passed or coalesce((g.validation_json->>'passed')::boolean,false)=false then raise exception 'generation % is not validated',p_generation_id; end if;
 select generation_id into prior from public.pokemon_set_page_snapshot_current_generation where scope='pokemon' for update;
 select count(*) into n from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 if n<>g.expected_set_count then raise exception 'generation % became incomplete',p_generation_id; end if;
 delete from public.pokemon_set_page_snapshot_latest where set_id is not null;
 insert into public.pokemon_set_page_snapshot_latest select set_id,set_identity_json,title_card_json,rip_summary_json,market_summary_json,risk_summary_json,concentration_json,desirability_summary_json,set_intelligence_json,payload_json,as_of,source_updated_at,created_at,updated_at,rip_bootstrap_json,rip_simulation_evidence_json,rip_advanced_json from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 insert into public.pokemon_set_page_snapshot_current_generation(scope,generation_id,activated_at) values('pokemon',p_generation_id,timezone('utc',now())) on conflict(scope) do update set generation_id=excluded.generation_id,activated_at=excluded.activated_at;
 update public.pokemon_set_page_snapshot_generations set status='published',previous_generation_id=case when prior is distinct from p_generation_id then prior else previous_generation_id end,published_at=coalesce(published_at,timezone('utc',now())) where id=p_generation_id;
 return p_generation_id;
end $$;

revoke all on function public.validate_pokemon_set_page_snapshot_generation(uuid),public.activate_pokemon_set_page_snapshot_generation(uuid) from public,anon,authenticated;
grant execute on function public.validate_pokemon_set_page_snapshot_generation(uuid),public.activate_pokemon_set_page_snapshot_generation(uuid) to service_role;
commit;
