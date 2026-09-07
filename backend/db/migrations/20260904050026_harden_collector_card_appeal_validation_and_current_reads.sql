create or replace function private.collector_json_has_forbidden_price_key(p_value jsonb)
returns boolean
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
    v_key text;
    v_value jsonb;
    v_normalized text;
begin
    if jsonb_typeof(p_value) = 'object' then
        for v_key, v_value in select key, value from jsonb_each(p_value)
        loop
            v_normalized := lower(regexp_replace(v_key, '[^a-z0-9]+', '_', 'g'));
            if v_normalized = any (array[
                'price','card_price','market_price','current_price','near_mint_price',
                'current_near_mint_market_price','sealed_price','product_price','price_used',
                'price_as_of','price_source','tcgplayer_price','set_value','market_value',
                'price_weight','market_price_weight','market_value_weight','set_value_weight'
            ]) then
                return true;
            end if;
            if private.collector_json_has_forbidden_price_key(v_value) then
                return true;
            end if;
        end loop;
    elsif jsonb_typeof(p_value) = 'array' then
        for v_value in select value from jsonb_array_elements(p_value)
        loop
            if private.collector_json_has_forbidden_price_key(v_value) then
                return true;
            end if;
        end loop;
    end if;
    return false;
end;
$$;

alter table public.pokemon_collector_appeal_model_runs
    add constraint pokemon_collector_appeal_model_runs_sources_nonempty
    check (cardinality(source_run_ids) >= 1),
    add constraint pokemon_collector_appeal_model_runs_config_price_free
    check (not private.collector_json_has_forbidden_price_key(scoring_config_json));

alter table public.pokemon_collector_entity_scores
    add constraint pokemon_collector_entity_scores_components_price_free
    check (not private.collector_json_has_forbidden_price_key(score_components_json));

alter table public.pokemon_playability_scores
    add constraint pokemon_playability_scores_components_price_free
    check (not private.collector_json_has_forbidden_price_key(score_components_json));

alter table public.pokemon_card_collector_appeal_scores
    add constraint pokemon_card_collector_appeal_components_price_free
    check (not private.collector_json_has_forbidden_price_key(component_inputs_json)),
    add constraint pokemon_card_collector_appeal_positive_lift_floor
    check (
        score_status <> 'scored'
        or (
            subject_baseline_score is not null
            and combined_lift is not null
            and collector_card_appeal_score is not null
            and collector_card_appeal_score >= subject_baseline_score
        )
    );

alter table public.pokemon_set_collector_desirability_scores
    add constraint pokemon_set_collector_desirability_inputs_price_free
    check (not private.collector_json_has_forbidden_price_key(component_inputs_json));

alter table public.pokemon_collector_source_runs
    add constraint pokemon_collector_source_runs_terminal_completed
    check (status = 'running' or completed_at is not null);

create table public.pokemon_collector_appeal_model_run_sources (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    source_run_id uuid not null references public.pokemon_collector_source_runs(id),
    source_position integer not null check (source_position >= 1),
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, source_run_id),
    unique (model_run_id, source_position)
);
create index pokemon_collector_appeal_model_run_sources_source_idx
    on public.pokemon_collector_appeal_model_run_sources(source_run_id, model_run_id);
comment on table public.pokemon_collector_appeal_model_run_sources is
'Normalized FK-backed lineage for pokemon_collector_appeal_model_runs.source_run_ids. Populated automatically at model-run insert so source evidence cannot be missing or duplicated.';

create or replace function private.sync_pokemon_collector_appeal_model_run_sources()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_position integer;
begin
    for v_position in 1..cardinality(new.source_run_ids)
    loop
        insert into public.pokemon_collector_appeal_model_run_sources(model_run_id, source_run_id, source_position)
        values (new.id, new.source_run_ids[v_position], v_position);
    end loop;
    return new;
end;
$$;

create trigger trg_sync_pokemon_collector_appeal_model_run_sources
after insert on public.pokemon_collector_appeal_model_runs
for each row execute function private.sync_pokemon_collector_appeal_model_run_sources();

