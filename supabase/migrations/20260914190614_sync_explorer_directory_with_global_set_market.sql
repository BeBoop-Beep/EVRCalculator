-- Keep Market Explorer's prepared Set directory transactionally aligned with
-- the canonical Global Set Market snapshot. The directory already derives Set
-- membership from that snapshot; this trigger makes the refresh automatic.

CREATE OR REPLACE FUNCTION public.refresh_market_explorer_directory_after_set_market_v1()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
  IF TG_OP = 'UPDATE'
     AND OLD.market_date IS NOT DISTINCT FROM NEW.market_date
     AND OLD.set_count IS NOT DISTINCT FROM NEW.set_count
     AND OLD.source_generation_fingerprint IS NOT DISTINCT FROM NEW.source_generation_fingerprint THEN
    RETURN NEW;
  END IF;

  PERFORM public.refresh_pokemon_market_explorer_prepared_directory_v1();
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_market_explorer_directory_after_set_market_v1()
  FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS pokemon_global_set_market_refresh_explorer_directory
  ON public.pokemon_explore_set_value_snapshot_latest;

CREATE TRIGGER pokemon_global_set_market_refresh_explorer_directory
AFTER INSERT OR UPDATE OF market_date, set_count, source_generation_fingerprint, payload_json
ON public.pokemon_explore_set_value_snapshot_latest
FOR EACH ROW
WHEN (NEW.tcg = 'pokemon' AND NEW.scope = 'market')
EXECUTE FUNCTION public.refresh_market_explorer_directory_after_set_market_v1();

COMMENT ON FUNCTION public.refresh_market_explorer_directory_after_set_market_v1() IS
'Fail-closed coupling between the canonical Global Set Market snapshot and the prepared Market Explorer directory. A changed Pokemon market snapshot refreshes the directory/history in the same transaction.';
