-- A set's first_market_date is its earliest authoritative contribution, not a
-- cohort-wide lower bound.  Keep fail-closed completeness on missing/stale
-- coverage while allowing valid earlier history from other requested sets.
BEGIN;

DO $migration$
DECLARE
  target regprocedure :=
    'public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)'::regprocedure;
  old_definition text;
  new_definition text;
  old_predicate constant text :=
    ' and first_market_date<=p_start_date and computed_through>=p_end_date';
  new_predicate constant text :=
    ' and computed_through>=p_end_date';
BEGIN
  old_definition := pg_get_functiondef(target);
  new_definition := replace(old_definition, old_predicate, new_predicate);
  IF new_definition = old_definition THEN
    RAISE EXCEPTION 'expected staggered-start coverage predicate was not found';
  END IF;
  EXECUTE new_definition;
END
$migration$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
) IS 'Daily projection candidate. Every requested set must be covered through the requested end; first_market_date is per-set contribution metadata and never truncates other sets.';

COMMIT;
