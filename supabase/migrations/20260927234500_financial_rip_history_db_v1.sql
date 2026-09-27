-- Financial RIP historical chart authority over certified Benchmark V1 publications.
-- Additive only: no scoring math, model promotion, frontend/API entitlement, or public-table exposure.
set local lock_timeout = '2s';
set local statement_timeout = '30s';

create index if not exists rip_benchmark_financial_history_v1
  on public.pokemon_rip_benchmark_rows_v1
    (entity_type, entity_id, market_date, publication_id)
  include (
    raw_model_value, benchmark_raw_value, raw_delta, rank, cohort_size,
    source_model_version, benchmark_status
  )
  where metric_key = 'financial' and entity_type in ('set','era');

create table if not exists public.pokemon_rip_benchmark_publication_attempts_v1 (
  id uuid primary key,
  market_date date not null check (isfinite(market_date)),
  benchmark_key text not null check (length(benchmark_key) between 1 and 100),
  calibration_version text not null check (length(calibration_version) between 1 and 160),
  candidate_publication_id uuid,
  rankings_publication_id uuid,
  opening_economics_snapshot_id uuid,
  status text not null check (status in ('evaluating','published','failed','deferred')),
  reason_code text not null check (length(reason_code) between 1 and 120),
  reason_detail text check (reason_detail is null or length(reason_detail) <= 2000),
  resulting_publication_id uuid references public.pokemon_rip_benchmark_publications_v1(id),
  attempted_at timestamptz not null default clock_timestamp(),
  completed_at timestamptz,
  diagnostics jsonb not null default '{}'::jsonb
    check (jsonb_typeof(diagnostics) = 'object' and octet_length(diagnostics::text) <= 16384),
  check (
    (status = 'evaluating' and completed_at is null and resulting_publication_id is null)
    or (status = 'published' and completed_at is not null and resulting_publication_id is not null)
    or (status in ('failed','deferred') and completed_at is not null)
  )
);

alter table public.pokemon_rip_benchmark_publication_attempts_v1 enable row level security;

revoke all on table public.pokemon_rip_benchmark_publication_attempts_v1 from public, anon, authenticated;
grant select, insert, update on table public.pokemon_rip_benchmark_publication_attempts_v1 to service_role;

create index if not exists rip_benchmark_attempt_market_date_v1
  on public.pokemon_rip_benchmark_publication_attempts_v1 (market_date desc, attempted_at desc);

create or replace function public.validate_rip_benchmark_financial_authority_v1()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_rankings_payload jsonb;
  v_rankings_updated_at timestamptz;
  v_rankings_publication_id uuid;
  v_rankings_source_date date;
  v_rankings_financial_version text;
  v_rankings_overall_version text;
  v_rankings_set_ids uuid[];
  v_stored_set_ids uuid[];
  v_set_rows integer;
  v_set_available integer;
  v_set_reference_count integer;
  v_set_reference public.rip_benchmark_finite_v1;
  v_set_mean numeric;
  v_set_rank_count integer;
  v_set_min_rank integer;
  v_set_max_rank integer;
  v_set_bad_cohort integer;
  v_set_bad_source integer;
  v_era_rows integer;
  v_era_available integer;
  v_era_reference_count integer;
  v_era_bad_reference integer;
  v_era_rank_count integer;
  v_era_min_rank integer;
  v_era_max_rank integer;
  v_era_bad_cohort integer;
  v_era_bad_source integer;
  v_members integer;
  v_distinct_members integer;
  v_unmatched_members integer;
  v_bad_era_means integer;
  v_bad_era_policy integer;
