begin;

-- Existing Collector constraints call this recursive helper.  Execute it with
-- its owner's private-schema access rather than granting service_role broad
-- USAGE on the private schema.
alter function private.collector_json_has_forbidden_price_key(jsonb) security definer;
alter function private.collector_json_has_forbidden_price_key(jsonb) set search_path='';
revoke all on function private.collector_json_has_forbidden_price_key(jsonb) from public,anon,authenticated;
grant execute on function private.collector_json_has_forbidden_price_key(jsonb) to service_role;

-- The model lifecycle is backend-only, but its existing tables did not carry
-- explicit service-role DML grants in production.
grant select,insert,update on public.pokemon_collector_appeal_model_runs to service_role;
grant select,insert,update,delete on public.pokemon_collector_appeal_model_run_sources to service_role;
grant select,insert,update,delete on public.pokemon_card_collector_appeal_scores to service_role;
grant select,insert,update,delete on public.pokemon_set_collector_desirability_scores to service_role;
grant select on public.pokemon_collector_appeal_current to service_role;
grant select on public.pokemon_set_collector_appeal_history to service_role;

create table public.pokemon_set_collector_appeal_scores (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    set_id uuid not null references public.sets(id),
    collector_roster_desirability_score numeric(12,8) not null check (collector_roster_desirability_score between 0 and 100),
    generalized_desirable_outcome_frequency numeric(14,12) check (generalized_desirable_outcome_frequency between 0 and 1),
    generalized_frequency_status text not null check (generalized_frequency_status in ('available','unavailable')),
    generalized_frequency_status_reason text,
    frequency_index numeric(14,12) check (frequency_index between 0 and 1),
    frequency_modifier_points numeric(12,8) check (frequency_modifier_points between -1 and 2),
    collector_appeal_score numeric(12,8) check (collector_appeal_score between 0 and 100),
    score_status text not null check (score_status in ('scored','unavailable')),
    score_status_reason text,
    collector_appeal_rank integer check (collector_appeal_rank >= 1),
    component_inputs_json jsonb not null default '{}'::jsonb check (jsonb_typeof(component_inputs_json)='object'),
    diagnostics_json jsonb not null default '{}'::jsonb check (jsonb_typeof(diagnostics_json)='object'),
    lineage_json jsonb not null default '{}'::jsonb check (jsonb_typeof(lineage_json)='object'),
    created_at timestamptz not null default timezone('utc',now()),
    primary key (model_run_id,set_id),
    constraint pokemon_set_collector_appeal_state_consistent check (
      (score_status='scored' and generalized_frequency_status='available' and generalized_desirable_outcome_frequency is not null and generalized_frequency_status_reason is null and frequency_index is not null and frequency_modifier_points is not null and collector_appeal_score is not null and score_status_reason is null)
      or
      (score_status='unavailable' and generalized_frequency_status='unavailable' and generalized_desirable_outcome_frequency is null and frequency_index is null and frequency_modifier_points is null and collector_appeal_score is null and generalized_frequency_status_reason is not null and score_status_reason is not null)
    ),
    constraint pokemon_set_collector_appeal_inputs_nonfinancial check (not private.collector_json_has_forbidden_price_key(component_inputs_json))
);
comment on table public.pokemon_set_collector_appeal_scores is 'Run-scoped C5 Collector Appeal state. C4 roster D remains in pokemon_set_collector_desirability_scores; unavailable F is explicit and never zero-filled.';
alter table public.pokemon_set_collector_appeal_scores enable row level security;
revoke all on public.pokemon_set_collector_appeal_scores from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_set_collector_appeal_scores to service_role;
create index pokemon_set_collector_appeal_scores_set_lookup_idx on public.pokemon_set_collector_appeal_scores(set_id,model_run_id);

alter table public.pokemon_set_collector_appeal_history
 add column collector_roster_desirability_score numeric(12,8),
 add column generalized_desirable_outcome_frequency numeric(14,12),
 add column frequency_modifier_points numeric(12,8),
 add column collector_appeal_score numeric(12,8),
 add column collector_appeal_status text,
 add column collector_appeal_status_reason text,
 add column collector_appeal_components_json jsonb,
 add column collector_appeal_lineage_json jsonb;

