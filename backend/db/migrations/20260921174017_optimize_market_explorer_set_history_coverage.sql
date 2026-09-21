-- Optimize Market Explorer's canonical Set history edge lookups.
--
-- get_pokemon_market_explorer_set_history_coverage_v1 performs first/latest
-- lookups for standard Set Value history. Existing indexes put value_scope
-- after snapshot_date (or index it separately), which can leave the broad
-- 166-Set authority read above the PostgREST statement timeout. This partial
-- index matches the function predicate and ordering directly without changing
-- any reader contract or data.
create index if not exists idx_pokemon_set_value_daily_history_standard_set_date
  on public.pokemon_set_value_daily_history (set_id, snapshot_date)
  where value_scope = 'standard';

analyze public.pokemon_set_value_daily_history;
