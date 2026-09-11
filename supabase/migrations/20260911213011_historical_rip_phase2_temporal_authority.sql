-- Phase 2: independently versioned, append-only RIP temporal authority.
create table if not exists public.pokemon_rip_temporal_history (
    domain text not null check (domain in ('collector','financial','chase','overall')),
    entity_type text not null check (entity_type in ('set','sealed_product')),
    entity_id uuid not null,
    set_id uuid not null references public.sets(id),
    as_of_date date not null,
    model_version text not null,
    score numeric null check (score is null or score between 0 and 100),
    rank integer null check (rank is null or rank > 0),
    quality_status text not null check (quality_status in (
        'READY','PARTIAL','UNAVAILABLE','RECONSTRUCTED_VALIDATED','BLOCKED_SOURCE_GAP'
    )),
    reconstruction_status text not null,
    source_result_id uuid null,
    calculation_run_id uuid null,
    model_run_id uuid null references public.pokemon_collector_appeal_model_runs(id),
    model_fingerprint text not null,
    cohort_fingerprint text not null,
    source_lineage jsonb not null default '{}'::jsonb,
    effective_from date null,
    effective_until date null,
    created_at timestamptz not null default timezone('utc', now()),
    primary key (domain, entity_type, entity_id, as_of_date, model_version, model_fingerprint)
);

create unique index if not exists pokemon_rip_temporal_history_source_result_uq
on public.pokemon_rip_temporal_history(domain, source_result_id)
where source_result_id is not null;
create index if not exists pokemon_rip_temporal_history_set_domain_date_idx
on public.pokemon_rip_temporal_history(set_id, domain, as_of_date desc);

create or replace function private.reject_pokemon_rip_temporal_history_mutation()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin raise exception 'pokemon_rip_temporal_history is append-only'; end; $$;
drop trigger if exists trg_pokemon_rip_temporal_history_append_only on public.pokemon_rip_temporal_history;
create trigger trg_pokemon_rip_temporal_history_append_only before update or delete
on public.pokemon_rip_temporal_history for each row
execute function private.reject_pokemon_rip_temporal_history_mutation();

alter table public.pokemon_rip_temporal_history enable row level security;
revoke all on table public.pokemon_rip_temporal_history from public, anon, authenticated, service_role;
grant select, insert on table public.pokemon_rip_temporal_history to service_role;

-- Exact existing Collector V7 authority. Unavailable rows intentionally retain NULL scores.
insert into public.pokemon_rip_temporal_history (
    domain, entity_type, entity_id, set_id, as_of_date, model_version, score, rank,
    quality_status, reconstruction_status, model_run_id, model_fingerprint,
    cohort_fingerprint, source_lineage, effective_from, effective_until
)
select 'collector', 'set', h.set_id, h.set_id, h.snapshot_date, h.model_version,
       h.collector_appeal_score, h.collector_desirability_rank,
       case when h.collector_appeal_status = 'scored' then 'READY' else 'UNAVAILABLE' end,
       'LIVE_OBSERVATION', h.model_run_id, m.input_fingerprint,
       encode(extensions.digest((select string_agg(x.set_id::text, ',' order by x.set_id)
                      from public.pokemon_set_collector_appeal_history x
                      where x.model_run_id=h.model_run_id), 'sha256'), 'hex'),
       jsonb_build_object('sourceRunIds', m.source_run_ids,
                          'collectorAppealStatus', h.collector_appeal_status,
                          'collectorAppealStatusReason', h.collector_appeal_status_reason),
       h.snapshot_date, null
from public.pokemon_set_collector_appeal_history h
join public.pokemon_collector_appeal_model_runs m on m.id = h.model_run_id
where h.model_version = 'pokemon_collector_appeal_v7_expanded_price_blind_v1'
on conflict do nothing;

-- Preserve every exact product/run observation; same-day reruns remain distinct via fingerprint.
insert into public.pokemon_rip_temporal_history (
    domain, entity_type, entity_id, set_id, as_of_date, model_version, score,
    quality_status, reconstruction_status, source_result_id, calculation_run_id,
    model_fingerprint, cohort_fingerprint, source_lineage, effective_from, effective_until
)
select 'financial', 'sealed_product', r.sealed_product_id, r.set_id, r.price_as_of,
       r.financial_rip_v4_version, r.financial_rip_v4_score,
       case when r.financial_rip_v4_status = 'ready' then 'READY' else 'UNAVAILABLE' end,
       'PERSISTED_EXACT', r.id, r.calculation_run_id,
       encode(extensions.digest(r.financial_rip_v4_payload::text, 'sha256'), 'hex'),
       encode(extensions.digest((select string_agg(x.set_id::text || ':' || x.sealed_product_id::text, ','
                                        order by x.set_id, x.sealed_product_id)
                      from public.simulation_sealed_product_results x
                      where x.price_as_of=r.price_as_of and x.calculation_run_id=r.calculation_run_id),
                     'sha256'), 'hex'),
       jsonb_build_object('priceAsOf', r.price_as_of, 'priceSource', r.price_source,
                          'productMarketCost', r.product_market_cost,
                          'payload', r.financial_rip_v4_payload), r.price_as_of, r.price_as_of
