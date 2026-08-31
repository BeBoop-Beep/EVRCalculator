-- Make explicitly bounded Set Value refreshes honor latest-known-price-as-of-day.
--
-- The deployed function's constituent predicates are the production authority
-- and have evolved beyond the oldest checked-in function body.  Patch only its
-- two identical set_dates end-bound expressions so all identity, eligibility,
-- variant, condition, hits and top-10 behavior remains otherwise unchanged.

BEGIN;

DO $migration$
DECLARE
    v_function regprocedure :=
        'public.refresh_pokemon_set_value_daily_history(uuid,date,date)'::regprocedure;
    v_definition text;
    v_patched_definition text;
    v_old_end_bound_pattern constant text := $pattern$least\(\s*coalesce\(p_end_date,\s*b\.latest_observation_date\),\s*b\.latest_observation_date,\s*timezone\(v_set_value_market_day_timezone,\s*now\(\)\)::date\s*\)$pattern$;
    v_new_end_bound constant text := $replacement$
least(
                CASE
                    WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                        THEN p_end_date
                    ELSE b.latest_observation_date
                END,
                timezone(v_set_value_market_day_timezone, now())::date
            )
$replacement$;
    v_match_count integer;
BEGIN
    SELECT pg_get_functiondef(v_function)
    INTO v_definition;

    SELECT count(*)
    INTO v_match_count
    FROM regexp_matches(v_definition, v_old_end_bound_pattern, 'g');

    IF v_match_count <> 2 THEN
        RAISE EXCEPTION
            'bounded Set Value refresh patch expected 2 legacy end bounds, found %',
            v_match_count;
    END IF;

    v_patched_definition := regexp_replace(
        v_definition,
        v_old_end_bound_pattern,
        v_new_end_bound,
        'g'
    );

    IF v_patched_definition = v_definition THEN
        RAISE EXCEPTION 'bounded Set Value refresh patch made no change';
    END IF;

    EXECUTE v_patched_definition;
END;
$migration$;

COMMENT ON FUNCTION public.refresh_pokemon_set_value_daily_history(uuid, date, date) IS
    'Refreshes canonical Set Value history. Explicitly bounded calls generate '
    'requested Phoenix market dates through p_end_date (never future dates) when '
    'eligible prior observations exist; unbounded calls remain capped at the '
    'latest eligible observation date. Prices remain latest-known as of each day.';

COMMIT;
