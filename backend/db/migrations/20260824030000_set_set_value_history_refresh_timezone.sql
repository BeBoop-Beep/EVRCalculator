-- Pin the canonical market-day timezone for the Set Value history refresh.
-- captured_at is a bare DATE, so its implicit timestamp conversion must not
-- depend on the calling session's TimeZone.

BEGIN;

ALTER FUNCTION public.refresh_pokemon_set_value_daily_history(UUID, DATE, DATE)
    SET "TimeZone" TO 'America/Phoenix';

COMMIT;
