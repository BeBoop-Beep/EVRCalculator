-- Verified V2-only Market Explorer daily publication.
--
-- The V1 daily-state relation was retired on 2026-09-09. This migration adds
-- a fail-closed V2 publication wrapper that preserves the old exact-
-- reconciliation guarantee without recreating any V1 storage.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '120s';

CREATE OR REPLACE FUNCTION public.verify_pokemon_market_explorer_daily_v2_for_set(
    p_set_id uuid,
    p_through_date date,
    p_retention_days integer DEFAULT 100
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path TO ''
AS $function$
DECLARE
    v_from date;
    v_expected bigint := 0;
    v_actual bigint := 0;
    v_mismatch bigint := 0;
    v_outside_window bigint := 0;
    v_coverage public.pokemon_market_explorer_card_daily_coverage_v2_shadow%rowtype;
    v_coverage_ok boolean := false;
BEGIN
    IF p_set_id IS NULL OR p_through_date IS NULL THEN
        RAISE EXCEPTION 'set_id and through_date are required';
    END IF;
    IF p_retention_days IS NULL OR p_retention_days < 1 OR p_retention_days > 400 THEN
        RAISE EXCEPTION 'p_retention_days must be between 1 and 400';
    END IF;

    v_from := p_through_date - (p_retention_days - 1);

    WITH approved_dates AS MATERIALIZED (
        SELECT DISTINCT quality.market_date
        FROM public.pokemon_market_date_quality quality
        WHERE quality.tcg = 'pokemon'
          AND quality.market_date BETWEEN v_from AND p_through_date
          AND quality.status IN ('READY', 'LEGACY_VERIFIED')
    ), expected AS MATERIALIZED (
        SELECT d.market_date, i.card_variant_id, i.set_id, i.market_price
        FROM approved_dates d
        JOIN public.pokemon_market_price_intervals_v2_shadow i
          ON i.set_id = p_set_id
         AND i.valid_from <= d.market_date
         AND (i.valid_to IS NULL OR d.market_date < i.valid_to)
    ), actual AS MATERIALIZED (
        SELECT s.market_date, s.card_variant_id, s.set_id, s.market_price
        FROM public.pokemon_market_explorer_card_daily_states_v2_shadow s
        WHERE s.set_id = p_set_id
          AND s.market_date BETWEEN v_from AND p_through_date
    ), differences AS MATERIALIZED (
        SELECT
            coalesce(e.market_date, a.market_date) AS market_date,
            coalesce(e.card_variant_id, a.card_variant_id) AS card_variant_id
        FROM expected e
        FULL OUTER JOIN actual a
          ON a.market_date = e.market_date
         AND a.card_variant_id = e.card_variant_id
        WHERE e.card_variant_id IS NULL
           OR a.card_variant_id IS NULL
           OR e.set_id IS DISTINCT FROM a.set_id
           OR e.market_price IS DISTINCT FROM a.market_price
    )
    SELECT
        (SELECT count(*) FROM expected),
        (SELECT count(*) FROM actual),
        (SELECT count(*) FROM differences)
    INTO v_expected, v_actual, v_mismatch;

    SELECT count(*)
    INTO v_outside_window
    FROM public.pokemon_market_explorer_card_daily_states_v2_shadow s
    WHERE s.set_id = p_set_id
      AND (s.market_date < v_from OR s.market_date > p_through_date);

    SELECT *
    INTO v_coverage
    FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow
    WHERE set_id = p_set_id;

    IF FOUND THEN
        v_coverage_ok :=
            v_coverage.retained_from = v_from
            AND v_coverage.computed_through = p_through_date
            AND v_coverage.retention_days = p_retention_days
            AND v_coverage.row_count = v_actual;
    END IF;

    RETURN jsonb_build_object(
        'set_id', p_set_id,
        'retained_from', v_from,
        'computed_through', p_through_date,
        'retention_days', p_retention_days,
        'expected_rows', v_expected,
        'actual_rows', v_actual,
        'mismatch_rows', v_mismatch,
        'outside_window_rows', v_outside_window,
        'coverage_ok', v_coverage_ok,
        'reconciled', (
            v_expected = v_actual
            AND v_mismatch = 0
            AND v_outside_window = 0
            AND v_coverage_ok
        )
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.publish_pokemon_market_explorer_daily_v2_for_set(
    p_set_id uuid,
    p_through_date date,
    p_retention_days integer DEFAULT 100,
    p_force_rebuild boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path TO ''
AS $function$
DECLARE
    v_action jsonb;
    v_verify jsonb;
    v_mode text;
BEGIN
    IF p_set_id IS NULL OR p_through_date IS NULL THEN
        RAISE EXCEPTION 'set_id and through_date are required';
    END IF;
    IF p_retention_days IS NULL OR p_retention_days < 1 OR p_retention_days > 400 THEN
        RAISE EXCEPTION 'p_retention_days must be between 1 and 400';
    END IF;

    IF p_force_rebuild THEN
        v_action := public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(
            p_set_id, p_through_date, p_retention_days
        );
        v_mode := 'rebuilt';
    ELSE
        v_action := public.advance_pokemon_market_explorer_daily_v2_shadow_for_set(
            p_set_id, p_through_date, p_retention_days
        );
        v_mode := 'advanced';
    END IF;

    v_verify := public.verify_pokemon_market_explorer_daily_v2_for_set(
        p_set_id, p_through_date, p_retention_days
    );

    -- Forward-append is the cheap path. If anything in the retained panel has
    -- drifted (identity retirement, corrected interval, stale row_count, etc.),
    -- rebuild exactly this set and verify again in the same transaction.
    IF coalesce((v_verify ->> 'reconciled')::boolean, false) IS NOT TRUE
       AND p_force_rebuild IS NOT TRUE THEN
        v_action := public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(
            p_set_id, p_through_date, p_retention_days
        );
        v_mode := 'rebuilt_after_drift';
        v_verify := public.verify_pokemon_market_explorer_daily_v2_for_set(
            p_set_id, p_through_date, p_retention_days
        );
    END IF;

    IF coalesce((v_verify ->> 'reconciled')::boolean, false) IS NOT TRUE THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = format(
                'Market Explorer V2 daily reconciliation failed for set %s through %s: %s',
                p_set_id, p_through_date, v_verify::text
            );
    END IF;

    RETURN v_verify
        || jsonb_build_object(
            'status', 'verified',
            'mode', v_mode,
            'action', v_action
        );
END;
$function$;

REVOKE ALL ON FUNCTION public.verify_pokemon_market_explorer_daily_v2_for_set(uuid,date,integer)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.publish_pokemon_market_explorer_daily_v2_for_set(uuid,date,integer,boolean)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.verify_pokemon_market_explorer_daily_v2_for_set(uuid,date,integer)
TO service_role;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_market_explorer_daily_v2_for_set(uuid,date,integer,boolean)
TO service_role;

COMMIT;