create or replace function private.guard_pokemon_collector_source_run_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'Collector source runs are immutable provenance; mark a running run aborted or create a replacement run';
    end if;

    if old.status <> 'running' then
        raise exception 'Terminal Collector source run % is immutable', old.id;
    end if;

    if new.id is distinct from old.id
       or new.source_name is distinct from old.source_name
       or new.source_kind is distinct from old.source_kind
       or new.run_key is distinct from old.run_key
       or new.capture_version is distinct from old.capture_version
       or new.source_url is distinct from old.source_url
       or new.geo is distinct from old.geo
       or new.anchor_term is distinct from old.anchor_term
       or new.window_start is distinct from old.window_start
       or new.window_end is distinct from old.window_end
       or new.started_at is distinct from old.started_at
       or new.created_at is distinct from old.created_at then
        raise exception 'Collector source run identity/provenance fields are immutable after insert';
    end if;

    return new;
end;
$$;

create trigger trg_guard_pokemon_collector_source_run_mutation
before update or delete on public.pokemon_collector_source_runs
for each row execute function private.guard_pokemon_collector_source_run_mutation();

create or replace function private.guard_pokemon_collector_appeal_model_run_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'Collector Appeal model runs are immutable provenance and cannot be deleted';
    end if;

    if old.status in ('published','failed') then
        raise exception 'Terminal Collector Appeal model run % is immutable', old.id;
    end if;

    if new.id is distinct from old.id
       or new.model_version is distinct from old.model_version
       or new.as_of_date is distinct from old.as_of_date
       or new.source_run_ids is distinct from old.source_run_ids
       or new.input_fingerprint is distinct from old.input_fingerprint
       or new.scoring_config_json is distinct from old.scoring_config_json
       or new.price_policy is distinct from old.price_policy
       or new.treatment_policy is distinct from old.treatment_policy
       or new.energy_policy is distinct from old.energy_policy
       or new.hit_eligibility_policy is distinct from old.hit_eligibility_policy
       or new.started_at is distinct from old.started_at
       or new.created_at is distinct from old.created_at then
        raise exception 'Collector Appeal model identity/configuration fields are immutable after insert';
    end if;

    if old.status = 'building' and new.status not in ('building','validated','failed') then
        raise exception 'Invalid Collector Appeal model transition % -> %', old.status, new.status;
    end if;

    if old.status = 'validated' and new.status not in ('validated','published','failed') then
        raise exception 'Invalid Collector Appeal model transition % -> %', old.status, new.status;
    end if;

    return new;
end;
$$;

create trigger trg_guard_pokemon_collector_appeal_model_run_mutation
before update or delete on public.pokemon_collector_appeal_model_runs
for each row execute function private.guard_pokemon_collector_appeal_model_run_mutation();

