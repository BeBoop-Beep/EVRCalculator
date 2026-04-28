-- Extend explore_rip_statistics_latest with ranking/tier/relative fields from
-- set_pack_score_rankings_latest by appending only missing columns at the end.
-- This avoids breaking existing column order and is idempotent.
DO $$
DECLARE
    required_cols text[] := ARRAY[
        'pack_tier',
        'profit_rank',
        'profit_tier',
        'safety_rank',
        'safety_tier',
        'stability_rank',
        'stability_tier',
        'relative_profit_score',
        'relative_safety_score',
        'relative_stability_score',
        'median_value_to_cost_ratio',
        'median_loss_when_losing_fraction'
    ];
    missing_cols text[] := ARRAY[]::text[];
    col_name text;
    appended_select text;
    current_view_def text;
    create_sql text;
BEGIN
    IF to_regclass('public.explore_rip_statistics_latest') IS NULL THEN
        RAISE EXCEPTION 'View public.explore_rip_statistics_latest does not exist';
    END IF;

    IF to_regclass('public.set_pack_score_rankings_latest') IS NULL THEN
        RAISE EXCEPTION 'View public.set_pack_score_rankings_latest does not exist';
    END IF;

    FOREACH col_name IN ARRAY required_cols LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = 'explore_rip_statistics_latest'
              AND c.column_name = col_name
        ) THEN
            missing_cols := array_append(missing_cols, col_name);
        END IF;
    END LOOP;

    IF coalesce(array_length(missing_cols, 1), 0) = 0 THEN
        RAISE NOTICE 'explore_rip_statistics_latest already contains all required columns';
        RETURN;
    END IF;

    SELECT pg_get_viewdef('public.explore_rip_statistics_latest'::regclass, true)
    INTO current_view_def;

    SELECT string_agg(format('sprl.%I AS %I', c, c), E',\n    ')
    INTO appended_select
    FROM unnest(missing_cols) AS c;

    create_sql := format(
$view$
CREATE OR REPLACE VIEW public.explore_rip_statistics_latest AS
SELECT
    base.*,
    %s
FROM (
%s
) AS base
LEFT JOIN public.set_pack_score_rankings_latest AS sprl
    ON sprl.calculation_run_id = base.calculation_run_id
   AND sprl.target_id = base.set_id
$view$,
        appended_select,
        current_view_def
    );

    EXECUTE create_sql;
END $$;
