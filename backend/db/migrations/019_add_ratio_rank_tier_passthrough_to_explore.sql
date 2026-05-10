-- Migration 019: pass through ratio rank and tier fields into explore_rip_statistics_latest
-- from set_pack_score_rankings_latest.
--
-- Scope:
--   - mean_value_to_cost_rank
--   - mean_value_to_cost_tier
--   - p95_value_to_cost_rank
--   - p95_value_to_cost_tier
--
-- These fields already exist in set_pack_score_rankings_latest but were not included
-- in explore_rip_statistics_latest. The Explore page "Best Average Return" and
-- "Biggest Upside" ranking modes need them to display mode-specific tier badges.
--
-- Non-goals:
--   - No recalculation of ratio tiers in this view
--   - No changes to score formulas
--   - No changes to pack/profit/safety/stability/chase/experience tier behavior

DO $$
DECLARE
    passthrough_cols text[] := ARRAY[
        'mean_value_to_cost_rank',
        'mean_value_to_cost_tier',
        'p95_value_to_cost_rank',
        'p95_value_to_cost_tier'
    ];
    base_cols_select text;
    passthrough_select text;
    current_view_def text;
    create_sql text;
BEGIN
    IF to_regclass('public.explore_rip_statistics_latest') IS NULL THEN
        RAISE EXCEPTION 'View public.explore_rip_statistics_latest does not exist';
    END IF;

    IF to_regclass('public.set_pack_score_rankings_latest') IS NULL THEN
        RAISE EXCEPTION 'View public.set_pack_score_rankings_latest does not exist';
    END IF;

    -- Get all current columns of explore_rip_statistics_latest excluding the ones we're adding
    SELECT string_agg(format('base.%I', c.column_name), E',\n    ' ORDER BY c.ordinal_position)
    INTO base_cols_select
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name = 'explore_rip_statistics_latest'
      AND c.column_name <> ALL(passthrough_cols);

    IF base_cols_select IS NULL THEN
        RAISE EXCEPTION 'Could not resolve existing columns for public.explore_rip_statistics_latest';
    END IF;

    -- Build the passthrough select from set_pack_score_rankings_latest
    SELECT string_agg(format('r.%I AS %I', col_name, col_name), E',\n    ')
    INTO passthrough_select
    FROM unnest(passthrough_cols) AS col_name;

    -- Get the current view definition to use as a subquery
    SELECT pg_get_viewdef('public.explore_rip_statistics_latest'::regclass, true)
    INTO current_view_def;

    create_sql := format(
$view$
CREATE OR REPLACE VIEW public.explore_rip_statistics_latest AS
SELECT
    %s,
    %s
FROM (
%s
) AS base
LEFT JOIN public.set_pack_score_rankings_latest AS r
    ON r.calculation_run_id = base.calculation_run_id
   AND r.target_id = base.set_id
$view$,
        base_cols_select,
        passthrough_select,
        current_view_def
    );

    EXECUTE create_sql;
END $$;