create or replace function public.validate_pokemon_collector_appeal_model_run(
    p_model_run_id uuid,
    p_diagnostics jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_run public.pokemon_collector_appeal_model_runs%rowtype;
    v_source_count integer;
    v_bad_source_count integer;
    v_card_count integer;
    v_set_count integer;
    v_bad_scored_card_count integer;
    v_card_without_set_count integer;
    v_set_without_card_count integer;
    v_duplicate_rank_count integer;
    v_out_of_range_rank_count integer;
    v_report jsonb;
    v_passed boolean;
begin
    if p_diagnostics is null or jsonb_typeof(p_diagnostics) <> 'object' then
        raise exception 'p_diagnostics must be a JSON object';
    end if;

    select * into v_run
    from public.pokemon_collector_appeal_model_runs
    where id = p_model_run_id
    for update;

    if not found then
        raise exception 'Collector Appeal model run % not found', p_model_run_id;
    end if;

    if v_run.status <> 'building' then
        raise exception 'Collector Appeal model run % must be building to validate; status=%', p_model_run_id, v_run.status;
    end if;

    select count(*) into v_source_count
    from public.pokemon_collector_appeal_model_run_sources
    where model_run_id = p_model_run_id;

    select count(*) into v_bad_source_count
    from public.pokemon_collector_appeal_model_run_sources l
    join public.pokemon_collector_source_runs s on s.id = l.source_run_id
    where l.model_run_id = p_model_run_id
      and s.status not in ('success','partial_failure');

    select count(*) into v_card_count
    from public.pokemon_card_collector_appeal_scores
    where model_run_id = p_model_run_id;

    select count(*) into v_set_count
    from public.pokemon_set_collector_desirability_scores
    where model_run_id = p_model_run_id;

    select count(*) into v_bad_scored_card_count
    from public.pokemon_card_collector_appeal_scores
    where model_run_id = p_model_run_id
      and score_status = 'scored'
      and (
          subject_baseline_score is null
          or combined_lift is null
          or collector_card_appeal_score is null
          or collector_card_appeal_score < subject_baseline_score
      );

    select count(*) into v_card_without_set_count
    from public.pokemon_card_collector_appeal_scores c
    where c.model_run_id = p_model_run_id
      and not exists (
          select 1
          from public.pokemon_set_collector_desirability_scores s
          where s.model_run_id = c.model_run_id
            and s.set_id = c.set_id
      );

    select count(*) into v_set_without_card_count
    from public.pokemon_set_collector_desirability_scores s
    where s.model_run_id = p_model_run_id
      and not exists (
          select 1
          from public.pokemon_card_collector_appeal_scores c
          where c.model_run_id = s.model_run_id
            and c.set_id = s.set_id
      );

    select count(*) into v_duplicate_rank_count
    from (
        select collector_desirability_rank
        from public.pokemon_set_collector_desirability_scores
        where model_run_id = p_model_run_id
          and collector_desirability_rank is not null
        group by collector_desirability_rank
        having count(*) > 1
    ) d;

    select count(*) into v_out_of_range_rank_count
    from public.pokemon_set_collector_desirability_scores
    where model_run_id = p_model_run_id
      and collector_desirability_rank is not null
      and collector_desirability_rank > v_set_count;

    v_passed :=
        v_source_count = cardinality(v_run.source_run_ids)
        and v_bad_source_count = 0
        and v_card_count > 0
        and v_set_count > 0
        and v_bad_scored_card_count = 0
        and v_card_without_set_count = 0
        and v_set_without_card_count = 0
        and v_duplicate_rank_count = 0
        and v_out_of_range_rank_count = 0
        and v_run.price_policy = 'excluded'
        and v_run.hit_eligibility_policy = 'independent'
        and not private.collector_json_has_forbidden_price_key(v_run.scoring_config_json);

    v_report := jsonb_build_object(
        'passed', v_passed,
        'validated_at', timezone('utc', now()),
        'source_count', v_source_count,
        'expected_source_count', cardinality(v_run.source_run_ids),
        'bad_source_count', v_bad_source_count,
        'card_score_count', v_card_count,
        'set_score_count', v_set_count,
        'bad_scored_card_count', v_bad_scored_card_count,
        'card_without_set_count', v_card_without_set_count,
        'set_without_card_count', v_set_without_card_count,
        'duplicate_rank_count', v_duplicate_rank_count,
        'out_of_range_rank_count', v_out_of_range_rank_count,
        'price_policy', v_run.price_policy,
        'hit_eligibility_policy', v_run.hit_eligibility_policy
    );

    update public.pokemon_collector_appeal_model_runs
    set status = case when v_passed then 'validated' else 'failed' end,
        validation_passed = v_passed,
        validation_json = v_report,
        diagnostics_json = diagnostics_json || p_diagnostics,
        card_score_count = v_card_count,
        set_score_count = v_set_count,
        completed_at = timezone('utc', now()),
        updated_at = timezone('utc', now())
    where id = p_model_run_id;

    return v_report;
end;
$$;

create or replace function public.fail_pokemon_collector_appeal_model_run(
    p_model_run_id uuid,
    p_reason text,
    p_diagnostics jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_status text;
begin
    if p_reason is null or btrim(p_reason) = '' then
        raise exception 'Failure reason is required';
    end if;
    if p_diagnostics is null or jsonb_typeof(p_diagnostics) <> 'object' then
        raise exception 'p_diagnostics must be a JSON object';
    end if;

    select status into v_status
    from public.pokemon_collector_appeal_model_runs
    where id = p_model_run_id
    for update;

    if not found then
        raise exception 'Collector Appeal model run % not found', p_model_run_id;
    end if;
    if v_status not in ('building','validated') then
        raise exception 'Collector Appeal model run % cannot fail from status %', p_model_run_id, v_status;
    end if;

    update public.pokemon_collector_appeal_model_runs
    set status = 'failed',
        validation_passed = false,
        validation_json = validation_json || jsonb_build_object('failed_at', timezone('utc', now()), 'failure_reason', p_reason),
        diagnostics_json = diagnostics_json || p_diagnostics,
        completed_at = timezone('utc', now()),
        updated_at = timezone('utc', now())
    where id = p_model_run_id;

    return p_model_run_id;
end;
$$;

revoke update on table public.pokemon_collector_appeal_model_runs from service_role;
revoke delete on table public.pokemon_collector_source_runs from service_role;

alter table public.pokemon_collector_appeal_model_run_sources enable row level security;
revoke all on table public.pokemon_collector_appeal_model_run_sources from public, anon, authenticated, service_role;
grant select on table public.pokemon_collector_appeal_model_run_sources to service_role;

revoke all on function public.validate_pokemon_collector_appeal_model_run(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.validate_pokemon_collector_appeal_model_run(uuid, jsonb) to service_role;
revoke all on function public.fail_pokemon_collector_appeal_model_run(uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.fail_pokemon_collector_appeal_model_run(uuid, text, jsonb) to service_role;

create view public.pokemon_collector_appeal_current_model_v
with (security_invoker = true)
as
select
    c.scope,
    c.model_run_id,
    c.model_version,
    c.as_of_date,
    c.promoted_at,
    r.published_at,
    r.input_fingerprint,
    r.card_score_count,
    r.set_score_count,
    r.price_policy,
    r.treatment_policy,
    r.energy_policy,
    r.hit_eligibility_policy,
    r.validation_json
from public.pokemon_collector_appeal_current c
join public.pokemon_collector_appeal_model_runs r on r.id = c.model_run_id
where r.status = 'published' and r.validation_passed;

create view public.pokemon_card_collector_appeal_current_v
with (security_invoker = true)
as
select
    c.model_run_id,
    cur.model_version,
    cur.as_of_date,
    c.pokemon_canonical_card_id,
    c.set_id,
    c.subject_policy,
    c.subject_baseline_score,
    c.artist_recognition_score,
    c.playability_score,
    c.artist_lift,
    c.playability_lift,
    c.combined_lift,
    c.collector_card_appeal_score,
    c.score_status,
    c.confidence,
    c.component_inputs_json,
    c.lineage_json
from public.pokemon_collector_appeal_current cur
join public.pokemon_card_collector_appeal_scores c on c.model_run_id = cur.model_run_id;

create view public.pokemon_set_collector_desirability_current_v
with (security_invoker = true)
as
select
    s.model_run_id,
    cur.model_version,
    cur.as_of_date,
    s.set_id,
    s.aggregation_version,
    s.collector_desirability_score,
    s.collector_desirability_rank,
    s.eligible_card_count,
    s.scored_card_count,
    s.neutral_card_count,
    s.unsupported_card_count,
    s.score_coverage_ratio,
    s.max_card_appeal_score,
    s.top_3_card_appeal_score,
    s.top_5_card_appeal_score,
    s.effective_desirable_card_count,
    s.subject_rollups_json,
    s.top_cards_json,
    s.component_inputs_json,
    s.diagnostics_json
from public.pokemon_collector_appeal_current cur
join public.pokemon_set_collector_desirability_scores s on s.model_run_id = cur.model_run_id;

revoke all on table public.pokemon_collector_appeal_current_model_v,
    public.pokemon_card_collector_appeal_current_v,
    public.pokemon_set_collector_desirability_current_v
from public, anon, authenticated;
grant select on table public.pokemon_collector_appeal_current_model_v,
    public.pokemon_card_collector_appeal_current_v,
    public.pokemon_set_collector_desirability_current_v
to service_role;