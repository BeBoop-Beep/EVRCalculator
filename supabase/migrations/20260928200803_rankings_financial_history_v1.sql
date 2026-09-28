-- Rankings redesign Bucket 1: exact Financial RIP V4 historical authority.
-- Production-applied migration: rankings_financial_history_v1.
-- Dedicated authority intentionally complements, rather than mutates, full 648-row Benchmark V1 publications.

create table public.pokemon_financial_rip_history_candidates_v1 (
  source_snapshot_id uuid primary key references public.pokemon_public_rip_leaderboard_snapshots(id) on delete restrict,
  snapshot_market_date date not null,
  source_market_date date,
  financial_model_version text not null,
  set_count integer not null,
  row_count integer not null,
  source_date_count integer not null,
  cohort_fingerprint text,
  overall_financial_rip_reference numeric,
  classification text not null check (classification in (
    'EXACT_PERSISTED_CANONICAL_V4','EXACT_RECONSTRUCTABLE_CANONICAL_V4',
    'INCOMPATIBLE_FINANCIAL_VERSION','INCOMPLETE_COHORT',
    'AMBIGUOUS_MARKET_DATE_LINEAGE','UNAVAILABLE_INSUFFICIENT_EVIDENCE'
  )),
  selected_for_history boolean not null default false,
  classification_reason text,
  observed_at timestamptz not null default now()
);

create table public.pokemon_financial_rip_history_publications_v1 (
  id uuid primary key default gen_random_uuid(),
  market_date date not null,
  source_snapshot_id uuid not null unique references public.pokemon_public_rip_leaderboard_snapshots(id) on delete restrict,
  snapshot_market_date date not null,
  source_market_date date not null,
  financial_model_version text not null,
  cohort_fingerprint text not null,
  set_count integer not null check (set_count=22),
  overall_financial_rip_reference numeric not null,
  reconstruction_status text not null check (reconstruction_status in ('EXACT_PERSISTED_CANONICAL_V4','EXACT_RECONSTRUCTABLE_CANONICAL_V4')),
  source_row_fingerprint text not null,
  created_at timestamptz not null default now(),
  unique(market_date,financial_model_version),
  check(market_date=source_market_date)
);

create table public.pokemon_financial_rip_history_rows_v1 (
  publication_id uuid not null references public.pokemon_financial_rip_history_publications_v1(id) on delete restrict,
  market_date date not null,
  entity_type text not null check(entity_type in ('set','era')),
  entity_id uuid not null,
  absolute_financial_rip_score numeric not null,
  overall_financial_rip_reference numeric not null,
  absolute_delta_vs_overall numeric generated always as (absolute_financial_rip_score-overall_financial_rip_reference) stored,
  rank integer not null check(rank>0),
  cohort_size integer not null check(cohort_size>0),
  financial_model_version text not null,
  source_snapshot_id uuid not null,
  source_market_date date not null,
  cohort_fingerprint text not null,
  reconstruction_status text not null check (reconstruction_status in ('EXACT_PERSISTED_CANONICAL_V4','EXACT_RECONSTRUCTABLE_CANONICAL_V4')),
  created_at timestamptz not null default now(),
  primary key(publication_id,entity_type,entity_id),
  check(market_date=source_market_date)
);

create index pokemon_financial_rip_history_rows_lookup_v1 on public.pokemon_financial_rip_history_rows_v1(entity_type,entity_id,market_date,publication_id);
create index pokemon_financial_rip_history_pub_date_v1 on public.pokemon_financial_rip_history_publications_v1(market_date desc);
create index pokemon_financial_rip_history_candidates_class_v1 on public.pokemon_financial_rip_history_candidates_v1(classification,source_market_date);

alter table public.pokemon_financial_rip_history_candidates_v1 enable row level security;
alter table public.pokemon_financial_rip_history_publications_v1 enable row level security;
alter table public.pokemon_financial_rip_history_rows_v1 enable row level security;
revoke all on public.pokemon_financial_rip_history_candidates_v1 from public,anon,authenticated;
revoke all on public.pokemon_financial_rip_history_publications_v1 from public,anon,authenticated;
revoke all on public.pokemon_financial_rip_history_rows_v1 from public,anon,authenticated;
grant select,insert,update on public.pokemon_financial_rip_history_candidates_v1 to service_role;
grant select,insert on public.pokemon_financial_rip_history_publications_v1 to service_role;
grant select,insert on public.pokemon_financial_rip_history_rows_v1 to service_role;
create policy pokemon_financial_history_candidates_service_v1 on public.pokemon_financial_rip_history_candidates_v1 for all to service_role using(true) with check(true);
create policy pokemon_financial_history_publications_service_v1 on public.pokemon_financial_rip_history_publications_v1 for select to service_role using(true);
create policy pokemon_financial_history_publications_insert_service_v1 on public.pokemon_financial_rip_history_publications_v1 for insert to service_role with check(true);
create policy pokemon_financial_history_rows_service_v1 on public.pokemon_financial_rip_history_rows_v1 for select to service_role using(true);
create policy pokemon_financial_history_rows_insert_service_v1 on public.pokemon_financial_rip_history_rows_v1 for insert to service_role with check(true);

