-- Seal Collector Appeal evidence/output tables to the lifecycle state of their parent run.
-- This prevents late inserts from mutating a completed source capture or a validated/published model.

create or replace function private.require_running_pokemon_collector_source_run()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_status text;
begin
    select status into v_status
    from public.pokemon_collector_source_runs
    where id = new.source_run_id
    for share;

    if not found then
        raise exception 'Collector source run % not found', new.source_run_id;
    end if;

    if v_status <> 'running' then
        raise exception 'Collector evidence may only be inserted while source run % is running; status=%', new.source_run_id, v_status;
    end if;

    return new;
end;
$$;

create or replace function private.require_building_pokemon_collector_appeal_model_run()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_status text;
begin
    select status into v_status
    from public.pokemon_collector_appeal_model_runs
    where id = new.model_run_id
    for share;

    if not found then
        raise exception 'Collector Appeal model run % not found', new.model_run_id;
    end if;

    if v_status <> 'building' then
        raise exception 'Collector Appeal outputs may only be inserted while model run % is building; status=%', new.model_run_id, v_status;
    end if;

    return new;
end;
$$;

create or replace function private.require_published_pokemon_collector_appeal_model_run()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_status text;
begin
    select status into v_status
    from public.pokemon_collector_appeal_model_runs
    where id = new.model_run_id
    for share;

    if not found then
        raise exception 'Collector Appeal model run % not found', new.model_run_id;
    end if;

    if v_status <> 'published' then
        raise exception 'Collector Appeal publication history may only be written for a published model run; run % status=%', new.model_run_id, v_status;
    end if;

    return new;
end;
$$;

-- Evidence can only arrive while its source capture is open.
drop trigger if exists trg_require_running_collector_source_entity_observation on public.pokemon_collector_entity_observations;
create trigger trg_require_running_collector_source_entity_observation
before insert on public.pokemon_collector_entity_observations
for each row execute function private.require_running_pokemon_collector_source_run();

drop trigger if exists trg_require_running_collector_source_playability_observation on public.pokemon_playability_event_observations;
create trigger trg_require_running_collector_source_playability_observation
before insert on public.pokemon_playability_event_observations
for each row execute function private.require_running_pokemon_collector_source_run();

-- Scoring outputs can only arrive while the model run is still building.
drop trigger if exists trg_require_building_collector_model_entity_score on public.pokemon_collector_entity_scores;
create trigger trg_require_building_collector_model_entity_score
before insert on public.pokemon_collector_entity_scores
for each row execute function private.require_building_pokemon_collector_appeal_model_run();

drop trigger if exists trg_require_building_collector_model_playability_score on public.pokemon_playability_scores;
create trigger trg_require_building_collector_model_playability_score
before insert on public.pokemon_playability_scores
for each row execute function private.require_building_pokemon_collector_appeal_model_run();

drop trigger if exists trg_require_building_collector_model_card_score on public.pokemon_card_collector_appeal_scores;
create trigger trg_require_building_collector_model_card_score
before insert on public.pokemon_card_collector_appeal_scores
for each row execute function private.require_building_pokemon_collector_appeal_model_run();

drop trigger if exists trg_require_building_collector_model_set_score on public.pokemon_set_collector_desirability_scores;
create trigger trg_require_building_collector_model_set_score
before insert on public.pokemon_set_collector_desirability_scores
for each row execute function private.require_building_pokemon_collector_appeal_model_run();

-- Publication history is written only by the controlled promotion path.
drop trigger if exists trg_require_published_collector_model_history on public.pokemon_set_collector_appeal_history;
create trigger trg_require_published_collector_model_history
before insert on public.pokemon_set_collector_appeal_history
for each row execute function private.require_published_pokemon_collector_appeal_model_run();

revoke insert on table public.pokemon_set_collector_appeal_history from service_role;
revoke insert on table public.pokemon_set_collector_appeal_history from anon, authenticated;

comment on function private.require_running_pokemon_collector_source_run() is
'Prevents late evidence inserts after a Collector source run is terminal. FOR SHARE serializes inserts against source-run completion.';
comment on function private.require_building_pokemon_collector_appeal_model_run() is
'Prevents late score/output inserts after a Collector Appeal model leaves building state. FOR SHARE serializes inserts against validation/promotion.';
comment on function private.require_published_pokemon_collector_appeal_model_run() is
'Limits Collector Appeal publication-history rows to already-published model runs.';