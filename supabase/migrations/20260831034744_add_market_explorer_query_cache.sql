-- Backend-only shared cache for normalized Market Explorer results.
-- This migration is deployment-ready but intentionally not applied by Effort 1H.

create table if not exists public.pokemon_market_explorer_query_cache (
    id uuid primary key default gen_random_uuid(),
    query_fingerprint text not null unique,
    query_contract_version text not null,
    service_version text not null,
    instrument_methodology_version text not null,
    asset text not null check (asset in ('cards', 'sealed')),
    normalized_spec jsonb not null,
    cache_kind text not null default 'custom'
        check (cache_kind in ('custom', 'maintained', 'prepared')),
    status text not null check (status in ('building', 'ready', 'stale', 'failed')),
    computed_from date,
    computed_through date,
    series_payload jsonb,
    current_value numeric,
    constituent_count bigint,
    eligible_universe_count bigint,
    current_constituents jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_built_at timestamptz,
    build_token uuid,
    build_started_at timestamptz,
    build_expires_at timestamptz,
    request_count bigint not null default 0,
    last_requested_at timestamptz,
    constraint pokemon_market_explorer_query_cache_dates_valid
        check (computed_from is null or computed_through is null or computed_from <= computed_through),
    constraint pokemon_market_explorer_query_cache_ready_payload
        check (status <> 'ready' or (computed_through is not null and series_payload is not null)),
    constraint pokemon_market_explorer_query_cache_build_lease
        check (
            status <> 'building'
            or (build_token is not null and build_started_at is not null and build_expires_at is not null)
        )
);

comment on table public.pokemon_market_explorer_query_cache is
    'Service-only L2 cache for versioned normalized Market Explorer queries; not source authority.';
comment on column public.pokemon_market_explorer_query_cache.computed_through is
    'Semantic freshness watermark; updated_at must never be used as publication freshness.';
comment on column public.pokemon_market_explorer_query_cache.cache_kind is
    'Allows future custom-to-maintained/prepared promotion without changing identity.';

create index if not exists idx_pokemon_market_explorer_query_cache_status_freshness
    on public.pokemon_market_explorer_query_cache (status, computed_through);
create index if not exists idx_pokemon_market_explorer_query_cache_retention
    on public.pokemon_market_explorer_query_cache (cache_kind, last_requested_at, updated_at);

alter table public.pokemon_market_explorer_query_cache enable row level security;

revoke all on table public.pokemon_market_explorer_query_cache
    from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.pokemon_market_explorer_query_cache
    to service_role;

-- Two non-sensitive counters let every API worker detect a historical repair
-- without clearing another process's memory. Normal publication dates remain
-- sourced from the canonical Cards/Sealed publication tables.
create table if not exists public.pokemon_market_explorer_cache_state (
    asset text primary key check (asset in ('cards', 'sealed')),
    repair_generation bigint not null default 0 check (repair_generation >= 0),
    updated_at timestamptz not null default now()
);

insert into public.pokemon_market_explorer_cache_state (asset)
values ('cards'), ('sealed')
on conflict (asset) do nothing;

alter table public.pokemon_market_explorer_cache_state enable row level security;
revoke all on table public.pokemon_market_explorer_cache_state
    from public, anon, authenticated, service_role;
grant select, update on table public.pokemon_market_explorer_cache_state
    to service_role;

comment on table public.pokemon_market_explorer_cache_state is
    'Service-only cross-worker repair generations; contains no market intelligence.';

create or replace function public.claim_pokemon_market_explorer_query_cache_build(
    p_query_fingerprint text,
    p_query_contract_version text,
    p_service_version text,
    p_instrument_methodology_version text,
    p_asset text,
    p_normalized_spec jsonb,
    p_build_token uuid,
    p_lease_seconds integer default 30
) returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    claimed_fingerprint text;
begin
    if p_query_fingerprint is null or length(p_query_fingerprint) <> 64
       or p_build_token is null or p_lease_seconds < 1 or p_lease_seconds > 300 then
        return false;
    end if;

    insert into public.pokemon_market_explorer_query_cache (
        query_fingerprint, query_contract_version, service_version,
        instrument_methodology_version, asset, normalized_spec, status,
        build_token, build_started_at, build_expires_at
    ) values (
        p_query_fingerprint, p_query_contract_version, p_service_version,
        p_instrument_methodology_version, p_asset, p_normalized_spec, 'building',
        p_build_token, clock_timestamp(),
        clock_timestamp() + make_interval(secs => p_lease_seconds)
    )
    on conflict (query_fingerprint) do update
    set status = 'building',
        query_contract_version = excluded.query_contract_version,
        service_version = excluded.service_version,
        instrument_methodology_version = excluded.instrument_methodology_version,
        asset = excluded.asset,
        normalized_spec = excluded.normalized_spec,
        build_token = excluded.build_token,
        build_started_at = excluded.build_started_at,
        build_expires_at = excluded.build_expires_at,
        updated_at = clock_timestamp()
    where public.pokemon_market_explorer_query_cache.status <> 'building'
       or public.pokemon_market_explorer_query_cache.build_expires_at <= clock_timestamp()
    returning query_fingerprint into claimed_fingerprint;

    return claimed_fingerprint is not null;
