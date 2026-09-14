create or replace function public.get_pokemon_market_root_set_value_daily_history_v1(
    p_root_set_id uuid,
    p_start_date date,
    p_end_date date
)
returns table(
    set_id uuid,
    set_name text,
    market_scope text,
    market_date date,
    set_value numeric,
    expected_card_count integer,
    priced_card_count integer,
    coverage_pct numeric,
    certified_on_date boolean,
    source text
)
language sql
stable
set search_path to ''
set "TimeZone" to 'America/Phoenix'
as $$
    select h.set_id,s.name as set_name,h.market_scope,h.market_date,h.set_value,
           h.expected_card_count,h.priced_card_count,h.coverage_pct,h.certified_on_date,h.source
    from public.pokemon_market_root_set_value_daily_history_v2_shadow h
    join public.sets s on s.id=h.set_id
    where h.set_id=p_root_set_id
      and h.market_date between p_start_date and p_end_date
    order by h.market_date,h.market_scope;
$$;
revoke all on function public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date) to postgres,service_role;