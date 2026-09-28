
-- Rankings redesign DB Bucket 1 final corrective pass.
-- Additive correction over live 20260928200803/20260928200839 objects.
-- 1) Financial Set->Era identity is canonical sets.era_id only.
-- 2) Daily Financial continuation is per-snapshot, not whole-history.
-- 3) Card facets build automatically from real Collector/Chase pointers.
-- 4) Current facet view binds to actual pointers, never latest built_at.

set local lock_timeout = '3s';
set local statement_timeout = '60s';

create or replace function public.refresh_pokemon_financial_rip_history_snapshot_v1(
  p_source_snapshot_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v4 constant text := 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5';
  c record;
  v_class text;
  v_reason text;
  v_existing record;
  v_pub uuid;
  v_fingerprint text;
  v_bad_map integer;
  v_inserted boolean := false;
begin
  select
    s.id source_snapshot_id,
    s.market_date snapshot_market_date,
    s.financial_rip_version,
    s.cohort_fingerprint,
    s.publication_status,
    count(r.*)::int row_count,
    count(distinct r.set_id)::int set_count,
    count(distinct r.source_market_date)::int source_date_count,
    min(r.source_market_date) source_market_date,
    max(r.source_market_date) max_source_market_date,
    avg(r.financial_rip_score) overall_ref,
    min(r.financial_ranked_cohort_count) min_cohort,
    max(r.financial_ranked_cohort_count) max_cohort
  into c
  from public.pokemon_public_rip_leaderboard_snapshots s
  left join public.pokemon_public_rip_leaderboard_rows r
    on r.snapshot_id = s.id
  where s.id = p_source_snapshot_id
  group by s.id,s.market_date,s.financial_rip_version,s.cohort_fingerprint,s.publication_status;

  if not found then
    raise exception using errcode='22023', message='Financial history source snapshot not found';
  end if;

  if c.financial_rip_version <> v4 then
    v_class := 'INCOMPATIBLE_FINANCIAL_VERSION';
    v_reason := 'financial model is not canonical Financial RIP V4';
  elsif c.publication_status <> 'complete' then
    v_class := 'UNAVAILABLE_INSUFFICIENT_EVIDENCE';
    v_reason := 'leaderboard snapshot is not complete';
  elsif c.row_count <> 22 or c.set_count <> 22
        or c.min_cohort <> 22 or c.max_cohort <> 22 then
    v_class := 'INCOMPLETE_COHORT';
    v_reason := 'canonical 22-Set cohort is incomplete or cohort metadata differs';
  elsif c.source_date_count <> 1
        or c.source_market_date is null
        or c.source_market_date <> c.max_source_market_date then
    v_class := 'AMBIGUOUS_MARKET_DATE_LINEAGE';
    v_reason := 'rows do not resolve to one source market date';
  elsif c.cohort_fingerprint is null then
    v_class := 'UNAVAILABLE_INSUFFICIENT_EVIDENCE';
    v_reason := 'cohort fingerprint missing';
  else
    select count(*) into v_bad_map
    from public.pokemon_public_rip_leaderboard_rows r
    left join public.sets st on st.id = r.set_id
    where r.snapshot_id = p_source_snapshot_id
      and (st.id is null or st.era_id is null);

    if v_bad_map <> 0 then
      v_class := 'UNAVAILABLE_INSUFFICIENT_EVIDENCE';
      v_reason := 'canonical sets.id -> sets.era_id mapping is missing';
    else
      v_class := 'EXACT_PERSISTED_CANONICAL_V4';
      v_reason := 'persisted complete canonical V4 leaderboard cohort with canonical Set/Era identity';
    end if;
  end if;

  insert into public.pokemon_financial_rip_history_candidates_v1(
    source_snapshot_id,snapshot_market_date,source_market_date,financial_model_version,
    set_count,row_count,source_date_count,cohort_fingerprint,overall_financial_rip_reference,
    classification,selected_for_history,classification_reason,observed_at
  ) values (
    c.source_snapshot_id,c.snapshot_market_date,c.source_market_date,c.financial_rip_version,
    c.set_count,c.row_count,c.source_date_count,c.cohort_fingerprint,c.overall_ref,
    v_class,false,v_reason,now()
  )
  on conflict(source_snapshot_id) do update set
    snapshot_market_date=excluded.snapshot_market_date,
    source_market_date=excluded.source_market_date,
    financial_model_version=excluded.financial_model_version,
    set_count=excluded.set_count,
    row_count=excluded.row_count,
    source_date_count=excluded.source_date_count,
    cohort_fingerprint=excluded.cohort_fingerprint,
    overall_financial_rip_reference=excluded.overall_financial_rip_reference,
    classification=excluded.classification,
    classification_reason=excluded.classification_reason,
    observed_at=excluded.observed_at;

  if v_class <> 'EXACT_PERSISTED_CANONICAL_V4' then
    return jsonb_build_object(
      'source_snapshot_id',p_source_snapshot_id,
      'classification',v_class,
      'inserted',false
    );
  end if;

  select md5(string_agg(
    r.set_id::text || ':' || r.financial_rip_score::text || ':' || r.financial_rip_rank::text,
    '|' order by r.set_id::text
  ))
  into v_fingerprint
  from public.pokemon_public_rip_leaderboard_rows r
  where r.snapshot_id = p_source_snapshot_id;

  select *
  into v_existing
  from public.pokemon_financial_rip_history_publications_v1 p
  where p.market_date = c.source_market_date
    and p.financial_model_version = v4;

  if found then
    if v_existing.cohort_fingerprint = c.cohort_fingerprint
       and v_existing.source_row_fingerprint = v_fingerprint
       and abs(v_existing.overall_financial_rip_reference-c.overall_ref) <= 0.00000001
    then
      update public.pokemon_financial_rip_history_candidates_v1
      set selected_for_history = (v_existing.source_snapshot_id = p_source_snapshot_id),
          classification_reason = case
            when v_existing.source_snapshot_id = p_source_snapshot_id
              then 'already published exact semantic market authority'
            else 'exact duplicate semantic market date; existing identical authority retained'
          end
      where source_snapshot_id = p_source_snapshot_id;

      return jsonb_build_object(
        'source_snapshot_id',p_source_snapshot_id,
        'market_date',c.source_market_date,
        'classification','EXACT_PERSISTED_CANONICAL_V4',
        'inserted',false,
        'existing_publication_id',v_existing.id
      );
    end if;

    update public.pokemon_financial_rip_history_candidates_v1
    set selected_for_history=false,
        classification='AMBIGUOUS_MARKET_DATE_LINEAGE',
        classification_reason='conflicting exact candidate exists for semantic source market date'
    where source_snapshot_id=p_source_snapshot_id;

    return jsonb_build_object(
      'source_snapshot_id',p_source_snapshot_id,
      'market_date',c.source_market_date,
      'classification','AMBIGUOUS_MARKET_DATE_LINEAGE',
      'inserted',false
    );
  end if;

  insert into public.pokemon_financial_rip_history_publications_v1(
    market_date,source_snapshot_id,snapshot_market_date,source_market_date,
    financial_model_version,cohort_fingerprint,set_count,overall_financial_rip_reference,
    reconstruction_status,source_row_fingerprint
  ) values (
    c.source_market_date,c.source_snapshot_id,c.snapshot_market_date,c.source_market_date,
    v4,c.cohort_fingerprint,22,c.overall_ref,
    'EXACT_PERSISTED_CANONICAL_V4',v_fingerprint
  )
  returning id into v_pub;

  insert into public.pokemon_financial_rip_history_rows_v1(
    publication_id,market_date,entity_type,entity_id,absolute_financial_rip_score,
    overall_financial_rip_reference,rank,cohort_size,financial_model_version,
    source_snapshot_id,source_market_date,cohort_fingerprint,reconstruction_status
  )
  select
    v_pub,c.source_market_date,'set',r.set_id,r.financial_rip_score,c.overall_ref,
    r.financial_rip_rank,r.financial_ranked_cohort_count,v4,c.source_snapshot_id,
    c.source_market_date,c.cohort_fingerprint,'EXACT_PERSISTED_CANONICAL_V4'
  from public.pokemon_public_rip_leaderboard_rows r
  where r.snapshot_id=c.source_snapshot_id;

  insert into public.pokemon_financial_rip_history_rows_v1(
    publication_id,market_date,entity_type,entity_id,absolute_financial_rip_score,
    overall_financial_rip_reference,rank,cohort_size,financial_model_version,
    source_snapshot_id,source_market_date,cohort_fingerprint,reconstruction_status
  )
  with era_scores as (
    select st.era_id, avg(r.financial_rip_score) score
    from public.pokemon_public_rip_leaderboard_rows r
    join public.sets st on st.id = r.set_id
    where r.snapshot_id = c.source_snapshot_id
    group by st.era_id
  ),
  ranked as (
    select
      era_id,score,
      rank() over(order by score desc,era_id::text)::int era_rank,
      count(*) over()::int era_cohort
    from era_scores
  )
  select
    v_pub,c.source_market_date,'era',era_id,score,c.overall_ref,
    era_rank,era_cohort,v4,c.source_snapshot_id,c.source_market_date,
    c.cohort_fingerprint,'EXACT_PERSISTED_CANONICAL_V4'
  from ranked;

  update public.pokemon_financial_rip_history_candidates_v1
  set selected_for_history=true,
      classification_reason=case
        when c.snapshot_market_date=c.source_market_date
          then 'selected exact persisted canonical V4 authority'
        else 'selected exact persisted canonical V4 authority using semantic source market date'
      end
  where source_snapshot_id=c.source_snapshot_id;

  v_inserted := true;

  return jsonb_build_object(
    'source_snapshot_id',p_source_snapshot_id,
    'publication_id',v_pub,
    'market_date',c.source_market_date,
    'classification','EXACT_PERSISTED_CANONICAL_V4',
    'inserted',v_inserted
  );
end;
$$;

revoke all on function public.refresh_pokemon_financial_rip_history_snapshot_v1(uuid)
  from public,anon,authenticated;
grant execute on function public.refresh_pokemon_financial_rip_history_snapshot_v1(uuid)
  to service_role;

create or replace function public.refresh_pokemon_financial_rip_history_v1()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  s record;
  v_result jsonb;
  v_inserted integer := 0;
begin
  for s in
    select id
    from public.pokemon_public_rip_leaderboard_snapshots
    order by market_date,published_at nulls last,id
  loop
    v_result := public.refresh_pokemon_financial_rip_history_snapshot_v1(s.id);
    if coalesce((v_result->>'inserted')::boolean,false) then
      v_inserted := v_inserted + 1;
    end if;
  end loop;

  return jsonb_build_object(
    'inserted_publications',v_inserted,
    'publication_count',(select count(*) from public.pokemon_financial_rip_history_publications_v1),
    'row_count',(select count(*) from public.pokemon_financial_rip_history_rows_v1)
  );
end;
$$;

revoke all on function public.refresh_pokemon_financial_rip_history_v1()
  from public,anon,authenticated;
grant execute on function public.refresh_pokemon_financial_rip_history_v1()
  to service_role;

create or replace function public.pokemon_financial_rip_history_snapshot_autorefresh_v2()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  perform public.refresh_pokemon_financial_rip_history_snapshot_v1(new.id);
  return null;
end;
$$;

create or replace function public.pokemon_financial_rip_history_rows_autorefresh_v2()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  r record;
begin
  for r in select distinct snapshot_id from new_financial_history_rows
  loop
    perform public.refresh_pokemon_financial_rip_history_snapshot_v1(r.snapshot_id);
  end loop;
  return null;
end;
$$;

revoke all on function public.pokemon_financial_rip_history_snapshot_autorefresh_v2()
  from public,anon,authenticated;
revoke all on function public.pokemon_financial_rip_history_rows_autorefresh_v2()
  from public,anon,authenticated;

drop trigger if exists pokemon_financial_history_snapshot_refresh_v1
  on public.pokemon_public_rip_leaderboard_snapshots;
drop trigger if exists pokemon_financial_history_rows_refresh_v1
  on public.pokemon_public_rip_leaderboard_rows;

create trigger pokemon_financial_history_snapshot_refresh_v2
after insert or update of publication_status
on public.pokemon_public_rip_leaderboard_snapshots
for each row
execute function public.pokemon_financial_rip_history_snapshot_autorefresh_v2();

create trigger pokemon_financial_history_rows_refresh_v2
after insert
on public.pokemon_public_rip_leaderboard_rows
referencing new table as new_financial_history_rows
for each statement
execute function public.pokemon_financial_rip_history_rows_autorefresh_v2();

comment on function public.refresh_pokemon_financial_rip_history_snapshot_v1(uuid) is
  'Incremental exact Financial RIP V4 history publisher for one leaderboard snapshot. Set-to-Era identity is exclusively public.sets.id -> public.sets.era_id; Collector tables are not dependencies.';
comment on function public.refresh_pokemon_financial_rip_history_v1() is
  'Explicit full Financial RIP history reconciliation/backfill. Normal publication triggers call the single-snapshot function instead.';

create or replace function public.refresh_pokemon_collector_card_ranking_facets_v1(
  p_model_run_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_model_version text;
  v_as_of date;
  v_gen uuid;
  v_scored integer;
  v_count integer;
begin
  select model_version,as_of_date
  into v_model_version,v_as_of
  from public.pokemon_collector_appeal_model_runs
  where id=p_model_run_id;

  if not found then
    raise exception using errcode='22023', message='Collector facet source model run not found';
  end if;

  select id into v_gen
  from public.pokemon_card_ranking_facet_generations_v1
  where lens='collector' and source_authority_id=p_model_run_id;

  if found then
    select count(*) into v_count
    from public.pokemon_card_ranking_facets_v1
    where generation_id=v_gen;
    if v_count=0 then
      raise exception using errcode='P0001', message='Existing Collector facet generation is empty';
    end if;
    return jsonb_build_object(
      'generation_id',v_gen,'lens','collector','created',false,'facet_rows',v_count
    );
  end if;

  select count(*) into v_scored
  from public.pokemon_card_collector_appeal_rankings
  where model_run_id=p_model_run_id and status='scored';
  if v_scored=0 then
    raise exception using errcode='22023', message='Collector facet source has no scored ranking rows';
  end if;

  insert into public.pokemon_card_ranking_facet_generations_v1(
    lens,source_authority_id,source_model_version,as_of_date
  )
  values('collector',p_model_run_id,v_model_version,v_as_of)
  returning id into v_gen;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'collector','era',
    coalesce(e.canonical_key,e.id::text),e.name,e.id,null::uuid
  from public.pokemon_card_collector_appeal_rankings r
  join public.sets st on st.id=r.set_id
  join public.eras e on e.id=st.era_id
  where r.model_run_id=p_model_run_id and r.status='scored'
  group by e.id,e.canonical_key,e.name
  on conflict do nothing;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'collector','set',
    coalesce(st.canonical_key,st.id::text),st.name,st.id,st.era_id
  from public.pokemon_card_collector_appeal_rankings r
  join public.sets st on st.id=r.set_id
  where r.model_run_id=p_model_run_id and r.status='scored'
  group by st.id,st.canonical_key,st.name,st.era_id
  on conflict do nothing;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'collector','rarity',lower(r.rarity),min(r.rarity),null::uuid,null::uuid
  from public.pokemon_card_collector_appeal_rankings r
  where r.model_run_id=p_model_run_id and r.status='scored' and r.rarity is not null
  group by lower(r.rarity)
  on conflict do nothing;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'collector','subject_type',
    lower(s.component_inputs_json->>'subjectType'),
    min(s.component_inputs_json->>'subjectType'),
    null::uuid,null::uuid
  from public.pokemon_card_collector_appeal_rankings r
  join public.pokemon_card_collector_appeal_scores s
    on s.model_run_id=r.model_run_id
   and s.pokemon_canonical_card_id=r.pokemon_canonical_card_id
  where r.model_run_id=p_model_run_id
    and r.status='scored'
    and nullif(s.component_inputs_json->>'subjectType','') is not null
  group by lower(s.component_inputs_json->>'subjectType')
  on conflict do nothing;

  select count(*) into v_count
  from public.pokemon_card_ranking_facets_v1
  where generation_id=v_gen;

  if v_count=0 then
    raise exception using errcode='P0001', message='Collector facet generation produced no rows';
  end if;

  return jsonb_build_object(
    'generation_id',v_gen,'lens','collector','created',true,'facet_rows',v_count
  );
end;
$$;

create or replace function public.refresh_pokemon_chase_card_ranking_facets_v1(
  p_snapshot_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_model_version text;
  v_as_of date;
  v_status text;
  v_gen uuid;
  v_rows integer;
  v_count integer;
begin
  select calculation_methodology_version,market_date,publication_status
  into v_model_version,v_as_of,v_status
  from public.pokemon_card_chase_efficiency_snapshots
  where id=p_snapshot_id;

  if not found then
    raise exception using errcode='22023', message='Chase facet source snapshot not found';
  end if;
  if v_status <> 'published' then
    raise exception using errcode='22023', message='Chase facet source snapshot is not published';
  end if;

  select id into v_gen
  from public.pokemon_card_ranking_facet_generations_v1
  where lens='chase' and source_authority_id=p_snapshot_id;

  if found then
    select count(*) into v_count
    from public.pokemon_card_ranking_facets_v1
    where generation_id=v_gen;
    if v_count=0 then
      raise exception using errcode='P0001', message='Existing Chase facet generation is empty';
    end if;
    return jsonb_build_object(
      'generation_id',v_gen,'lens','chase','created',false,'facet_rows',v_count
    );
  end if;

  select count(*) into v_rows
  from public.pokemon_card_chase_efficiency_rows
  where snapshot_id=p_snapshot_id;
  if v_rows=0 then
    raise exception using errcode='22023', message='Chase facet source has no ranking rows';
  end if;

  insert into public.pokemon_card_ranking_facet_generations_v1(
    lens,source_authority_id,source_model_version,as_of_date
  )
  values('chase',p_snapshot_id,v_model_version,v_as_of)
  returning id into v_gen;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'chase','era',
    coalesce(e.canonical_key,e.id::text),e.name,e.id,null::uuid
  from public.pokemon_card_chase_efficiency_rows r
  join public.sets st on st.id=r.set_id
  join public.eras e on e.id=st.era_id
  where r.snapshot_id=p_snapshot_id
  group by e.id,e.canonical_key,e.name
  on conflict do nothing;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'chase','set',
    coalesce(st.canonical_key,st.id::text),st.name,st.id,st.era_id
  from public.pokemon_card_chase_efficiency_rows r
  join public.sets st on st.id=r.set_id
  where r.snapshot_id=p_snapshot_id
  group by st.id,st.canonical_key,st.name,st.era_id
  on conflict do nothing;

  insert into public.pokemon_card_ranking_facets_v1(
    generation_id,lens,dimension_type,facet_key,display_name,entity_id,parent_entity_id
  )
  select
    v_gen,'chase','rarity',
    lower(r.canonical_rarity),min(r.canonical_rarity),null::uuid,null::uuid
  from public.pokemon_card_chase_efficiency_rows r
  where r.snapshot_id=p_snapshot_id and r.canonical_rarity is not null
  group by lower(r.canonical_rarity)
  on conflict do nothing;

  select count(*) into v_count
  from public.pokemon_card_ranking_facets_v1
  where generation_id=v_gen;

  if v_count=0 then
    raise exception using errcode='P0001', message='Chase facet generation produced no rows';
  end if;

  return jsonb_build_object(
    'generation_id',v_gen,'lens','chase','created',true,'facet_rows',v_count
  );
end;
$$;

revoke all on function public.refresh_pokemon_collector_card_ranking_facets_v1(uuid)
  from public,anon,authenticated;
revoke all on function public.refresh_pokemon_chase_card_ranking_facets_v1(uuid)
  from public,anon,authenticated;
grant execute on function public.refresh_pokemon_collector_card_ranking_facets_v1(uuid)
  to service_role;
grant execute on function public.refresh_pokemon_chase_card_ranking_facets_v1(uuid)
  to service_role;

create or replace function public.pokemon_collector_card_ranking_facets_pointer_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.scope='pokemon'
     and (tg_op='INSERT' or old.model_run_id is distinct from new.model_run_id)
  then
    perform public.refresh_pokemon_collector_card_ranking_facets_v1(new.model_run_id);
  end if;
  return null;
end;
$$;

create or replace function public.pokemon_chase_card_ranking_facets_pointer_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_op='INSERT' or old.snapshot_id is distinct from new.snapshot_id then
    perform public.refresh_pokemon_chase_card_ranking_facets_v1(new.snapshot_id);
  end if;
  return null;
end;
$$;

revoke all on function public.pokemon_collector_card_ranking_facets_pointer_v1()
  from public,anon,authenticated;
revoke all on function public.pokemon_chase_card_ranking_facets_pointer_v1()
  from public,anon,authenticated;

drop trigger if exists pokemon_collector_card_ranking_facets_pointer_v1
  on public.pokemon_collector_appeal_current;
create trigger pokemon_collector_card_ranking_facets_pointer_v1
after insert or update of model_run_id
on public.pokemon_collector_appeal_current
for each row
execute function public.pokemon_collector_card_ranking_facets_pointer_v1();

drop trigger if exists pokemon_chase_card_ranking_facets_pointer_v1
  on public.pokemon_card_chase_efficiency_latest;
create trigger pokemon_chase_card_ranking_facets_pointer_v1
after insert or update of snapshot_id
on public.pokemon_card_chase_efficiency_latest
for each row
execute function public.pokemon_chase_card_ranking_facets_pointer_v1();

create or replace function public.refresh_pokemon_card_ranking_facets_v1()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  c record;
  h record;
  c_result jsonb := null;
  h_result jsonb := null;
begin
  select model_run_id into c
  from public.pokemon_collector_appeal_current
  where scope='pokemon';

  if found then
    c_result := public.refresh_pokemon_collector_card_ranking_facets_v1(c.model_run_id);
  end if;

  select snapshot_id into h
  from public.pokemon_card_chase_efficiency_latest
  where contract_version='pokemon-chase-efficiency-v1'
    and calculation_methodology_version='value-times-hit-hazard-over-best-pack-cost-v1'
    and pricing_basis_version='best-verified-pack-equivalent-cost-v1';

  if found then
    h_result := public.refresh_pokemon_chase_card_ranking_facets_v1(h.snapshot_id);
  end if;

  return jsonb_build_object('collector',c_result,'chase',h_result);
end;
$$;

revoke all on function public.refresh_pokemon_card_ranking_facets_v1()
  from public,anon,authenticated;
grant execute on function public.refresh_pokemon_card_ranking_facets_v1()
  to service_role;

create or replace view public.pokemon_card_ranking_facets_current_v1
with (security_invoker=true)
as
with current_sources as (
  select 'collector'::text lens,c.model_run_id source_authority_id
  from public.pokemon_collector_appeal_current c
  where c.scope='pokemon'
  union all
  select 'chase'::text,l.snapshot_id
  from public.pokemon_card_chase_efficiency_latest l
  where l.contract_version='pokemon-chase-efficiency-v1'
    and l.calculation_methodology_version='value-times-hit-hazard-over-best-pack-cost-v1'
    and l.pricing_basis_version='best-verified-pack-equivalent-cost-v1'
)
select
  g.lens,g.source_authority_id,g.source_model_version,g.as_of_date,
  f.dimension_type,f.facet_key,f.display_name,f.entity_id,f.parent_entity_id
from current_sources s
join public.pokemon_card_ranking_facet_generations_v1 g
  on g.lens=s.lens
 and g.source_authority_id=s.source_authority_id
join public.pokemon_card_ranking_facets_v1 f
  on f.generation_id=g.id;

revoke all on public.pokemon_card_ranking_facets_current_v1
  from public,anon,authenticated;
grant select on public.pokemon_card_ranking_facets_current_v1
  to service_role;

comment on view public.pokemon_card_ranking_facets_current_v1 is
  'Current Card Rankings facets bound directly to the actual Collector current model_run_id and canonical Chase latest snapshot_id. built_at never selects current authority.';
comment on function public.refresh_pokemon_collector_card_ranking_facets_v1(uuid) is
  'Idempotently prepares immutable Collector facets for one model run. Pointer trigger runs this in the same transaction as current-authority mutation.';
comment on function public.refresh_pokemon_chase_card_ranking_facets_v1(uuid) is
  'Idempotently prepares immutable Chase facets for one published snapshot. Pointer trigger runs this in the same transaction as latest-authority mutation.';
