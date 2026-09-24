-- Faithful minimal fixture of production dependencies (NOT the migration under test).
create role anon nologin; create role authenticated nologin; create role service_role nologin;
create role market_explorer_publisher nologin;

create table public.eras (id uuid primary key, name text not null);
create table public.sets (id uuid primary key, name text not null, era_id uuid references public.eras(id));
create table public.pokemon_canonical_cards (id uuid primary key, name text, printed_number text, rarity text);
create table public.card_variants (id uuid primary key, edition text, printing_type text, special_type text);

-- Resolver fixture: root/child membership with counts_toward_parent_set_value flag.
create table public.fx_roster (root_set_id uuid, set_id uuid, canonical_card_id uuid, card_variant_id uuid,
  market_price numeric, market_date date, counts_toward_parent_set_value boolean not null default true);
create function public.get_pokemon_cards_daily_constituents(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] default null)
returns table(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
language plpgsql stable set search_path='' as $$
begin
  return query select r.canonical_card_id, r.set_id, r.market_date, r.market_price, r.card_variant_id, 'fx'::text, r.market_date
  from public.fx_roster r where r.root_set_id = any(p_set_ids) and r.counts_toward_parent_set_value
    and r.market_date between p_start_date and p_end_date;
end $$;

create table public.pokemon_market_explorer_query_cache (
  query_fingerprint text primary key, cache_kind text not null, status text not null, asset text not null,
  computed_through date, last_built_at timestamptz, constituent_count integer,
  normalized_spec jsonb, series_payload jsonb);
create table public.pokemon_market_explorer_query_cache_constituents (
  query_fingerprint text not null references public.pokemon_market_explorer_query_cache(query_fingerprint) on delete cascade,
  rank integer not null, item jsonb not null, primary key (query_fingerprint, rank));
create table public.pokemon_explore_set_value_snapshot_latest (
  tcg text not null, scope text not null, market_date date, updated_at timestamptz, set_count integer,
  payload_json jsonb, primary key (tcg, scope));
create table public.pokemon_set_market_dashboard_snapshot_latest (set_id uuid, updated_at timestamptz);
create table public.pokemon_set_sealed_market_snapshot_latest (tcg text, updated_at timestamptz, product_count integer, payload_json jsonb);
