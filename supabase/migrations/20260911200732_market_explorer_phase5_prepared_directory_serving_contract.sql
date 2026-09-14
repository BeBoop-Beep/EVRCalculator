create table if not exists public.pokemon_market_explorer_prepared_directory_v1 (
  market_key text primary key,
  market_type text not null check (market_type in ('set','era','curated','prepared_rarity','prepared_format')),
  label text not null,
  asset text not null check (asset in ('cards','sealed')),
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
  history_point_count integer not null default 0 check (history_point_count >= 0),
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
  screen_group text check (screen_group is null or screen_group in ('card','sealed')),
  screen_eligible boolean not null default false,
  source_kind text not null,
  source_status text,
  metadata jsonb not null default '{}'::jsonb,
  generation_id uuid not null,
  generated_at timestamptz not null
);

create table if not exists public.pokemon_market_explorer_prepared_history_v1 (
  market_key text not null references public.pokemon_market_explorer_prepared_directory_v1(market_key) on delete cascade,
  market_date date not null,
  index_value numeric not null,
  tracked_value numeric,
  chain_segment_id integer not null default 0,
  generation_id uuid not null,
  primary key (market_key, market_date)
);

alter table public.pokemon_market_explorer_prepared_directory_v1 enable row level security;
alter table public.pokemon_market_explorer_prepared_history_v1 enable row level security;

revoke all on public.pokemon_market_explorer_prepared_directory_v1 from public, anon, authenticated;
revoke all on public.pokemon_market_explorer_prepared_history_v1 from public, anon, authenticated;
grant select, insert, update, delete on public.pokemon_market_explorer_prepared_directory_v1 to service_role;
grant select, insert, update, delete on public.pokemon_market_explorer_prepared_history_v1 to service_role;

create or replace function public.get_pokemon_market_explorer_prepared_directory_v1()
returns setof public.pokemon_market_explorer_prepared_directory_v1
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
as $$
  select d.*
  from public.pokemon_market_explorer_prepared_directory_v1 d
  order by
    case d.market_type
      when 'era' then 1
      when 'set' then 2
      when 'curated' then 3
      when 'prepared_rarity' then 4
      when 'prepared_format' then 5
      else 9
    end,
    d.label,
    d.market_key;
$$;

create or replace function public.get_pokemon_market_explorer_prepared_comparison_v1(p_market_keys text[])
returns setof public.pokemon_market_explorer_prepared_directory_v1
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
as $$
begin
  if p_market_keys is null or cardinality(p_market_keys) < 1 or cardinality(p_market_keys) > 25 then
    raise exception 'prepared comparison requires 1..25 market keys';
  end if;
  return query
  select d.*
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.market_key = any(p_market_keys)
  order by array_position(p_market_keys, d.market_key), d.market_key;
end;
$$;

create or replace function public.get_pokemon_market_explorer_prepared_history_v1(
  p_market_keys text[],
  p_start_date date default null
)
returns setof public.pokemon_market_explorer_prepared_history_v1
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
as $$
begin
  if p_market_keys is null or cardinality(p_market_keys) < 1 or cardinality(p_market_keys) > 25 then
    raise exception 'prepared history requires 1..25 market keys';
  end if;
  return query
  select h.*
  from public.pokemon_market_explorer_prepared_history_v1 h
  where h.market_key = any(p_market_keys)
    and (p_start_date is null or h.market_date >= p_start_date)
  order by array_position(p_market_keys, h.market_key), h.market_date;
end;
$$;

create or replace function public.get_pokemon_market_explorer_prepared_screen_v1(
  p_screen_key text,
  p_asset text default null,
  p_limit integer default 10
)
returns table (
  rank integer,
  market_key text,
  label text,
  asset text,
  market_type text,
  metric_value numeric,
  comparison_as_of date,
  generation_id uuid,
  generated_at timestamptz
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
as $$
begin
  if p_limit is null or p_limit < 1 or p_limit > 25 then
    raise exception 'screen limit must be 1..25';
  end if;
  if p_asset is not null and p_asset not in ('cards','sealed') then
    raise exception 'unsupported screen asset';
  end if;
  if p_screen_key not in ('rarity-leaders','sealed-format-leaders','momentum-leaders','largest-drawdowns') then
    raise exception 'unsupported prepared screen';
  end if;

  return query
  with candidates as (
    select d.*,
      case
        when p_screen_key in ('rarity-leaders','sealed-format-leaders','momentum-leaders') then d.return_30d_pct
        when p_screen_key='largest-drawdowns' then d.current_drawdown_pct
      end as metric
    from public.pokemon_market_explorer_prepared_directory_v1 d
    where d.screen_eligible
      and (p_asset is null or d.asset = p_asset)
      and (p_screen_key <> 'rarity-leaders' or (d.market_type='prepared_rarity' and d.asset='cards'))
      and (p_screen_key <> 'sealed-format-leaders' or (d.market_type='prepared_format' and d.asset='sealed'))
  ), ranked as (
    select c.*,
      row_number() over (
        order by
          case when p_screen_key='largest-drawdowns' then c.metric end asc nulls last,
          case when p_screen_key<>'largest-drawdowns' then c.metric end desc nulls last,
          c.market_key asc
      )::integer as screen_rank
    from candidates c
    where c.metric is not null
  )
  select r.screen_rank, r.market_key, r.label, r.asset, r.market_type,
         r.metric, r.comparison_as_of, r.generation_id, r.generated_at
  from ranked r
  where r.screen_rank <= p_limit
  order by r.screen_rank;
end;
$$;

revoke all on function public.get_pokemon_market_explorer_prepared_directory_v1() from public, anon, authenticated;
revoke all on function public.get_pokemon_market_explorer_prepared_comparison_v1(text[]) from public, anon, authenticated;
revoke all on function public.get_pokemon_market_explorer_prepared_history_v1(text[],date) from public, anon, authenticated;
revoke all on function public.get_pokemon_market_explorer_prepared_screen_v1(text,text,integer) from public, anon, authenticated;
grant execute on function public.get_pokemon_market_explorer_prepared_directory_v1() to service_role;
grant execute on function public.get_pokemon_market_explorer_prepared_comparison_v1(text[]) to service_role;
grant execute on function public.get_pokemon_market_explorer_prepared_history_v1(text[],date) to service_role;
grant execute on function public.get_pokemon_market_explorer_prepared_screen_v1(text,text,integer) to service_role;
