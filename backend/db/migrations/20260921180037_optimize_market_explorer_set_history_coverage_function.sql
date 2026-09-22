-- Make the Market Explorer tracked-Set coverage RPC stable under the
-- service-role/PostgREST statement budget.
--
-- Same contract and ACL as v1:
--   * standard Set Value history is the authority
--   * catalog_only Sets are excluded
--   * optional p_set_ids narrows the result
--   * service_role only
--
-- The grouped form uses the dedicated partial index and avoids hundreds of
-- lateral edge probes whose planning/execution was sensitive to DB load.

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
    h.set_id,
    min(h.snapshot_date) as first_snapshot_date,
    max(h.snapshot_date) as latest_snapshot_date
  from public.pokemon_set_value_daily_history h
  join public.sets s on s.id = h.set_id
  where h.value_scope = 'standard'
    and coalesce(s.catalog_only, false) = false
    and (p_set_ids is null or h.set_id = any(p_set_ids))
  group by h.set_id
  order by h.set_id;
$function$;

revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from public;
revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from anon;
revoke all on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) from authenticated;
grant execute on function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[]) to service_role;