create or replace function public.refresh_pokemon_financial_rip_history_v1()
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare
  v4 constant text := 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5';
  c record; v_class text; v_reason text; v_existing uuid; v_pub uuid; v_fingerprint text; v_bad_map integer; v_inserted integer:=0;
begin
  for c in
    select s.id source_snapshot_id,s.market_date snapshot_market_date,s.financial_rip_version,
           s.cohort_fingerprint,s.publication_status,count(r.*)::int row_count,count(distinct r.set_id)::int set_count,
           count(distinct r.source_market_date)::int source_date_count,min(r.source_market_date) source_market_date,
           max(r.source_market_date) max_source_market_date,avg(r.financial_rip_score) overall_ref,
           min(r.financial_ranked_cohort_count) min_cohort,max(r.financial_ranked_cohort_count) max_cohort
    from public.pokemon_public_rip_leaderboard_snapshots s
    left join public.pokemon_public_rip_leaderboard_rows r on r.snapshot_id=s.id
    group by s.id,s.market_date,s.financial_rip_version,s.cohort_fingerprint,s.publication_status
    order by s.market_date,s.published_at nulls last,s.id
  loop
    if c.financial_rip_version<>v4 then v_class:='INCOMPATIBLE_FINANCIAL_VERSION'; v_reason:='financial model is not canonical Financial RIP V4';
    elsif c.publication_status<>'complete' then v_class:='UNAVAILABLE_INSUFFICIENT_EVIDENCE'; v_reason:='leaderboard snapshot is not complete';
    elsif c.row_count<>22 or c.set_count<>22 or c.min_cohort<>22 or c.max_cohort<>22 then v_class:='INCOMPLETE_COHORT'; v_reason:='canonical 22-Set cohort is incomplete or cohort metadata differs';
    elsif c.source_date_count<>1 or c.source_market_date is null or c.source_market_date<>c.max_source_market_date then v_class:='AMBIGUOUS_MARKET_DATE_LINEAGE'; v_reason:='rows do not resolve to one source market date';
    elsif c.cohort_fingerprint is null then v_class:='UNAVAILABLE_INSUFFICIENT_EVIDENCE'; v_reason:='cohort fingerprint missing';
    else v_class:='EXACT_PERSISTED_CANONICAL_V4'; v_reason:='persisted complete canonical V4 leaderboard cohort'; end if;

    insert into public.pokemon_financial_rip_history_candidates_v1
      (source_snapshot_id,snapshot_market_date,source_market_date,financial_model_version,set_count,row_count,source_date_count,cohort_fingerprint,overall_financial_rip_reference,classification,selected_for_history,classification_reason,observed_at)
    values(c.source_snapshot_id,c.snapshot_market_date,c.source_market_date,c.financial_rip_version,c.set_count,c.row_count,c.source_date_count,c.cohort_fingerprint,c.overall_ref,v_class,false,v_reason,now())
    on conflict(source_snapshot_id) do update set snapshot_market_date=excluded.snapshot_market_date,source_market_date=excluded.source_market_date,
      financial_model_version=excluded.financial_model_version,set_count=excluded.set_count,row_count=excluded.row_count,source_date_count=excluded.source_date_count,
      cohort_fingerprint=excluded.cohort_fingerprint,overall_financial_rip_reference=excluded.overall_financial_rip_reference,
      classification=excluded.classification,classification_reason=excluded.classification_reason,observed_at=excluded.observed_at;

    if v_class<>'EXACT_PERSISTED_CANONICAL_V4' then continue; end if;
    select md5(string_agg(r.set_id::text||':'||r.financial_rip_score::text||':'||r.financial_rip_rank::text,'|' order by r.set_id::text))
      into v_fingerprint from public.pokemon_public_rip_leaderboard_rows r where r.snapshot_id=c.source_snapshot_id;
    select p.id into v_existing from public.pokemon_financial_rip_history_publications_v1 p where p.market_date=c.source_market_date and p.financial_model_version=v4;
    if v_existing is not null then
      if exists(select 1 from public.pokemon_financial_rip_history_publications_v1 p where p.id=v_existing and p.cohort_fingerprint=c.cohort_fingerprint
        and p.source_row_fingerprint=v_fingerprint and abs(p.overall_financial_rip_reference-c.overall_ref)<=0.00000001) then
        update public.pokemon_financial_rip_history_candidates_v1 set classification_reason='exact duplicate semantic market date; existing identical authority retained' where source_snapshot_id=c.source_snapshot_id;
      else
        update public.pokemon_financial_rip_history_candidates_v1 set classification='AMBIGUOUS_MARKET_DATE_LINEAGE',classification_reason='conflicting exact candidate exists for semantic source market date' where source_snapshot_id=c.source_snapshot_id;
      end if; continue;
    end if;

    select count(*) into v_bad_map from (
      select r.set_id from public.pokemon_public_rip_leaderboard_rows r
      left join (select set_id,(array_agg(era_id order by era_id::text))[1] era_id,count(distinct era_id) era_count
                 from public.pokemon_card_collector_appeal_rankings_current_v group by set_id) m on m.set_id=r.set_id
      where r.snapshot_id=c.source_snapshot_id and (m.era_id is null or m.era_count<>1)
    ) x;
    if v_bad_map<>0 then
      update public.pokemon_financial_rip_history_candidates_v1 set classification='UNAVAILABLE_INSUFFICIENT_EVIDENCE',
        classification_reason='canonical Set-to-Era identity mapping missing or ambiguous' where source_snapshot_id=c.source_snapshot_id;
      continue;
    end if;

    insert into public.pokemon_financial_rip_history_publications_v1
      (market_date,source_snapshot_id,snapshot_market_date,source_market_date,financial_model_version,cohort_fingerprint,set_count,overall_financial_rip_reference,reconstruction_status,source_row_fingerprint)
    values(c.source_market_date,c.source_snapshot_id,c.snapshot_market_date,c.source_market_date,v4,c.cohort_fingerprint,22,c.overall_ref,'EXACT_PERSISTED_CANONICAL_V4',v_fingerprint)
    returning id into v_pub;

    insert into public.pokemon_financial_rip_history_rows_v1
      (publication_id,market_date,entity_type,entity_id,absolute_financial_rip_score,overall_financial_rip_reference,rank,cohort_size,financial_model_version,source_snapshot_id,source_market_date,cohort_fingerprint,reconstruction_status)
    select v_pub,c.source_market_date,'set',r.set_id,r.financial_rip_score,c.overall_ref,r.financial_rip_rank,r.financial_ranked_cohort_count,
           v4,c.source_snapshot_id,c.source_market_date,c.cohort_fingerprint,'EXACT_PERSISTED_CANONICAL_V4'
    from public.pokemon_public_rip_leaderboard_rows r where r.snapshot_id=c.source_snapshot_id;

    insert into public.pokemon_financial_rip_history_rows_v1
      (publication_id,market_date,entity_type,entity_id,absolute_financial_rip_score,overall_financial_rip_reference,rank,cohort_size,financial_model_version,source_snapshot_id,source_market_date,cohort_fingerprint,reconstruction_status)
    with map as (
      select set_id,(array_agg(era_id order by era_id::text))[1] era_id from public.pokemon_card_collector_appeal_rankings_current_v
      group by set_id having count(distinct era_id)=1
    ), era_scores as (
      select m.era_id,avg(r.financial_rip_score) score from public.pokemon_public_rip_leaderboard_rows r join map m on m.set_id=r.set_id
      where r.snapshot_id=c.source_snapshot_id group by m.era_id
    ), ranked as (
      select era_id,score,rank() over(order by score desc,era_id::text)::int era_rank,count(*) over()::int era_cohort from era_scores
    )
    select v_pub,c.source_market_date,'era',era_id,score,c.overall_ref,era_rank,era_cohort,v4,c.source_snapshot_id,c.source_market_date,
           c.cohort_fingerprint,'EXACT_PERSISTED_CANONICAL_V4' from ranked;

    update public.pokemon_financial_rip_history_candidates_v1 set selected_for_history=true,
      classification_reason=case when c.snapshot_market_date=c.source_market_date then 'selected exact persisted canonical V4 authority'
      else 'selected exact persisted canonical V4 authority using semantic source market date' end
    where source_snapshot_id=c.source_snapshot_id;
    v_inserted:=v_inserted+1;
  end loop;
  return jsonb_build_object('inserted_publications',v_inserted,'publication_count',(select count(*) from public.pokemon_financial_rip_history_publications_v1),
    'row_count',(select count(*) from public.pokemon_financial_rip_history_rows_v1));
end; $$;
revoke all on function public.refresh_pokemon_financial_rip_history_v1() from public,anon,authenticated;
grant execute on function public.refresh_pokemon_financial_rip_history_v1() to service_role;

create or replace function public.pokemon_financial_rip_history_autorefresh_v1()
returns trigger language plpgsql security invoker set search_path=''
as $$ begin perform public.refresh_pokemon_financial_rip_history_v1(); return null; end $$;
revoke all on function public.pokemon_financial_rip_history_autorefresh_v1() from public,anon,authenticated;

create trigger pokemon_financial_history_snapshot_refresh_v1 after insert or update of publication_status
on public.pokemon_public_rip_leaderboard_snapshots for each statement execute function public.pokemon_financial_rip_history_autorefresh_v1();
create trigger pokemon_financial_history_rows_refresh_v1 after insert
on public.pokemon_public_rip_leaderboard_rows for each statement execute function public.pokemon_financial_rip_history_autorefresh_v1();
