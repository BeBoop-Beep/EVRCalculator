BEGIN;
ALTER FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
) SET work_mem = '64MB';
COMMIT;