begin
  if not (old.publication_status = 'staged' and new.publication_status = 'published') then
    return new;
  end if;

  if new.financial_model_version <>
       'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
     or new.overall_model_version <>
       'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
     or new.chase_model_version <> 'chase_accessibility_v1'
     or new.collector_model_version <>
       'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark financial history refuses non-canonical V4/V12/V1/V5 model authority';
  end if;

  if nullif(new.source_manifest->>'model_source_date','')::date is distinct from new.market_date
     or coalesce((new.source_manifest->>'set_count')::integer, -1) <> 22
     or coalesce((new.source_manifest->>'era_count')::integer, -1) <> 2
     or nullif(new.source_manifest->>'rankings_publication_id','') is null
     or nullif(new.source_manifest->>'rankings_updated_at','') is null
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark source manifest is not a complete same-day 22-set/2-era authority';
  end if;

  select ranking_payload_json, updated_at
    into v_rankings_payload, v_rankings_updated_at
  from public.pokemon_explore_rankings_snapshot_latest
  where tcg = 'pokemon' and scope = 'rip-statistics'
  limit 1;

  if not found then
    raise exception using
      errcode = 'P0001',
      message = 'RIP Benchmark same-day Rankings authority is missing';
  end if;

  v_rankings_publication_id :=
    nullif(v_rankings_payload #>> '{meta,snapshot,publicationId}','')::uuid;
  v_rankings_source_date :=
    nullif(v_rankings_payload #>> '{meta,snapshot,simulationSourceMarketDate}','')::date;
  v_rankings_financial_version :=
    v_rankings_payload #>> '{meta,ripWeightsConfig,financialRip,version}';
  v_rankings_overall_version :=
    v_rankings_payload #>> '{meta,ripWeightsConfig,overallRip,version}';

  if v_rankings_publication_id is distinct from
       nullif(new.source_manifest->>'rankings_publication_id','')::uuid
     or v_rankings_source_date is distinct from new.market_date
     or v_rankings_updated_at is distinct from
       nullif(new.source_manifest->>'rankings_updated_at','')::timestamptz
     or v_rankings_financial_version is distinct from new.financial_model_version
     or v_rankings_overall_version is distinct from new.overall_model_version
     or coalesce(
          (v_rankings_payload #>> '{meta,publicAnalyticsCohort,overallRanked,publishable}')::boolean,
          false
        ) is not true
     or coalesce(
          (v_rankings_payload #>> '{meta,publicAnalyticsCohort,overallRanked,rankedSetCount}')::integer,
          -1
        ) <> 22
  then
    raise exception using
      errcode = '40001',
      message = 'RIP Benchmark Rankings authority changed or is not coherent with the candidate';
  end if;

  if new.opening_economics_snapshot_id is null
     or (new.source_manifest->>'opening_economics_snapshot_id')::uuid
          is distinct from new.opening_economics_snapshot_id
     or not exists (
       select 1
       from public.pokemon_rip_stats_snapshots s
       where s.id = new.opening_economics_snapshot_id
         and s.market_date = new.market_date
         and s.publication_status = 'published'
         and s.contract_version = 'pokemon-rip-stats-v3'
     )
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark Opening Economics authority is not exact same-day published V3';
  end if;

  select
    count(*),
    count(*) filter (
      where r.benchmark_status = 'available'
        and r.raw_model_value is not null
        and r.benchmark_raw_value is not null
    ),
    count(distinct r.benchmark_raw_value),
    min(r.benchmark_raw_value),
    avg(r.raw_model_value),
    count(distinct r.rank),
    min(r.rank),
    max(r.rank),
    count(*) filter (where r.cohort_size is distinct from 22),
    count(*) filter (
      where r.source_market_date is distinct from new.market_date
         or r.source_model_version is distinct from new.financial_model_version
    ),
    array_agg(r.entity_id order by r.entity_id)
  into
    v_set_rows, v_set_available, v_set_reference_count, v_set_reference,
    v_set_mean, v_set_rank_count, v_set_min_rank, v_set_max_rank,
    v_set_bad_cohort, v_set_bad_source, v_stored_set_ids
  from public.pokemon_rip_benchmark_rows_v1 r
  where r.publication_id = new.id
    and r.entity_type = 'set'
    and r.metric_key = 'financial';

  if v_set_rows <> 22
     or v_set_available <> 22
     or v_set_reference_count <> 1
     or v_set_reference is distinct from v_set_mean
     or v_set_rank_count <> 22
     or v_set_min_rank <> 1
     or v_set_max_rank <> 22
     or v_set_bad_cohort <> 0
     or v_set_bad_source <> 0
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark Set Financial authority is incomplete or reference-incoherent';
  end if;

  select array_agg((x.value)::uuid order by (x.value)::uuid)
    into v_rankings_set_ids
  from jsonb_array_elements_text(
    v_rankings_payload #> '{meta,publicAnalyticsCohort,overallRanked,rankedSetIds}'
  ) as x(value);

  if v_rankings_set_ids is distinct from v_stored_set_ids then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark Set membership differs from the active Rankings cohort';
  end if;

  select
    count(*),
    count(*) filter (
      where r.benchmark_status = 'available'
        and r.raw_model_value is not null
        and r.benchmark_raw_value is not null
    ),
    count(distinct r.benchmark_raw_value),
    count(*) filter (where r.benchmark_raw_value is distinct from v_set_reference),
    count(distinct r.rank),
    min(r.rank),
    max(r.rank),
    count(*) filter (where r.cohort_size is distinct from 2),
    count(*) filter (
      where r.source_market_date is distinct from new.market_date
         or r.source_model_version is distinct from new.financial_model_version
    )
  into
    v_era_rows, v_era_available, v_era_reference_count, v_era_bad_reference,
    v_era_rank_count, v_era_min_rank, v_era_max_rank,
    v_era_bad_cohort, v_era_bad_source
  from public.pokemon_rip_benchmark_rows_v1 r
  where r.publication_id = new.id
    and r.entity_type = 'era'
    and r.metric_key = 'financial';

  if v_era_rows <> 2
     or v_era_available <> 2
     or v_era_reference_count <> 1
     or v_era_bad_reference <> 0
     or v_era_rank_count <> 2
     or v_era_min_rank <> 1
     or v_era_max_rank <> 2
     or v_era_bad_cohort <> 0
     or v_era_bad_source <> 0
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark Era Financial authority is incomplete or reference-incoherent';
  end if;

  with era_rows as (
    select r.entity_id, r.raw_model_value, r.source_lineage
    from public.pokemon_rip_benchmark_rows_v1 r
    where r.publication_id = new.id
      and r.entity_type = 'era'
      and r.metric_key = 'financial'
  ),
  members as (
    select e.entity_id as era_id, (m.value)::uuid as set_id
    from era_rows e
    cross join lateral jsonb_array_elements_text(e.source_lineage->'member_set_ids') m(value)
  ),
  set_rows as (
    select r.entity_id, r.raw_model_value
    from public.pokemon_rip_benchmark_rows_v1 r
    where r.publication_id = new.id
      and r.entity_type = 'set'
      and r.metric_key = 'financial'
  ),
  per_era as (
    select
      e.entity_id,
      e.raw_model_value,
      count(m.set_id) as member_count,
      count(s.entity_id) as matched_count,
      avg(s.raw_model_value) as member_mean
    from era_rows e
    left join members m on m.era_id = e.entity_id
    left join set_rows s on s.entity_id = m.set_id
    group by e.entity_id, e.raw_model_value
  )
  select
    (select count(*) from members),
    (select count(distinct set_id) from members),
    (select count(*) from members m left join set_rows s on s.entity_id=m.set_id where s.entity_id is null),
    (select count(*) from per_era where member_count <> matched_count or raw_model_value is distinct from member_mean),
    (select count(*) from era_rows
       where source_lineage->>'aggregation' <> 'equal_weight_mean_of_canonical_member_set_raw_scores'
          or source_lineage->>'aggregation_version' <> 'era_rip_aggregation_v1_equal_set_mean')
  into v_members, v_distinct_members, v_unmatched_members, v_bad_era_means, v_bad_era_policy;

  if v_members <> 22
     or v_distinct_members <> 22
     or v_unmatched_members <> 0
     or v_bad_era_means <> 0
     or v_bad_era_policy <> 0
  then
    raise exception using
      errcode = '22023',
      message = 'RIP Benchmark Era aggregation is not an exact partition/equal-set mean of the certified Set cohort';
  end if;

  return new;
end;
$$;

drop trigger if exists validate_rip_benchmark_financial_authority_v1
  on public.pokemon_rip_benchmark_publications_v1;
create trigger validate_rip_benchmark_financial_authority_v1
before update of publication_status on public.pokemon_rip_benchmark_publications_v1
for each row
when (old.publication_status = 'staged' and new.publication_status = 'published')
execute function public.validate_rip_benchmark_financial_authority_v1();

create or replace function public.get_pokemon_financial_rip_history_v1(
  p_entities jsonb,
  p_start_date date,
  p_end_date date,
  p_benchmark_key text default 'pokemon_equal_weight_eligible_sets_v1',
  p_calibration_version text default 'rip_benchmark_v1_fin5_chase10_collector10_overall5'
)
returns table (
  market_date date,
  entity_type text,
  entity_id uuid,
  metric_key text,
  absolute_financial_rip_score public.rip_benchmark_finite_v1,
  overall_financial_rip_reference public.rip_benchmark_finite_v1,
  absolute_delta_vs_overall public.rip_benchmark_finite_v1,
  rank integer,
  cohort_size integer,
  financial_model_version text,
  publication_id uuid,
  status text
)
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_count integer;
  v_distinct_count integer;
begin
  if jsonb_typeof(p_entities) <> 'array' then
    raise exception using errcode='22023', message='p_entities must be a JSON array';
  end if;

  v_count := jsonb_array_length(p_entities);
  if v_count < 1 or v_count > 22 then
    raise exception using errcode='22023', message='p_entities must contain 1..22 Set/Era entities';
  end if;

  if p_start_date is null or p_end_date is null
     or not isfinite(p_start_date) or not isfinite(p_end_date)
     or p_start_date > p_end_date
     or (p_end_date - p_start_date) > 365
  then
    raise exception using errcode='22023', message='history window must be an inclusive range of at most 366 days';
  end if;

  if coalesce(length(btrim(p_benchmark_key)),0) < 1
     or coalesce(length(btrim(p_calibration_version)),0) < 1
  then
    raise exception using errcode='22023', message='benchmark/calibration keys are required';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_entities) e(value)
    where jsonb_typeof(e.value) <> 'object'
       or (e.value - 'entity_type' - 'entity_id') <> '{}'::jsonb
       or e.value->>'entity_type' not in ('set','era')
       or nullif(e.value->>'entity_id','') is null
  ) then
    raise exception using errcode='22023', message='each entity must contain only entity_type=set|era and entity_id';
  end if;

  begin
    select count(distinct (e.value->>'entity_type', (e.value->>'entity_id')::uuid))
      into v_distinct_count
    from jsonb_array_elements(p_entities) e(value);
  exception when invalid_text_representation then
    raise exception using errcode='22023', message='entity_id must be a UUID';
  end;

  if v_distinct_count <> v_count then
    raise exception using errcode='22023', message='duplicate entities are not allowed';
  end if;

  return query
  with requested as (
    select
      e.value->>'entity_type' as entity_type,
      (e.value->>'entity_id')::uuid as entity_id
    from jsonb_array_elements(p_entities) e(value)
  )
  select
    r.market_date,
    r.entity_type,
    r.entity_id,
    r.metric_key,
    r.raw_model_value,
    r.benchmark_raw_value,
    r.raw_delta,
    r.rank,
    r.cohort_size,
    r.source_model_version,
    r.publication_id,
    r.benchmark_status
  from requested q
  join public.pokemon_rip_benchmark_rows_v1 r
    on r.entity_type = q.entity_type
   and r.entity_id = q.entity_id
   and r.metric_key = 'financial'
   and r.market_date between p_start_date and p_end_date
  join public.pokemon_rip_benchmark_publications_v1 p
    on p.id = r.publication_id
   and p.publication_status = 'published'
   and p.benchmark_key = p_benchmark_key
   and p.calibration_version = p_calibration_version
  order by r.market_date, r.entity_type, r.entity_id;
end;
$$;

revoke all on function public.validate_rip_benchmark_financial_authority_v1() from public, anon, authenticated;
revoke all on function public.get_pokemon_financial_rip_history_v1(jsonb,date,date,text,text)
  from public, anon, authenticated;
grant execute on function public.get_pokemon_financial_rip_history_v1(jsonb,date,date,text,text)
  to service_role;

comment on function public.get_pokemon_financial_rip_history_v1(jsonb,date,date,text,text) is
  'Backend-only bounded Financial RIP V4 Set/Era history. raw_model_value is the absolute score; benchmark_raw_value is the exact frozen same-publication equal-Set Pokemon-wide Financial RIP reference; raw_delta is their difference. No simulation or JSON source scan occurs on reads.';
comment on function public.validate_rip_benchmark_financial_authority_v1() is
  'Final staged->published guard: refuses mixed Rankings/model dates, non-canonical V4/V12 authority, incomplete 22-Set/2-Era cohorts, incorrect Overall Financial references, or non-deterministic era aggregation.';
comment on table public.pokemon_rip_benchmark_publication_attempts_v1 is
  'Backend-only durable receipts for Benchmark publication attempts; failures do not mutate the prior published Benchmark authority.';