from public.simulation_sealed_product_results r
where r.financial_rip_v4_version = 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
  and r.price_as_of is not null
on conflict do nothing;

insert into public.pokemon_rip_temporal_history (
    domain, entity_type, entity_id, set_id, as_of_date, model_version, score,
    quality_status, reconstruction_status, source_result_id, calculation_run_id,
    model_fingerprint, cohort_fingerprint, source_lineage, effective_from, effective_until
)
select 'overall', 'sealed_product', r.sealed_product_id, r.set_id, r.price_as_of,
       r.overall_rip_v12_version, r.overall_rip_v12_score,
       case when r.overall_rip_v12_status = 'ready' then 'READY' else 'UNAVAILABLE' end,
       'PERSISTED_EXACT', r.id, r.calculation_run_id,
       encode(extensions.digest(r.overall_rip_v12_payload::text, 'sha256'), 'hex'),
       encode(extensions.digest((select string_agg(x.set_id::text || ':' || x.sealed_product_id::text, ','
                                        order by x.set_id, x.sealed_product_id)
                      from public.simulation_sealed_product_results x
                      where x.price_as_of=r.price_as_of and x.calculation_run_id=r.calculation_run_id),
                     'sha256'), 'hex'),
       jsonb_build_object('financialVersion', r.financial_rip_v4_version,
                          'collectorVersion', r.collector_appeal_version,
                          'payload', r.overall_rip_v12_payload), r.price_as_of, r.price_as_of
from public.simulation_sealed_product_results r
where r.overall_rip_v12_version = 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
  and r.price_as_of is not null
on conflict do nothing;

create or replace function public.append_current_collector_v7_history(p_as_of_date date)
returns integer language plpgsql security definer set search_path = '' as $$
declare v_run public.pokemon_collector_appeal_model_runs%rowtype; v_count integer; v_cohort text;
begin
  select m.* into strict v_run from public.pokemon_collector_appeal_current c
  join public.pokemon_collector_appeal_model_runs m on m.id=c.model_run_id where c.scope='pokemon';
  if v_run.model_version <> 'pokemon_collector_appeal_v7_expanded_price_blind_v1' then
    raise exception 'current Collector authority is not frozen V7';
  end if;
  if p_as_of_date < v_run.as_of_date then raise exception 'as-of date predates model authority'; end if;
  if exists (select 1 from unnest(v_run.source_run_ids) x(id) join public.pokemon_collector_source_runs s on s.id=x.id
             where s.captured_at::date > p_as_of_date) then raise exception 'future source evidence'; end if;
  select encode(extensions.digest(string_agg(s.set_id::text, ',' order by s.set_id),'sha256'),'hex') into v_cohort
  from public.pokemon_set_collector_appeal_scores s where s.model_run_id=v_run.id;
  insert into public.pokemon_rip_temporal_history(
    domain,entity_type,entity_id,set_id,as_of_date,model_version,score,rank,quality_status,
    reconstruction_status,model_run_id,model_fingerprint,cohort_fingerprint,source_lineage,
    effective_from,effective_until)
  select 'collector','set',s.set_id,s.set_id,p_as_of_date,v_run.model_version,
    s.collector_appeal_score,s.collector_appeal_rank,
    case when s.score_status='scored' then 'READY' else 'UNAVAILABLE' end,
    'LIVE_OBSERVATION',v_run.id,v_run.input_fingerprint,v_cohort,
    jsonb_build_object('sourceRunIds',v_run.source_run_ids,'sourceObservationDates',
      (select jsonb_object_agg(x.id::text, sr.captured_at::date) from unnest(v_run.source_run_ids) x(id)
       join public.pokemon_collector_source_runs sr on sr.id=x.id)),
    p_as_of_date,null
  from public.pokemon_set_collector_appeal_scores s where s.model_run_id=v_run.id
  on conflict do nothing;
  get diagnostics v_count = row_count; return v_count;
end $$;
revoke all on function public.append_current_collector_v7_history(date) from public,anon,authenticated;
grant execute on function public.append_current_collector_v7_history(date) to service_role;
