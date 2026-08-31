-- Production safe-update requires an explicit predicate on every UPDATE.
-- Preserve the conservative cross-asset invalidation transaction while
-- bounding the two-row repair-generation authority.
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
    update public.pokemon_market_explorer_query_cache
    set status = 'stale', updated_at = clock_timestamp()
    where status = 'ready'
      and (p_changed_market_date is null or computed_through >= p_changed_market_date);
    get diagnostics affected = row_count;

    update public.pokemon_market_explorer_cache_state
    set repair_generation = repair_generation + 1,
        updated_at = clock_timestamp()
    where asset in ('cards', 'sealed');
    return affected;
end;
$$;

revoke all on function public.invalidate_pokemon_market_explorer_query_cache(date)
    from public, anon, authenticated, service_role;
grant execute on function public.invalidate_pokemon_market_explorer_query_cache(date)
    to service_role;
