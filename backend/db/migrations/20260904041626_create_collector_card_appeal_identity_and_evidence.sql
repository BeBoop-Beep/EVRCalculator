create schema if not exists private;

create table public.pokemon_collector_entity_reference (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null check (entity_type in ('pokemon','trainer','artist')),
    canonical_key text not null,
    display_name text not null,
    normalized_name text not null,
    pokemon_reference_id bigint null references public.pokemon_reference(id),
    active boolean not null default true,
    identity_metadata_json jsonb not null default '{}'::jsonb check (jsonb_typeof(identity_metadata_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_collector_entity_reference_key_nonblank check (btrim(canonical_key) <> ''),
    constraint pokemon_collector_entity_reference_name_nonblank check (btrim(display_name) <> '' and btrim(normalized_name) <> ''),
    constraint pokemon_collector_entity_reference_pokemon_identity check (
        (entity_type = 'pokemon' and pokemon_reference_id is not null)
        or (entity_type <> 'pokemon' and pokemon_reference_id is null)
    ),
    unique (entity_type, canonical_key)
);
create unique index pokemon_collector_entity_reference_pokemon_ref_uidx
    on public.pokemon_collector_entity_reference(pokemon_reference_id)
    where pokemon_reference_id is not null;
create index pokemon_collector_entity_reference_name_idx
    on public.pokemon_collector_entity_reference(entity_type, normalized_name);
comment on table public.pokemon_collector_entity_reference is
'Collector Card Appeal identity registry. Separate from pokemon_reference so Pokemon, Trainer subjects, and artists can participate without changing Universal Pokemon Desirability.';

create table public.pokemon_card_collector_entity_links (
    id uuid primary key default gen_random_uuid(),
    pokemon_canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
    collector_entity_id uuid not null references public.pokemon_collector_entity_reference(id),
    link_role text not null check (link_role in ('subject','artist')),
    link_position integer not null default 1 check (link_position >= 1),
    link_count integer not null default 1 check (link_count >= 1),
    contribution_weight numeric not null default 1 check (contribution_weight >= 0 and contribution_weight <= 1),
    match_method text not null,
    match_confidence numeric not null default 1 check (match_confidence >= 0 and match_confidence <= 1),
    active boolean not null default true,
    notes text null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_card_collector_entity_links_method_nonblank check (btrim(match_method) <> ''),
    unique (pokemon_canonical_card_id, collector_entity_id, link_role)
);
create index pokemon_card_collector_entity_links_card_idx
    on public.pokemon_card_collector_entity_links(pokemon_canonical_card_id, link_role)
    where active;
create index pokemon_card_collector_entity_links_entity_idx
    on public.pokemon_card_collector_entity_links(collector_entity_id, link_role)
    where active;

create table public.pokemon_card_functional_reference (
    id uuid primary key default gen_random_uuid(),
    functional_key text not null unique,
    display_name text not null,
    normalized_name text not null,
    supertype text null,
    functional_identity_json jsonb not null default '{}'::jsonb check (jsonb_typeof(functional_identity_json) = 'object'),
    active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_card_functional_reference_key_nonblank check (btrim(functional_key) <> ''),
    constraint pokemon_card_functional_reference_name_nonblank check (btrim(display_name) <> '' and btrim(normalized_name) <> '')
);
create index pokemon_card_functional_reference_name_idx
    on public.pokemon_card_functional_reference(normalized_name, supertype);
comment on table public.pokemon_card_functional_reference is
'Functional card identity registry used for playability evidence. It is intentionally separate from collector-subject identities because functionally equivalent printings and collector subjects are different concepts.';

create table public.pokemon_card_functional_links (
    id uuid primary key default gen_random_uuid(),
    pokemon_canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
    functional_reference_id uuid not null references public.pokemon_card_functional_reference(id),
    match_method text not null,
    match_confidence numeric not null default 1 check (match_confidence >= 0 and match_confidence <= 1),
    active boolean not null default true,
    notes text null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_card_functional_links_method_nonblank check (btrim(match_method) <> ''),
    unique (pokemon_canonical_card_id, functional_reference_id)
);
create index pokemon_card_functional_links_card_idx
    on public.pokemon_card_functional_links(pokemon_canonical_card_id)
    where active;
create index pokemon_card_functional_links_function_idx
    on public.pokemon_card_functional_links(functional_reference_id)
    where active;

create table public.pokemon_collector_source_runs (
    id uuid primary key default gen_random_uuid(),
    source_name text not null,
    source_kind text not null check (source_kind in ('fan_ranking','search_interest','playability','reference')),
    run_key text not null,
    capture_version text not null,
    status text not null default 'running' check (status in ('running','success','partial_failure','failed','aborted')),
    source_url text null,
    geo text null,
    anchor_term text null,
    window_start date null,
    window_end date null,
    started_at timestamptz not null default timezone('utc', now()),
    completed_at timestamptz null,
    captured_at timestamptz null,
    source_fingerprint text null,
    item_count integer null check (item_count is null or item_count >= 0),
    raw_payload_json jsonb not null default '{}'::jsonb,
    diagnostics_json jsonb not null default '{}'::jsonb check (jsonb_typeof(diagnostics_json) = 'object'),
    notes text null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_collector_source_runs_name_nonblank check (btrim(source_name) <> '' and btrim(run_key) <> '' and btrim(capture_version) <> ''),
    constraint pokemon_collector_source_runs_window_order check (window_start is null or window_end is null or window_start <= window_end),
    unique (source_name, run_key)
);
create index pokemon_collector_source_runs_source_captured_idx
    on public.pokemon_collector_source_runs(source_name, captured_at desc);
create index pokemon_collector_source_runs_status_idx
    on public.pokemon_collector_source_runs(status, source_kind);
comment on table public.pokemon_collector_source_runs is
'Run-level provenance for Collector Card Appeal evidence. Failed/incomplete evidence is never converted to score zero.';

create table public.pokemon_collector_entity_observations (
    id uuid primary key default gen_random_uuid(),
    source_run_id uuid not null references public.pokemon_collector_source_runs(id),
    collector_entity_id uuid null references public.pokemon_collector_entity_reference(id),
    dimension_key text not null,
    raw_entity_name text not null,
    external_entity_key text null,
    raw_rank integer null check (raw_rank is null or raw_rank >= 1),
    raw_vote_count bigint null check (raw_vote_count is null or raw_vote_count >= 0),
    raw_score numeric null,
    raw_value numeric null,
    normalized_observation_score numeric null check (normalized_observation_score is null or (normalized_observation_score >= 0 and normalized_observation_score <= 100)),
    match_status text not null default 'unmatched' check (match_status in ('matched','unmatched','ambiguous','not_applicable')),
    match_confidence numeric null check (match_confidence is null or (match_confidence >= 0 and match_confidence <= 1)),
    source_detail_url text null,
    raw_row_json jsonb not null default '{}'::jsonb check (jsonb_typeof(raw_row_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_collector_entity_observations_nonblank check (btrim(dimension_key) <> '' and btrim(raw_entity_name) <> ''),
    constraint pokemon_collector_entity_observations_match_consistency check (
        (match_status = 'matched' and collector_entity_id is not null and match_confidence is not null)
        or (match_status <> 'matched')
    )
);
create index pokemon_collector_entity_observations_run_idx
    on public.pokemon_collector_entity_observations(source_run_id, dimension_key);
create index pokemon_collector_entity_observations_entity_idx
    on public.pokemon_collector_entity_observations(collector_entity_id, dimension_key)
    where collector_entity_id is not null;
create unique index pokemon_collector_entity_observations_external_uidx
    on public.pokemon_collector_entity_observations(source_run_id, dimension_key, external_entity_key)
    where external_entity_key is not null;

create table public.pokemon_playability_event_observations (
    id uuid primary key default gen_random_uuid(),
    source_run_id uuid not null references public.pokemon_collector_source_runs(id),
    functional_reference_id uuid null references public.pokemon_card_functional_reference(id),
    raw_card_name text not null,
    event_external_id text not null,
    event_name text null,
    event_date date null,
    format_name text null,
    field_deck_count integer null check (field_deck_count is null or field_deck_count >= 0),
    deck_appearance_count integer null check (deck_appearance_count is null or deck_appearance_count >= 0),
    copy_count integer null check (copy_count is null or copy_count >= 0),
    top_cut_deck_count integer null check (top_cut_deck_count is null or top_cut_deck_count >= 0),
    deck_share numeric null check (deck_share is null or (deck_share >= 0 and deck_share <= 1)),
    top_cut_share numeric null check (top_cut_share is null or (top_cut_share >= 0 and top_cut_share <= 1)),
    weighted_points numeric null,
    match_status text not null default 'unmatched' check (match_status in ('matched','unmatched','ambiguous','not_applicable')),
    match_confidence numeric null check (match_confidence is null or (match_confidence >= 0 and match_confidence <= 1)),
    raw_row_json jsonb not null default '{}'::jsonb check (jsonb_typeof(raw_row_json) = 'object'),
    created_at timestamptz not null default timezone('utc', now()),
    constraint pokemon_playability_event_observations_nonblank check (btrim(raw_card_name) <> '' and btrim(event_external_id) <> ''),
    constraint pokemon_playability_event_observations_match_consistency check (
        (match_status = 'matched' and functional_reference_id is not null and match_confidence is not null)
        or (match_status <> 'matched')
    )
);
create index pokemon_playability_event_observations_run_idx
    on public.pokemon_playability_event_observations(source_run_id, event_date desc);
create index pokemon_playability_event_observations_function_idx
    on public.pokemon_playability_event_observations(functional_reference_id, event_date desc)
    where functional_reference_id is not null;
create unique index pokemon_playability_event_observations_event_function_uidx
    on public.pokemon_playability_event_observations(source_run_id, event_external_id, functional_reference_id)
    where functional_reference_id is not null;

create or replace function private.validate_pokemon_card_collector_entity_link()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare v_type text;
begin
    select e.entity_type into v_type
    from public.pokemon_collector_entity_reference e
    where e.id = new.collector_entity_id;
    if v_type is null then
        raise exception 'collector entity % does not exist', new.collector_entity_id;
    end if;
    if new.link_role = 'artist' and v_type <> 'artist' then
        raise exception 'artist link must target artist entity, got %', v_type;
    end if;
    if new.link_role = 'subject' and v_type not in ('pokemon','trainer') then
        raise exception 'subject link must target pokemon or trainer entity, got %', v_type;
    end if;
    return new;
end;
$$;
create trigger trg_validate_pokemon_card_collector_entity_link
before insert or update on public.pokemon_card_collector_entity_links
for each row execute function private.validate_pokemon_card_collector_entity_link();

create or replace function private.reject_pokemon_collector_appeal_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception '% is append-only; create a new source/model run instead of mutating historical evidence or scores', tg_table_name;
end;
$$;
create trigger trg_pokemon_collector_entity_observations_append_only
before update or delete on public.pokemon_collector_entity_observations
for each row execute function private.reject_pokemon_collector_appeal_mutation();
create trigger trg_pokemon_playability_event_observations_append_only
before update or delete on public.pokemon_playability_event_observations
for each row execute function private.reject_pokemon_collector_appeal_mutation();

alter table public.pokemon_collector_entity_reference enable row level security;
alter table public.pokemon_card_collector_entity_links enable row level security;
alter table public.pokemon_card_functional_reference enable row level security;
alter table public.pokemon_card_functional_links enable row level security;
alter table public.pokemon_collector_source_runs enable row level security;
alter table public.pokemon_collector_entity_observations enable row level security;
alter table public.pokemon_playability_event_observations enable row level security;

revoke all on table public.pokemon_collector_entity_reference, public.pokemon_card_collector_entity_links,
public.pokemon_card_functional_reference, public.pokemon_card_functional_links, public.pokemon_collector_source_runs,
public.pokemon_collector_entity_observations, public.pokemon_playability_event_observations
from public, anon, authenticated, service_role;

grant select, insert, update, delete on table public.pokemon_collector_entity_reference to service_role;
grant select, insert, update, delete on table public.pokemon_card_collector_entity_links to service_role;
grant select, insert, update, delete on table public.pokemon_card_functional_reference to service_role;
grant select, insert, update, delete on table public.pokemon_card_functional_links to service_role;
grant select, insert, update, delete on table public.pokemon_collector_source_runs to service_role;
grant select, insert on table public.pokemon_collector_entity_observations to service_role;
grant select, insert on table public.pokemon_playability_event_observations to service_role;