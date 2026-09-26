BEGIN;

ALTER FUNCTION public.refresh_pokemon_set_value_daily_history(UUID, DATE, DATE)
    SET "TimeZone" TO 'America/Phoenix';

COMMIT;
