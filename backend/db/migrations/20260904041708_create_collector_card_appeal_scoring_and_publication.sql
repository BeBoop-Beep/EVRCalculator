create table public.pokemon_collector_appeal_model_runs (
    id uuid primary key default gen_random_uuid(),
    model_version text not null,
    status text not null default 'building' check (status in ('building','validated','published','failed')),
    as_of_date date not null,
    source_run_ids uuid[] not null default '{}'::uuid[],
    input_fingerprint text not null,
    scoring_config_json jsonb not null default '{}'::jsonb check (jsonb_typeof(scoring_config_json) = 'object'),
    validation_passed boolean not null default false,
    validation_json jsonb not null default '{}'::jsonb check (jsonb_typeof(validation_json) = 'object'),
    diagnostics_json jsonb not null default '{}'::jsonb check (jsonb_typeof(diagnostics_json) = 'object'),
    price_policy text not null default 'excluded' check (price_policy = 'excluded'),
    treatment_policy text not null default 'disabled_v1',
    energy_policy text not null default 'neutral_v1',
    hit_eligibility_policy text not null default 'independent' check (hit_eligibility_policy = 'independent'),
    card_score_count integer null check (card_score_count is null or card_score_count >= 0),
    set_score_count integer null check (set_score_count is null or set_score_count >= 0),
    started_at timestamptz not null default timezone('utc', now()),
    completed_at timestamptz null,
    published_at timestamptz null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_collector_appeal_model_runs_version_nonblank check (btrim(model_version) <> '' and btrim(input_fingerprint) <> ''),
    constraint pokemon_collector_appeal_model_runs_published_state check (status <> 'published' or (validation_passed and published_at is not null)),
    unique (model_version, input_fingerprint)
);
create index pokemon_collector_appeal_model_runs_status_idx
    on public.pokemon_collector_appeal_model_runs(status, as_of_date desc);
create index pokemon_collector_appeal_model_runs_version_idx
    on public.pokemon_collector_appeal_model_runs(model_version, as_of_date desc);
comment on table public.pokemon_collector_appeal_model_runs is
'Immutable-output model-run header for Collector Card Appeal. V1 contract: preserve Universal Pokemon Desirability, allow Pokemon/Trainer/neutral subject baselines, positive-only Artist Recognition and Playability lifts, Treatment disabled, Energy neutral, price excluded, and hit eligibility independent.';

