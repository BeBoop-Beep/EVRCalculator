create extension if not exists pgcrypto;
do $$ begin
  if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
end $$;
create table public.pokemon_canonical_cards(id uuid primary key);
create table public.card_variants(id uuid primary key, card_id uuid, edition text, printing_type text, special_type text);
create table public.pokemon_market_explorer_query_cache(
 id uuid primary key default gen_random_uuid(), query_fingerprint text not null unique,
 query_contract_version text not null, service_version text not null, instrument_methodology_version text not null,
 asset text not null, normalized_spec jsonb not null, status text not null, computed_from date, computed_through date,
 series_payload jsonb, current_value numeric, constituent_count bigint, eligible_universe_count bigint,
 current_constituents jsonb, created_at timestamptz default now(), updated_at timestamptz default now(),
 last_built_at timestamptz, build_token uuid, build_started_at timestamptz, build_expires_at timestamptz);
create function public.publish_pokemon_market_explorer_query_cache_build(
 text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) returns boolean language sql as $$ select false $$;
revoke all on function public.publish_pokemon_market_explorer_query_cache_build(
 text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.publish_pokemon_market_explorer_query_cache_build(
 text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) to service_role;
create table public.pokemon_market_explorer_surface_generations_v2(
 generation_id uuid primary key, base_prepared_generation_id uuid not null, market_date date not null,
 raw_methodology_version text not null, state text not null, diagnostics jsonb default '{}', created_at timestamptz default now());
create table public.pokemon_market_explorer_surface_serving_v2(
 singleton smallint primary key, generation_id uuid references public.pokemon_market_explorer_surface_generations_v2,
 previous_generation_id uuid, promoted_at timestamptz);
create table public.market_active_supply_snapshots_v1(id uuid primary key);
