-- Keep the service-role-only Market Explorer Set-history authority from
-- inheriting the global PostgREST authenticator statement budget.
--
-- This is scoped to one backend-only RPC. Public/anon/authenticated execution
-- remains revoked, and the global authenticator timeout is unchanged.
alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])
  set statement_timeout = '30s';

alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])
  set lock_timeout = '5s';