create table public.pokemon_collector_entity_scores (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    collector_entity_id uuid not null references public.pokemon_collector_entity_reference(id),
    collector_entity_score numeric null check (collector_entity_score is null or (collector_entity_score >= 0 and collector_entity_score <= 100)),
    favorite_score numeric null check (favorite_score is null or (favorite_score >= 0 and favorite_score <= 100)),
    cool_score numeric null check (cool_score is null or (cool_score >= 0 and cool_score <= 100)),
    cute_score numeric null check (cute_score is null or (cute_score >= 0 and cute_score <= 100)),
    search_interest_score numeric null check (search_interest_score is null or (search_interest_score >= 0 and search_interest_score <= 100)),
    recognition_score numeric null check (recognition_score is null or (recognition_score >= 0 and recognition_score <= 100)),
    score_status text not null check (score_status in ('scored','insufficient_evidence','not_applicable')),
    confidence text not null default 'insufficient' check (confidence in ('high','medium','low','insufficient')),
    source_run_ids uuid[] not null default '{}'::uuid[],
    score_components_json jsonb not null default '{}'::jsonb check (jsonb_typeof(score_components_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, collector_entity_id),
    constraint pokemon_collector_entity_scores_status_value check (
        (score_status = 'scored' and collector_entity_score is not null)
        or (score_status <> 'scored' and collector_entity_score is null)
    )
);
create index pokemon_collector_entity_scores_entity_idx
    on public.pokemon_collector_entity_scores(collector_entity_id, model_run_id);

create table public.pokemon_playability_scores (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    functional_reference_id uuid not null references public.pokemon_card_functional_reference(id),
    playability_score numeric null check (playability_score is null or (playability_score >= 0 and playability_score <= 100)),
    score_status text not null check (score_status in ('scored','insufficient_evidence','not_applicable')),
    confidence text not null default 'insufficient' check (confidence in ('high','medium','low','insufficient')),
    event_count integer not null default 0 check (event_count >= 0),
    deck_appearance_count integer not null default 0 check (deck_appearance_count >= 0),
    source_run_ids uuid[] not null default '{}'::uuid[],
    score_components_json jsonb not null default '{}'::jsonb check (jsonb_typeof(score_components_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, functional_reference_id),
    constraint pokemon_playability_scores_status_value check (
        (score_status = 'scored' and playability_score is not null)
        or (score_status <> 'scored' and playability_score is null)
    )
);
create index pokemon_playability_scores_function_idx
    on public.pokemon_playability_scores(functional_reference_id, model_run_id);

create table public.pokemon_card_collector_appeal_scores (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    pokemon_canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
    set_id uuid not null references public.sets(id),
    subject_policy text not null check (subject_policy in ('pokemon','trainer','neutral','unsupported')),
    subject_baseline_score numeric null check (subject_baseline_score is null or (subject_baseline_score >= 0 and subject_baseline_score <= 100)),
    artist_recognition_score numeric null check (artist_recognition_score is null or (artist_recognition_score >= 0 and artist_recognition_score <= 100)),
    playability_score numeric null check (playability_score is null or (playability_score >= 0 and playability_score <= 100)),
    artist_lift numeric null check (artist_lift is null or (artist_lift >= 0 and artist_lift <= 1)),
    playability_lift numeric null check (playability_lift is null or (playability_lift >= 0 and playability_lift <= 1)),
    combined_lift numeric null check (combined_lift is null or (combined_lift >= 0 and combined_lift <= 1)),
    collector_card_appeal_score numeric null check (collector_card_appeal_score is null or (collector_card_appeal_score >= 0 and collector_card_appeal_score <= 100)),
    score_status text not null check (score_status in ('scored','neutral','insufficient_evidence','not_applicable','unsupported')),
    confidence text not null default 'insufficient' check (confidence in ('high','medium','low','insufficient')),
    price_input_excluded boolean not null default true check (price_input_excluded),
    treatment_input_excluded boolean not null default true check (treatment_input_excluded),
    hit_eligibility_independent boolean not null default true check (hit_eligibility_independent),
    component_inputs_json jsonb not null default '{}'::jsonb check (jsonb_typeof(component_inputs_json) = 'object'),
    lineage_json jsonb not null default '{}'::jsonb check (jsonb_typeof(lineage_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, pokemon_canonical_card_id),
    constraint pokemon_card_collector_appeal_scores_status_value check (
        (score_status = 'scored' and collector_card_appeal_score is not null)
        or (score_status <> 'scored' and collector_card_appeal_score is null)
    )
);
create index pokemon_card_collector_appeal_scores_card_idx
    on public.pokemon_card_collector_appeal_scores(pokemon_canonical_card_id, model_run_id);
create index pokemon_card_collector_appeal_scores_set_idx
    on public.pokemon_card_collector_appeal_scores(model_run_id, set_id, collector_card_appeal_score desc nulls last);
comment on table public.pokemon_card_collector_appeal_scores is
'Card-level Collector Appeal output. Proposed bounded-headroom formula is model-versioned, not schema-hard-coded. Missing/non-applicable evidence is represented by NULL/status, never score zero. Price is prohibited as an input.';

create table public.pokemon_set_collector_desirability_scores (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    set_id uuid not null references public.sets(id),
    aggregation_version text not null,
    collector_desirability_score numeric not null check (collector_desirability_score >= 0 and collector_desirability_score <= 100),
    collector_desirability_rank integer null check (collector_desirability_rank is null or collector_desirability_rank >= 1),
    eligible_card_count integer not null default 0 check (eligible_card_count >= 0),
    scored_card_count integer not null default 0 check (scored_card_count >= 0),
    neutral_card_count integer not null default 0 check (neutral_card_count >= 0),
    unsupported_card_count integer not null default 0 check (unsupported_card_count >= 0),
    score_coverage_ratio numeric null check (score_coverage_ratio is null or (score_coverage_ratio >= 0 and score_coverage_ratio <= 1)),
    max_card_appeal_score numeric null check (max_card_appeal_score is null or (max_card_appeal_score >= 0 and max_card_appeal_score <= 100)),
    top_3_card_appeal_score numeric null check (top_3_card_appeal_score is null or (top_3_card_appeal_score >= 0 and top_3_card_appeal_score <= 100)),
    top_5_card_appeal_score numeric null check (top_5_card_appeal_score is null or (top_5_card_appeal_score >= 0 and top_5_card_appeal_score <= 100)),
    effective_desirable_card_count numeric null check (effective_desirable_card_count is null or effective_desirable_card_count >= 0),
    subject_rollups_json jsonb not null default '[]'::jsonb check (jsonb_typeof(subject_rollups_json) = 'array'),
    top_cards_json jsonb not null default '[]'::jsonb check (jsonb_typeof(top_cards_json) = 'array'),
    component_inputs_json jsonb not null default '{}'::jsonb check (jsonb_typeof(component_inputs_json) = 'object'),
    diagnostics_json jsonb not null default '{}'::jsonb check (jsonb_typeof(diagnostics_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, set_id),
    constraint pokemon_set_collector_desirability_counts check (scored_card_count + neutral_card_count + unsupported_card_count <= eligible_card_count)
);
create index pokemon_set_collector_desirability_scores_set_idx
    on public.pokemon_set_collector_desirability_scores(set_id, model_run_id);
create index pokemon_set_collector_desirability_scores_rank_idx
    on public.pokemon_set_collector_desirability_scores(model_run_id, collector_desirability_rank)
    where collector_desirability_rank is not null;
comment on table public.pokemon_set_collector_desirability_scores is
'Run-scoped generalized Collector Roster Desirability. It does not replace Universal Set Desirability; it adds Trainer/card-level collector evidence and preserves generalized subject rollups for later Collector Appeal composition.';

create table public.pokemon_set_collector_appeal_history (
    model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
    set_id uuid not null references public.sets(id),
    snapshot_date date not null,
    model_version text not null,
    aggregation_version text not null,
    collector_desirability_score numeric not null check (collector_desirability_score >= 0 and collector_desirability_score <= 100),
    collector_desirability_rank integer null check (collector_desirability_rank is null or collector_desirability_rank >= 1),
    score_coverage_ratio numeric null check (score_coverage_ratio is null or (score_coverage_ratio >= 0 and score_coverage_ratio <= 1)),
    scored_card_count integer not null default 0 check (scored_card_count >= 0),
    published_at timestamptz not null,
    created_at timestamptz not null default timezone('utc', now()),
    primary key (model_run_id, set_id)
);
create index pokemon_set_collector_appeal_history_set_date_idx
    on public.pokemon_set_collector_appeal_history(set_id, snapshot_date desc, published_at desc);
create index pokemon_set_collector_appeal_history_date_rank_idx
    on public.pokemon_set_collector_appeal_history(snapshot_date desc, collector_desirability_rank)
    where collector_desirability_rank is not null;

create table public.pokemon_collector_appeal_current (
    scope text primary key default 'pokemon' check (scope = 'pokemon'),
    model_run_id uuid not null unique references public.pokemon_collector_appeal_model_runs(id),
    model_version text not null,
    as_of_date date not null,
    promoted_at timestamptz not null default timezone('utc', now())
);
comment on table public.pokemon_collector_appeal_current is
'Atomic pointer to the promoted Collector Card Appeal model run. Readers resolve one run from this row to avoid mixed-version card/set data.';

create or replace function private.validate_pokemon_card_collector_appeal_set()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare v_set_id uuid;
begin
    select c.set_id into v_set_id
    from public.pokemon_canonical_cards c
    where c.id = new.pokemon_canonical_card_id;
    if v_set_id is null or v_set_id <> new.set_id then
        raise exception 'collector appeal card/set mismatch for card %', new.pokemon_canonical_card_id;
    end if;
    return new;
end;
$$;
create trigger trg_validate_pokemon_card_collector_appeal_set
before insert or update on public.pokemon_card_collector_appeal_scores
for each row execute function private.validate_pokemon_card_collector_appeal_set();

create trigger trg_pokemon_collector_entity_scores_append_only
before update or delete on public.pokemon_collector_entity_scores
for each row execute function private.reject_pokemon_collector_appeal_mutation();
create trigger trg_pokemon_playability_scores_append_only
before update or delete on public.pokemon_playability_scores
for each row execute function private.reject_pokemon_collector_appeal_mutation();
create trigger trg_pokemon_card_collector_appeal_scores_append_only
before update or delete on public.pokemon_card_collector_appeal_scores
for each row execute function private.reject_pokemon_collector_appeal_mutation();
create trigger trg_pokemon_set_collector_desirability_scores_append_only
before update or delete on public.pokemon_set_collector_desirability_scores
for each row execute function private.reject_pokemon_collector_appeal_mutation();
create trigger trg_pokemon_set_collector_appeal_history_append_only
before update or delete on public.pokemon_set_collector_appeal_history
for each row execute function private.reject_pokemon_collector_appeal_mutation();

create or replace function public.promote_pokemon_collector_appeal_model_run(p_model_run_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_run public.pokemon_collector_appeal_model_runs%rowtype;
    v_card_count integer;
    v_set_count integer;
begin
    select * into v_run
    from public.pokemon_collector_appeal_model_runs
    where id = p_model_run_id
    for update;
    if not found then
        raise exception 'Collector Appeal model run % not found', p_model_run_id;
    end if;
    if v_run.status <> 'validated' or not v_run.validation_passed then
        raise exception 'Collector Appeal model run % is not validated', p_model_run_id;
    end if;
    if cardinality(v_run.source_run_ids) = 0 then
        raise exception 'Collector Appeal model run % has no source-run lineage', p_model_run_id;
    end if;
    if exists (
        select 1
        from unnest(v_run.source_run_ids) as s(source_run_id)
        left join public.pokemon_collector_source_runs r on r.id = s.source_run_id
        where r.id is null or r.status not in ('success','partial_failure')
    ) then
        raise exception 'Collector Appeal model run % references missing/failed source evidence', p_model_run_id;
    end if;
    if v_run.price_policy <> 'excluded' or v_run.hit_eligibility_policy <> 'independent' then
        raise exception 'Collector Appeal model run % violates price/hit-eligibility separation contract', p_model_run_id;
    end if;
    select count(*) into v_card_count from public.pokemon_card_collector_appeal_scores where model_run_id = p_model_run_id;
    select count(*) into v_set_count from public.pokemon_set_collector_desirability_scores where model_run_id = p_model_run_id;
    if v_card_count = 0 or v_set_count = 0 then
        raise exception 'Collector Appeal model run % has incomplete outputs: cards %, sets %', p_model_run_id, v_card_count, v_set_count;
    end if;
    if v_run.card_score_count is not null and v_run.card_score_count <> v_card_count then
        raise exception 'Collector Appeal card-score count mismatch: expected %, found %', v_run.card_score_count, v_card_count;
    end if;
    if v_run.set_score_count is not null and v_run.set_score_count <> v_set_count then
        raise exception 'Collector Appeal set-score count mismatch: expected %, found %', v_run.set_score_count, v_set_count;
    end if;
    update public.pokemon_collector_appeal_model_runs
    set status = 'published', card_score_count = v_card_count, set_score_count = v_set_count,
        completed_at = coalesce(completed_at, timezone('utc', now())),
        published_at = timezone('utc', now()), updated_at = timezone('utc', now())
    where id = p_model_run_id;
    insert into public.pokemon_set_collector_appeal_history (
        model_run_id, set_id, snapshot_date, model_version, aggregation_version,
        collector_desirability_score, collector_desirability_rank, score_coverage_ratio,
        scored_card_count, published_at
    )
    select s.model_run_id, s.set_id, v_run.as_of_date, v_run.model_version, s.aggregation_version,
           s.collector_desirability_score, s.collector_desirability_rank, s.score_coverage_ratio,
           s.scored_card_count, timezone('utc', now())
    from public.pokemon_set_collector_desirability_scores s
    where s.model_run_id = p_model_run_id;
    insert into public.pokemon_collector_appeal_current(scope, model_run_id, model_version, as_of_date, promoted_at)
    values ('pokemon', p_model_run_id, v_run.model_version, v_run.as_of_date, timezone('utc', now()))
    on conflict (scope) do update
    set model_run_id = excluded.model_run_id, model_version = excluded.model_version,
        as_of_date = excluded.as_of_date, promoted_at = excluded.promoted_at;
    return p_model_run_id;
end;
$$;
revoke all on function public.promote_pokemon_collector_appeal_model_run(uuid) from public, anon, authenticated;
grant execute on function public.promote_pokemon_collector_appeal_model_run(uuid) to service_role;

alter table public.pokemon_collector_appeal_model_runs enable row level security;
alter table public.pokemon_collector_entity_scores enable row level security;
alter table public.pokemon_playability_scores enable row level security;
alter table public.pokemon_card_collector_appeal_scores enable row level security;
alter table public.pokemon_collector_appeal_current enable row level security;
alter table public.pokemon_set_collector_desirability_scores enable row level security;
alter table public.pokemon_set_collector_appeal_history enable row level security;

revoke all on table public.pokemon_collector_appeal_model_runs, public.pokemon_collector_entity_scores,
public.pokemon_playability_scores, public.pokemon_card_collector_appeal_scores,
public.pokemon_collector_appeal_current, public.pokemon_set_collector_desirability_scores,
public.pokemon_set_collector_appeal_history from public, anon, authenticated, service_role;

grant select, insert, update on table public.pokemon_collector_appeal_model_runs to service_role;
grant select, insert on table public.pokemon_collector_entity_scores to service_role;
grant select, insert on table public.pokemon_playability_scores to service_role;
grant select, insert on table public.pokemon_card_collector_appeal_scores to service_role;
grant select on table public.pokemon_collector_appeal_current to service_role;
grant select, insert on table public.pokemon_set_collector_desirability_scores to service_role;
grant select, insert on table public.pokemon_set_collector_appeal_history to service_role;