begin;

drop view public.pokemon_set_collector_appeal_current_v;
create view public.pokemon_set_collector_appeal_current_v
with (security_invoker=true) as
select p.model_run_id,r.model_version,r.as_of_date,a.set_id,
 d.collector_desirability_score as collector_roster_desirability_score,
 d.collector_desirability_rank as collector_roster_desirability_rank,
 d.eligible_card_count,d.scored_card_count,d.neutral_card_count,d.unsupported_card_count,
 d.score_coverage_ratio,d.subject_rollups_json,d.diagnostics_json as roster_diagnostics_json,
 a.generalized_desirable_outcome_frequency,a.generalized_frequency_status,
 a.generalized_frequency_status_reason,a.frequency_index,a.frequency_modifier_points,
 a.collector_appeal_score,a.score_status,a.score_status_reason,a.collector_appeal_rank,
 a.component_inputs_json,a.diagnostics_json,a.lineage_json
from public.pokemon_collector_appeal_current p
join public.pokemon_collector_appeal_model_runs r on r.id=p.model_run_id
join public.pokemon_set_collector_desirability_scores d on d.model_run_id=p.model_run_id
join public.pokemon_set_collector_appeal_scores a on a.model_run_id=d.model_run_id and a.set_id=d.set_id
where p.scope='pokemon';
revoke all on public.pokemon_set_collector_appeal_current_v from public,anon,authenticated;
grant select on public.pokemon_set_collector_appeal_current_v to service_role;

create or replace function public.select_pokemon_collector_appeal_current(p_model_run_id uuid default null)
returns uuid language plpgsql security definer set search_path='' as $$
declare r public.pokemon_collector_appeal_model_runs%rowtype;
begin
 if p_model_run_id is null then
  delete from public.pokemon_collector_appeal_current where scope='pokemon';
  return null;
 end if;
 select * into r from public.pokemon_collector_appeal_model_runs where id=p_model_run_id;
 if not found or r.status<>'published' or r.published_at is null then
  raise exception 'Collector Appeal rollback target % is not a published model',p_model_run_id;
 end if;
 insert into public.pokemon_collector_appeal_current(scope,model_run_id,model_version,as_of_date,promoted_at)
 values('pokemon',r.id,r.model_version,r.as_of_date,timezone('utc',now()))
 on conflict(scope) do update set model_run_id=excluded.model_run_id,model_version=excluded.model_version,as_of_date=excluded.as_of_date,promoted_at=excluded.promoted_at;
 return r.id;
end $$;
revoke all on function public.select_pokemon_collector_appeal_current(uuid) from public,anon,authenticated;
grant execute on function public.select_pokemon_collector_appeal_current(uuid) to service_role;

commit;
