do $$
declare
    v_def text;
begin
    if to_regprocedure('public.get_pokemon_market_root_set_value_daily_history_v1_legacy_shadow(uuid,date,date)') is null then
        select pg_get_functiondef('public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date)'::regprocedure)
        into v_def;
        v_def := replace(
            v_def,
            'FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1(',
            'FUNCTION public.get_pokemon_market_root_set_value_daily_history_v1_legacy_shadow('
        );
        execute v_def;
    end if;
end
$$;

revoke all on function public.get_pokemon_market_root_set_value_daily_history_v1_legacy_shadow(uuid,date,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_value_daily_history_v1_legacy_shadow(uuid,date,date) to postgres,service_role;

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
    select set_id,set_name,market_scope,market_date,set_value,
           expected_card_count,priced_card_count,coverage_pct,certified_on_date,source
    from public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(
        p_root_set_id,p_start_date,p_end_date
    );
$$;