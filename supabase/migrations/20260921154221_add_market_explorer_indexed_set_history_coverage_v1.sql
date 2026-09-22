-- Fast, semantics-preserving Set-history coverage for Market Explorer hot paths.
--
-- This keeps the legacy authority contract:
--   * a Set is tracked when it has at least one standard Set Value history row
--   * catalog_only Sets are excluded
--   * newly-onboarded Sets are visible immediately, even before V2 projection
--     coverage has caught up
--
-- The old pokemon_set_value_daily_history_coverage view groups the full
-- history table and can exceed the PostgREST statement budget under load.
-- This RPC instead performs indexed first/latest edge probes per Set.

create or replace function public.get_pokemon_market_explorer_set_history_coverage_v1(
  p_set_ids uuid[] default null
)
returns table(
  set_id uuid,
  first_snapshot_date date,
  latest_snapshot_date date
)
language sql
stable
security invoker
set search_path = ''
as $function$
  select
    s.id as set_id,
    first_edge.snapshot_date as first_snapshot_date,
    latest_edge.snapshot_date as latest_snapshot_date
  from public.sets s
  cross join lateral (
    select h.snapshot_date
    from public.pokemon_set_value_daily_history h
    where h.set_id = s.id
      and h.value_scope = 'standard'
    order by h.snapshot_date asc
    limit 1
  ) first_edge
  cross join lateral (
    select h.snapshot_date
    from public.pokemon_set_value_daily_history h
    where h.set_id = s.id
      and h.value_scope = 'standard'
    order by h.snapshot_date desc
    limit 1
  ) latest_edge
  where coalesce(s.catalog_only, false) = false
    and (p_set_ids is null or s.id = any(p_set_ids))
  order by s.id;
$function$;

revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from public;
revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from anon;
revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from authenticated;
grant execute on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) to service_role;