create or replace function public.validate_pokemon_collector_appeal_model_run(p_model_run_id uuid,p_diagnostics jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.pokemon_collector_appeal_model_runs%rowtype; sources int; bad_sources int; cards int; dsets int; c5sets int; scored int; unavailable int; violations int; dependency_ok boolean; expected jsonb; report jsonb; passed boolean;
begin
 if p_diagnostics is null or jsonb_typeof(p_diagnostics)<>'object' then raise exception 'p_diagnostics must be a JSON object'; end if;
 select * into r from public.pokemon_collector_appeal_model_runs where id=p_model_run_id for update;
 if not found then raise exception 'Collector Appeal model run % not found',p_model_run_id; end if;
 if r.status<>'building' then raise exception 'Collector Appeal model run % must be building to validate; status=%',p_model_run_id,r.status; end if;
 select count(*),count(*) filter(where coalesce(h.usable_for_model,false)=false) into sources,bad_sources from public.pokemon_collector_appeal_model_run_sources l left join public.pokemon_collector_source_run_health_v h on h.source_run_id=l.source_run_id where l.model_run_id=p_model_run_id;
 select count(*) into cards from public.pokemon_card_collector_appeal_scores where model_run_id=p_model_run_id;
 select count(*) into dsets from public.pokemon_set_collector_desirability_scores where model_run_id=p_model_run_id;
 select count(*),count(*) filter(where score_status='scored'),count(*) filter(where score_status='unavailable') into c5sets,scored,unavailable from public.pokemon_set_collector_appeal_scores where model_run_id=p_model_run_id;
 select count(*) into violations from (
  select s.set_id from public.pokemon_set_collector_desirability_scores s full join public.pokemon_set_collector_appeal_scores a on a.model_run_id=s.model_run_id and a.set_id=s.set_id where coalesce(s.model_run_id,a.model_run_id)=p_model_run_id and (s.set_id is null or a.set_id is null)
  union all select set_id from public.pokemon_set_collector_appeal_scores where model_run_id=p_model_run_id and score_status='scored' and (abs(collector_appeal_score-greatest(0,least(100,collector_roster_desirability_score+frequency_modifier_points)))>0.000001 or frequency_modifier_points not between -1 and 2)
  union all select set_id from public.pokemon_set_collector_appeal_scores where model_run_id=p_model_run_id and score_status='unavailable' and score_status_reason is null
  union all select set_id from public.pokemon_set_collector_appeal_scores where model_run_id=p_model_run_id and (lineage_json->>'c3bFingerprint' is distinct from r.scoring_config_json#>>'{dependencies,c3bFingerprint}' or lineage_json->>'c4RosterFingerprint' is distinct from r.scoring_config_json#>>'{dependencies,c4RosterFingerprint}' or lineage_json->>'c4FrequencyFingerprint' is distinct from r.scoring_config_json#>>'{dependencies,c4FrequencyFingerprint}' or lineage_json->>'c5Fingerprint' is distinct from r.scoring_config_json#>>'{dependencies,c5Fingerprint}')
 ) q;
 expected:=coalesce(r.scoring_config_json->'expectedCounts','{}'::jsonb);
 dependency_ok := r.scoring_config_json#>>'{dependencies,c3a5SubjectFingerprint}' is not null and r.scoring_config_json#>>'{dependencies,c3bFingerprint}' is not null and r.scoring_config_json#>>'{dependencies,c4RosterFingerprint}' is not null and r.scoring_config_json#>>'{dependencies,c4FrequencyFingerprint}' is not null and r.scoring_config_json#>>'{dependencies,c5Fingerprint}' is not null and r.scoring_config_json->>'topLevelInputFingerprint'=r.input_fingerprint;
 passed:=sources=cardinality(r.source_run_ids) and bad_sources=0 and cards>0 and dsets>0 and c5sets=dsets and violations=0 and dependency_ok and r.price_policy='excluded' and r.treatment_policy='disabled_v1' and r.hit_eligibility_policy='independent' and not private.collector_json_has_forbidden_price_key(r.scoring_config_json)
  and (not(expected?'cardRows') or cards=(expected->>'cardRows')::int) and (not(expected?'c4Rows') or dsets=(expected->>'c4Rows')::int) and (not(expected?'c5Rows') or c5sets=(expected->>'c5Rows')::int) and (not(expected?'scoredRows') or scored=(expected->>'scoredRows')::int) and (not(expected?'unavailableRows') or unavailable=(expected->>'unavailableRows')::int);
 report:=jsonb_build_object('passed',passed,'validated_at',timezone('utc',now()),'source_count',sources,'expected_source_count',cardinality(r.source_run_ids),'bad_source_count',bad_sources,'card_score_count',cards,'c4_set_count',dsets,'c5_state_count',c5sets,'scored_count',scored,'unavailable_count',unavailable,'state_or_lineage_violations',violations,'dependency_manifest_exact',dependency_ok,'expected_counts',expected);
 update public.pokemon_collector_appeal_model_runs set status=case when passed then 'validated' else 'failed' end,validation_passed=passed,validation_json=report,diagnostics_json=diagnostics_json||p_diagnostics,card_score_count=cards,set_score_count=dsets,completed_at=timezone('utc',now()),updated_at=timezone('utc',now()) where id=p_model_run_id;
 return report;
end$$;

create or replace function public.promote_pokemon_collector_appeal_model_run(p_model_run_id uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare r public.pokemon_collector_appeal_model_runs%rowtype; cards int; dsets int; c5sets int;
begin
 select * into r from public.pokemon_collector_appeal_model_runs where id=p_model_run_id for update;
 if not found then raise exception 'Collector Appeal model run % not found',p_model_run_id; end if;
 if r.status<>'validated' or not r.validation_passed or coalesce((r.validation_json->>'passed')::boolean,false)=false then raise exception 'Collector Appeal model run % is not validated',p_model_run_id; end if;
 select count(*) into cards from public.pokemon_card_collector_appeal_scores where model_run_id=p_model_run_id;
 select count(*) into dsets from public.pokemon_set_collector_desirability_scores where model_run_id=p_model_run_id;
 select count(*) into c5sets from public.pokemon_set_collector_appeal_scores where model_run_id=p_model_run_id;
 if cards=0 or dsets=0 or c5sets<>dsets then raise exception 'Collector Appeal model run % has incomplete outputs: cards %, C4 %, C5 %',p_model_run_id,cards,dsets,c5sets; end if;
 if exists(select 1 from public.pokemon_collector_appeal_model_run_sources l left join public.pokemon_collector_source_run_health_v h on h.source_run_id=l.source_run_id where l.model_run_id=p_model_run_id and coalesce(h.usable_for_model,false)=false) then raise exception 'Collector Appeal model run % references unusable source evidence',p_model_run_id; end if;
 if r.scoring_config_json->>'topLevelInputFingerprint' is distinct from r.input_fingerprint then raise exception 'Collector Appeal model run % dependency manifest differs from input fingerprint',p_model_run_id; end if;
 update public.pokemon_collector_appeal_model_runs set status='published',card_score_count=cards,set_score_count=dsets,completed_at=coalesce(completed_at,timezone('utc',now())),published_at=timezone('utc',now()),updated_at=timezone('utc',now()) where id=p_model_run_id;
 insert into public.pokemon_set_collector_appeal_history(model_run_id,set_id,snapshot_date,model_version,aggregation_version,collector_desirability_score,collector_desirability_rank,score_coverage_ratio,scored_card_count,published_at,collector_roster_desirability_score,generalized_desirable_outcome_frequency,frequency_modifier_points,collector_appeal_score,collector_appeal_status,collector_appeal_status_reason,collector_appeal_components_json,collector_appeal_lineage_json)
 select d.model_run_id,d.set_id,r.as_of_date,r.model_version,d.aggregation_version,d.collector_desirability_score,d.collector_desirability_rank,d.score_coverage_ratio,d.scored_card_count,timezone('utc',now()),a.collector_roster_desirability_score,a.generalized_desirable_outcome_frequency,a.frequency_modifier_points,a.collector_appeal_score,a.score_status,a.score_status_reason,a.component_inputs_json,a.lineage_json from public.pokemon_set_collector_desirability_scores d join public.pokemon_set_collector_appeal_scores a using(model_run_id,set_id) where d.model_run_id=p_model_run_id;
 insert into public.pokemon_collector_appeal_current(scope,model_run_id,model_version,as_of_date,promoted_at) values('pokemon',p_model_run_id,r.model_version,r.as_of_date,timezone('utc',now())) on conflict(scope) do update set model_run_id=excluded.model_run_id,model_version=excluded.model_version,as_of_date=excluded.as_of_date,promoted_at=excluded.promoted_at;
 return p_model_run_id;
end$$;

revoke all on function public.validate_pokemon_collector_appeal_model_run(uuid,jsonb) from public,anon,authenticated;
revoke all on function public.promote_pokemon_collector_appeal_model_run(uuid) from public,anon,authenticated;
grant execute on function public.validate_pokemon_collector_appeal_model_run(uuid,jsonb) to service_role;
grant execute on function public.promote_pokemon_collector_appeal_model_run(uuid) to service_role;

create view public.pokemon_set_collector_appeal_current_v with(security_invoker=true) as
select p.model_run_id,r.model_version,r.as_of_date,a.set_id,d.collector_desirability_score as collector_roster_desirability_score,a.generalized_desirable_outcome_frequency,a.generalized_frequency_status,a.generalized_frequency_status_reason,a.frequency_index,a.frequency_modifier_points,a.collector_appeal_score,a.score_status,a.score_status_reason,a.collector_appeal_rank,a.component_inputs_json,a.diagnostics_json,a.lineage_json
from public.pokemon_collector_appeal_current p join public.pokemon_collector_appeal_model_runs r on r.id=p.model_run_id join public.pokemon_set_collector_desirability_scores d on d.model_run_id=p.model_run_id join public.pokemon_set_collector_appeal_scores a on a.model_run_id=d.model_run_id and a.set_id=d.set_id where p.scope='pokemon';
revoke all on public.pokemon_set_collector_appeal_current_v from public,anon,authenticated;
grant select on public.pokemon_set_collector_appeal_current_v to service_role;

commit;
