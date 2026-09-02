-- Broad cache-first markets are built through this service-role-only candidate.
-- Keep the override local to the function and aligned with the 300-second L2
-- build lease; do not change the database or role-wide statement timeout.
BEGIN;

ALTER FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
) SET statement_timeout = '300s';

COMMIT;
