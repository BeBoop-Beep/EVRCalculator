-- Migration 021: ensure explore_rip_statistics_latest exposes p99_value_to_cost_ratio.
--
-- Scope:
--   - Adds p99_value_to_cost_ratio to public.explore_rip_statistics_latest when missing.
--   - Sources the value from simulation_derived_metrics via calculation_run_id.
--
-- Non-goals:
--   - No score formula changes.
--   - No changes to canonical ranking math or tier logic.
--   - No changes to simulation_derived_metrics persistence source.

DO $$
DECLARE
    base_cols_select text;
    current_view_def text;
    create_sql text;
BEGIN
    IF to_regclass('public.explore_rip_statistics_latest') IS NULL THEN
        RAISE EXCEPTION 'View public.explore_rip_statistics_latest does not exist';
    END IF;

    IF to_regclass('public.simulation_derived_metrics') IS NULL THEN
        RAISE EXCEPTION 'Table public.simulation_derived_metrics does not exist';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = 'explore_rip_statistics_latest'
          AND c.column_name = 'p99_value_to_cost_ratio'
    ) THEN
        RAISE NOTICE 'explore_rip_statistics_latest already exposes p99_value_to_cost_ratio';
        RETURN;
    END IF;

    SELECT string_agg(format('base.%I', c.column_name), E',\n    ' ORDER BY c.ordinal_position)
    INTO base_cols_select
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name = 'explore_rip_statistics_latest';

    IF base_cols_select IS NULL THEN
        RAISE EXCEPTION 'Could not resolve existing columns for public.explore_rip_statistics_latest';
    END IF;

    SELECT pg_get_viewdef('public.explore_rip_statistics_latest'::regclass, true)
    INTO current_view_def;

    create_sql := format(
$view$
CREATE OR REPLACE VIEW public.explore_rip_statistics_latest AS
SELECT
    %s,
    sdm.p99_value_to_cost_ratio AS p99_value_to_cost_ratio
FROM (
%s
) AS base
LEFT JOIN public.simulation_derived_metrics AS sdm
    ON sdm.calculation_run_id = base.calculation_run_id
$view$,
        base_cols_select,
        current_view_def
    );

    EXECUTE create_sql;
END $$;
