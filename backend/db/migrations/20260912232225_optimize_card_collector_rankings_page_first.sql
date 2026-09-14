alter table public.pokemon_card_collector_appeal_rankings
  add column set_id uuid references public.sets(id),
  add column card_name text,
  add column rarity text,
  add column subject_policy text,
  add column pokemon_appeal numeric,
  add column trainer_appeal numeric,
  add column artist_appeal numeric,
  add column playability numeric,
  add column treatment_category text,
  add column modeled_pull_probability numeric;

create or replace function public.hydrate_pokemon_card_collector_appeal_rankings(p_model_run_id uuid)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare v_updated integer;
begin
  update public.pokemon_card_collector_appeal_rankings r set
    set_id=s.set_id, card_name=cc.name, rarity=cc.rarity,
    subject_policy=s.subject_policy,
    pokemon_appeal=case when s.subject_policy='pokemon' then s.subject_baseline_score end,
    trainer_appeal=case when s.subject_policy='trainer' then s.subject_baseline_score end,
    artist_appeal=s.artist_recognition_score,
    playability=s.playability_score,
    treatment_category=s.component_inputs_json#>>'{treatmentDiagnostic,treatmentKey}',
    modeled_pull_probability=case
      when coalesce(s.component_inputs_json#>>'{pullScarcityDiagnostic,probability}',
                    s.component_inputs_json#>>'{pullScarcityDiagnostic,modeledProbability}')
           ~ '^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'
      then coalesce(s.component_inputs_json#>>'{pullScarcityDiagnostic,probability}',
                    s.component_inputs_json#>>'{pullScarcityDiagnostic,modeledProbability}')::numeric
    end
  from public.pokemon_card_collector_appeal_scores s
  join public.pokemon_canonical_cards cc on cc.id=s.pokemon_canonical_card_id
  where r.model_run_id=p_model_run_id and s.model_run_id=r.model_run_id
    and s.pokemon_canonical_card_id=r.pokemon_canonical_card_id;
  get diagnostics v_updated=row_count;
  if v_updated <> (select count(*) from public.pokemon_card_collector_appeal_rankings where model_run_id=p_model_run_id)
     or exists(select 1 from public.pokemon_card_collector_appeal_rankings where model_run_id=p_model_run_id and (set_id is null or card_name is null)) then
    raise exception 'card Collector ranking hydration incomplete';
  end if;
  return v_updated;
end $$;
revoke all on function public.hydrate_pokemon_card_collector_appeal_rankings(uuid) from public,anon,authenticated;
grant execute on function public.hydrate_pokemon_card_collector_appeal_rankings(uuid) to service_role;

select public.hydrate_pokemon_card_collector_appeal_rankings(model_run_id)
from public.pokemon_collector_appeal_current where scope='pokemon';

create index pokemon_card_collector_rankings_run_rank_card_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,rank,pokemon_canonical_card_id);
create index pokemon_card_collector_rankings_run_set_rank_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,set_id,rank);
create index pokemon_card_collector_rankings_run_rarity_rank_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,rarity,rank);
create index pokemon_card_collector_rankings_run_pokemon_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,pokemon_appeal desc nulls last,pokemon_canonical_card_id);
create index pokemon_card_collector_rankings_run_trainer_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,trainer_appeal desc nulls last,pokemon_canonical_card_id);
create index pokemon_card_collector_rankings_run_artist_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,artist_appeal desc nulls last,pokemon_canonical_card_id);
create index pokemon_card_collector_rankings_run_playability_idx on public.pokemon_card_collector_appeal_rankings(model_run_id,playability desc nulls last,pokemon_canonical_card_id);