end;
$$;

create or replace function public.publish_pokemon_market_explorer_query_cache_build(
    p_query_fingerprint text,
    p_build_token uuid,
    p_computed_from date,
    p_computed_through date,
    p_series_payload jsonb,
    p_current_value numeric,
    p_constituent_count bigint,
    p_eligible_universe_count bigint,
    p_current_constituents jsonb
) returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    published_fingerprint text;
begin
    update public.pokemon_market_explorer_query_cache
    set status = 'ready',
        computed_from = p_computed_from,
        computed_through = p_computed_through,
        series_payload = p_series_payload,
        current_value = p_current_value,
        constituent_count = p_constituent_count,
        eligible_universe_count = p_eligible_universe_count,
        current_constituents = p_current_constituents,
        last_built_at = clock_timestamp(),
        updated_at = clock_timestamp(),
        build_token = null,
        build_started_at = null,
        build_expires_at = null
    where query_fingerprint = p_query_fingerprint
      and status = 'building'
      and build_token = p_build_token
      and build_expires_at > clock_timestamp()
    returning query_fingerprint into published_fingerprint;
    return published_fingerprint is not null;
end;
$$;

create or replace function public.fail_pokemon_market_explorer_query_cache_build(
    p_query_fingerprint text,
    p_build_token uuid
) returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    failed_fingerprint text;
begin
    update public.pokemon_market_explorer_query_cache
    set status = 'failed', updated_at = clock_timestamp(),
        build_token = null, build_started_at = null, build_expires_at = null
    where query_fingerprint = p_query_fingerprint
      and status = 'building'
      and build_token = p_build_token
    returning query_fingerprint into failed_fingerprint;
    return failed_fingerprint is not null;
end;
$$;

create or replace function public.invalidate_pokemon_market_explorer_query_cache(
    p_changed_market_date date default null
) returns bigint
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    affected bigint;
begin
    -- Normal forward publication remains lazy and uses computed_through.
    -- Historical repair calls this with the earliest changed date; null is a
    -- conservative all-entry recovery operation.
    update public.pokemon_market_explorer_query_cache
    set status = 'stale', updated_at = clock_timestamp()
    where status = 'ready'
      and (p_changed_market_date is null or computed_through >= p_changed_market_date);
    get diagnostics affected = row_count;

    -- The repair workflow currently invalidates all affected Market Explorer
    -- assets conservatively. This increment shares the same transaction as
    -- L2 staleness, so workers can never observe a new generation without the
    -- corresponding stale rows.
    update public.pokemon_market_explorer_cache_state
    set repair_generation = repair_generation + 1,
        updated_at = clock_timestamp();
    return affected;
end;
$$;

revoke all on function public.claim_pokemon_market_explorer_query_cache_build(
    text, text, text, text, text, jsonb, uuid, integer
) from public, anon, authenticated, service_role;
revoke all on function public.publish_pokemon_market_explorer_query_cache_build(
    text, uuid, date, date, jsonb, numeric, bigint, bigint, jsonb
) from public, anon, authenticated, service_role;
revoke all on function public.fail_pokemon_market_explorer_query_cache_build(text, uuid)
    from public, anon, authenticated, service_role;
revoke all on function public.invalidate_pokemon_market_explorer_query_cache(date)
    from public, anon, authenticated, service_role;

grant execute on function public.claim_pokemon_market_explorer_query_cache_build(
    text, text, text, text, text, jsonb, uuid, integer
) to service_role;
grant execute on function public.publish_pokemon_market_explorer_query_cache_build(
    text, uuid, date, date, jsonb, numeric, bigint, bigint, jsonb
) to service_role;
grant execute on function public.fail_pokemon_market_explorer_query_cache_build(text, uuid)
    to service_role;
grant execute on function public.invalidate_pokemon_market_explorer_query_cache(date)
    to service_role;
