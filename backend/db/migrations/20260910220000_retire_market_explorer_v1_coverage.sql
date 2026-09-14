-- Final physical retirement of the frozen V1 Market Explorer coverage table.
--
-- Market Explorer runtime and publication are V2-only. Keep the V2 coverage
-- authority intact and fail closed if it is unavailable. Intentionally omit
-- CASCADE so any unexpected dependency blocks retirement rather than being
-- removed implicitly.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

DO $$
DECLARE
    v_v2_coverage_rows bigint;
BEGIN
    IF to_regclass('public.pokemon_market_explorer_card_daily_coverage_v2_shadow') IS NULL THEN
        RAISE EXCEPTION
            'Refusing V1 Market Explorer coverage retirement: V2 coverage authority is missing';
    END IF;

    EXECUTE 'select count(*) from public.pokemon_market_explorer_card_daily_coverage_v2_shadow'
    INTO v_v2_coverage_rows;

    IF coalesce(v_v2_coverage_rows, 0) = 0 THEN
        RAISE EXCEPTION
            'Refusing V1 Market Explorer coverage retirement: V2 coverage authority is empty';
    END IF;
END
$$;

DROP TABLE IF EXISTS public.pokemon_market_explorer_card_daily_coverage;

COMMIT;
