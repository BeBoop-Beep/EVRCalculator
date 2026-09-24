-- Minimal PostgreSQL 17 fixture for Market Explorer expansion migrations.
-- Disposable CI only: representative source contracts, no production data.

create schema if not exists extensions;
create extension if not exists pgcrypto;
create extension if not exists pg_trgm with schema extensions;

do $$
begin
  if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
end $$;

create or replace function public.normalize_pokemon_market_explorer_search_text_v2(p text)
returns text language sql immutable set search_path='' as $$
  select nullif(trim(regexp_replace(lower(coalesce(p,'')),'[^a-z0-9]+',' ','g')),'');
$$;

create or replace function public.market_explorer_filter_rarity_key(p text)
returns text language sql immutable set search_path='' as $$
  select case lower(trim(coalesce(p,'')))
    when 'rare holo gx' then 'rareHoloGx'
    when 'rare holo ex' then 'rareHoloEx'
    when 'rare holo v' then 'rareHoloV'
    when 'rare holo vmax' then 'rareHoloVmax'
    when 'rare holo vstar' then 'rareHoloVstar'
    when 'rare ultra' then 'rareUltra'
    when 'rare secret' then 'rareSecret'
    when 'ultra rare' then 'ultraRare'
    when 'special illustration rare' then 'specialIllustrationRare'
    when 'common' then 'common'
    when 'uncommon' then 'uncommon'
    when 'rare' then 'rare'
    else null
  end;
$$;

create table public.eras(
  id uuid primary key,
  name text not null
);
create table public.sets(
  id uuid primary key,
  name text not null,
  era_id uuid references public.eras(id),
  parent_opening_set_id uuid,
  counts_toward_parent_set_value boolean default false,
  catalog_only boolean default false
);
create table public.card_variants(
  id uuid primary key,
  image_small_url text,
  image_large_url text
);
create table public.pokemon_canonical_cards(
  id uuid primary key,
  set_id uuid references public.sets(id),
  name text not null,
  number text,
  printed_number text,
  rarity text,
  set_value_eligible boolean default true,
  image_small_url text,
  image_large_url text
);
create table public.pokemon_market_explorer_card_current_metadata(
  card_variant_id uuid primary key,
  canonical_card_id uuid not null,
  legacy_card_id uuid not null,
  set_id uuid not null,
  card_name text not null,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  image_url text,
  identity_basis text not null,
  refreshed_at timestamptz not null default now()
);
create table public.pokemon_market_explorer_card_daily_states_v2_shadow(
  market_date date not null,
  card_variant_id uuid not null,
  set_id uuid not null,
  market_price numeric not null,
  primary key(market_date,card_variant_id)
);
create table public.pokemon_market_date_quality(
  tcg text not null,
  market_date date not null,
  status text not null,
  primary key(tcg,market_date)
);

create table public.pokemon_market_explorer_prepared_directory_v1(
  market_key text primary key,
  market_type text not null,
  label text not null,
  asset text not null,
  set_id uuid,
  era_id uuid,
  parent_era_id uuid,
  prepared_series_key text not null,
  comparison_as_of date not null,
  source_as_of date,
  current_value numeric,
  comparison_value numeric,
  comparison_index_value numeric,
  history_available boolean not null default false,
  history_start_date date,
  history_end_date date,
  history_point_count integer not null default 0,
  return_7d_pct numeric,
  return_30d_pct numeric,
  return_90d_pct numeric,
  return_1y_pct numeric,
  current_drawdown_pct numeric,
  max_drawdown_pct numeric,
  relative_7d_vs_era_pct numeric,
  relative_30d_vs_era_pct numeric,
  relative_90d_vs_era_pct numeric,
  relative_1y_vs_era_pct numeric,
  screen_group text,
  screen_eligible boolean not null default false,
  source_kind text not null,
  source_status text,
  metadata jsonb not null default '{}'::jsonb,
  generation_id uuid not null,
  generated_at timestamptz not null
);
create table public.pokemon_market_explorer_prepared_history_v1(
  market_key text not null references public.pokemon_market_explorer_prepared_directory_v1(market_key) on delete cascade,
  market_date date not null,
  index_value numeric not null,
  tracked_value numeric,
  chain_segment_id integer not null default 0,
  generation_id uuid not null,
  primary key(market_key,market_date)
);
create table public.pokemon_market_explorer_prepared_constituent_totals_v1(
  generation_id uuid not null,
  market_key text not null,
  asset text not null,
  source_kind text not null,
  definition_version text,
  source_as_of date,
  total_count integer not null,
  availability text not null,
  availability_reason text,
  staged_at timestamptz default now(),
  primary key(generation_id,market_key)
);
create table public.pokemon_market_explorer_prepared_constituents_v1(
  generation_id uuid not null,
  market_key text not null,
  rank integer not null,
  instrument_id text not null,
  asset text not null,
  market_price numeric,
  price_as_of date,
  item jsonb not null,
  primary key(generation_id,market_key,rank),
  unique(generation_id,market_key,instrument_id)
);

create table public.pokemon_market_index_daily_history(
  id uuid primary key default gen_random_uuid(),
  tcg text not null,
  index_key text not null,
  market_date date not null,
  contract_version text not null,
  methodology_version text not null,
  basket_value numeric not null,
  normalized_index_value numeric not null,
  daily_return numeric,
  previous_market_date date,
  set_count integer not null,
  card_count integer not null,
  cohort_fingerprint text not null,
  source_generation_fingerprint text not null,
  constituents_json jsonb not null,
  diagnostics_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(tcg,index_key,market_date,methodology_version)
);

create table public.pokemon_market_set_scope_contract_v1(
  set_id uuid not null,
  base_set_name text,
  profile text not null,
  market_scope text not null,
  market_key text not null,
  display_label text,
  primary key(set_id,market_scope)
);

create table public.sealed_products(
  id uuid primary key,
  set_id uuid references public.sets(id),
  name text not null,
  image_small_url text,
  image_large_url text
);
create table public.sealed_product_price_observations(
  id bigserial primary key,
  sealed_product_id uuid not null references public.sealed_products(id),
  market_price numeric not null,
  source text,
  currency text default 'USD',
  captured_at timestamptz not null default now()
);
create index on public.sealed_product_price_observations(captured_at);
create index on public.sealed_product_price_observations(sealed_product_id,captured_at desc);

create or replace function public.search_pokemon_market_explorer_instruments_v2(
  p_query text,p_asset text default 'all',p_limit integer default 20
)
returns table(
  asset text,instrument_id uuid,name text,set_id uuid,set_name text,image_url text,
  card_number text,rarity text,edition text,printing_type text,special_type text,
  product_family text,variant_label text,match_kind text,relevance_score integer,name_similarity real
)
language sql stable set search_path='' as $$
  select
    'cards'::text,m.card_variant_id,m.card_name,m.set_id,s.name,m.image_url,
    m.card_number,m.rarity,m.edition,m.printing_type,m.special_type,
    null::text,null::text,'fixture'::text,900::integer,1.0::real
  from public.pokemon_market_explorer_card_current_metadata m
  left join public.sets s on s.id=m.set_id
  where p_asset in ('all','cards')
    and lower(m.card_name) like '%'||lower(p_query)||'%'
  order by m.card_name
  limit least(greatest(coalesce(p_limit,20),1),50);
$$;
