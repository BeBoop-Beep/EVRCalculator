-- Rankings redesign Bucket 1: prepared Card Rankings facets by authority generation.
create table public.pokemon_card_ranking_facet_generations_v1 (
  id uuid primary key default gen_random_uuid(),
  lens text not null check(lens in ('collector','chase')),
  source_authority_id uuid not null,
  source_model_version text not null,
  as_of_date date not null,
  built_at timestamptz not null default now(),
  unique(lens,source_authority_id)
);
create table public.pokemon_card_ranking_facets_v1 (
  generation_id uuid not null references public.pokemon_card_ranking_facet_generations_v1(id) on delete restrict,
  lens text not null check(lens in ('collector','chase')),
  dimension_type text not null check(dimension_type in ('era','set','rarity','subject_type')),
  facet_key text not null,
  display_name text not null,
  entity_id uuid,
  parent_entity_id uuid,
  primary key(generation_id,dimension_type,facet_key)
);
create index pokemon_card_ranking_facets_lookup_v1 on public.pokemon_card_ranking_facets_v1(lens,dimension_type,generation_id,display_name);
create index pokemon_card_ranking_facet_generations_current_v1 on public.pokemon_card_ranking_facet_generations_v1(lens,built_at desc);
alter table public.pokemon_card_ranking_facet_generations_v1 enable row level security;
alter table public.pokemon_card_ranking_facets_v1 enable row level security;
revoke all on public.pokemon_card_ranking_facet_generations_v1 from public,anon,authenticated;
revoke all on public.pokemon_card_ranking_facets_v1 from public,anon,authenticated;
grant select,insert on public.pokemon_card_ranking_facet_generations_v1 to service_role;
grant select,insert on public.pokemon_card_ranking_facets_v1 to service_role;
create policy pokemon_card_ranking_facet_generations_service_v1 on public.pokemon_card_ranking_facet_generations_v1 for select to service_role using(true);
create policy pokemon_card_ranking_facet_generations_insert_service_v1 on public.pokemon_card_ranking_facet_generations_v1 for insert to service_role with check(true);
create policy pokemon_card_ranking_facets_service_v1 on public.pokemon_card_ranking_facets_v1 for select to service_role using(true);
create policy pokemon_card_ranking_facets_insert_service_v1 on public.pokemon_card_ranking_facets_v1 for insert to service_role with check(true);

create or replace function public.refresh_pokemon_card_ranking_facets_v1()
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare c_run uuid; c_model text; c_date date; c_gen uuid; h_snap uuid; h_model text; h_date date; h_gen uuid;
begin
  select (array_agg(model_run_id order by model_run_id::text))[1],min(model_version),min(as_of_date)
  into c_run,c_model,c_date from public.pokemon_card_collector_appeal_rankings_current_v;
  if c_run is not null and 1=(select count(distinct model_run_id) from public.pokemon_card_collector_appeal_rankings_current_v) then
    insert into public.pokemon_card_ranking_facet_generations_v1(lens,source_authority_id,source_model_version,as_of_date)
    values('collector',c_run,c_model,c_date) on conflict(lens,source_authority_id) do nothing;
    select id into c_gen from public.pokemon_card_ranking_facet_generations_v1 where lens='collector' and source_authority_id=c_run;
    insert into public.pokemon_card_ranking_facets_v1
      select c_gen,'collector','era',era_canonical_key,era_name,era_id,null::uuid
      from public.pokemon_card_collector_appeal_rankings_current_v where era_id is not null
      group by era_canonical_key,era_name,era_id on conflict do nothing;
    insert into public.pokemon_card_ranking_facets_v1
      select c_gen,'collector','set',set_canonical_key,set_name,set_id,(array_agg(era_id order by era_id::text))[1]
      from public.pokemon_card_collector_appeal_rankings_current_v where set_id is not null
      group by set_canonical_key,set_name,set_id on conflict do nothing;
    insert into public.pokemon_card_ranking_facets_v1(generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id)
      select c_gen,'collector','rarity',lower(rarity),rarity,null::uuid,null::uuid
      from public.pokemon_card_collector_appeal_rankings_current_v where rarity is not null group by rarity on conflict do nothing;
    insert into public.pokemon_card_ranking_facets_v1(generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id)
      select c_gen,'collector','subject_type',lower(subject_type),subject_type,null::uuid,null::uuid
      from public.pokemon_card_collector_appeal_rankings_current_v where subject_type is not null group by subject_type on conflict do nothing;
  end if;

  select l.snapshot_id,s.calculation_methodology_version,l.market_date into h_snap,h_model,h_date
  from public.pokemon_card_chase_efficiency_latest l
  join public.pokemon_card_chase_efficiency_snapshots s on s.id=l.snapshot_id limit 1;
  if h_snap is not null then
    insert into public.pokemon_card_ranking_facet_generations_v1(lens,source_authority_id,source_model_version,as_of_date)
    values('chase',h_snap,h_model,h_date) on conflict(lens,source_authority_id) do nothing;
    select id into h_gen from public.pokemon_card_ranking_facet_generations_v1 where lens='chase' and source_authority_id=h_snap;
    insert into public.pokemon_card_ranking_facets_v1(generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id)
      select distinct h_gen,'chase','era',c.era_canonical_key,c.era_name,r.era_id,null::uuid
      from public.pokemon_card_chase_efficiency_rows r
      join (select distinct era_id,era_canonical_key,era_name from public.pokemon_card_collector_appeal_rankings_current_v) c on c.era_id=r.era_id
      where r.snapshot_id=h_snap and r.era_id is not null on conflict do nothing;
    insert into public.pokemon_card_ranking_facets_v1(generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id)
      select distinct h_gen,'chase','set',c.set_canonical_key,c.set_name,r.set_id,r.era_id
      from public.pokemon_card_chase_efficiency_rows r
      join (select distinct set_id,set_canonical_key,set_name from public.pokemon_card_collector_appeal_rankings_current_v) c on c.set_id=r.set_id
      where r.snapshot_id=h_snap and r.set_id is not null on conflict do nothing;
    insert into public.pokemon_card_ranking_facets_v1(generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id)
      select h_gen,'chase','rarity',lower(r.canonical_rarity),r.canonical_rarity,null::uuid,null::uuid
      from public.pokemon_card_chase_efficiency_rows r where r.snapshot_id=h_snap and r.canonical_rarity is not null
      group by r.canonical_rarity on conflict do nothing;
  end if;
  return jsonb_build_object('collector_generation_id',c_gen,'chase_generation_id',h_gen,
    'facet_rows',(select count(*) from public.pokemon_card_ranking_facets_v1));
end; $$;
revoke all on function public.refresh_pokemon_card_ranking_facets_v1() from public,anon,authenticated;
grant execute on function public.refresh_pokemon_card_ranking_facets_v1() to service_role;

create view public.pokemon_card_ranking_facets_current_v1 with (security_invoker=true) as
with latest as (
  select distinct on(lens) id,lens,source_authority_id,source_model_version,as_of_date,built_at
  from public.pokemon_card_ranking_facet_generations_v1 order by lens,built_at desc,id desc
)
select g.lens,g.source_authority_id,g.source_model_version,g.as_of_date,
       f.dimension_type,f.facet_key,f.display_name,f.entity_id,f.parent_entity_id
from latest g join public.pokemon_card_ranking_facets_v1 f on f.generation_id=g.id;
revoke all on public.pokemon_card_ranking_facets_current_v1 from public,anon,authenticated;
grant select on public.pokemon_card_ranking_facets_current_v1 to service_role;
