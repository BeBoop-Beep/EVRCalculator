-- Migration 022: add simulated set value and realized hit-only metrics.
--
-- These columns are nullable and additive. Set value here is the current
-- "simulated set value" from the priced simulation universe, not the future
-- canonical checklist value from a unique_cards table.

ALTER TABLE IF EXISTS public.simulation_derived_metrics
    ADD COLUMN IF NOT EXISTS simulated_set_value NUMERIC,
    ADD COLUMN IF NOT EXISTS simulated_set_value_card_count INTEGER,
    ADD COLUMN IF NOT EXISTS average_hit_value NUMERIC,
    ADD COLUMN IF NOT EXISTS hit_ev_per_pack NUMERIC,
    ADD COLUMN IF NOT EXISTS hit_pull_rate NUMERIC,
    ADD COLUMN IF NOT EXISTS hit_cards_pulled INTEGER;

DO $$
DECLARE
    metric_cols text[] := ARRAY[
        'simulated_set_value',
        'simulated_set_value_card_count',
        'average_hit_value',
        'hit_ev_per_pack',
        'hit_pull_rate',
        'hit_cards_pulled'
    ];
    view_name text;
    missing_cols text[] := ARRAY[]::text[];
    col_name text;
    base_cols_select text;
    appended_select text;
    current_view_def text;
    create_sql text;
BEGIN
    FOREACH view_name IN ARRAY ARRAY[
        'explore_rip_statistics_latest',
        'simulation_latest_by_target'
    ] LOOP
        IF to_regclass(format('public.%I', view_name)) IS NULL THEN
            RAISE NOTICE 'View public.% does not exist; skipping metric passthrough', view_name;
            CONTINUE;
        END IF;

        missing_cols := ARRAY[]::text[];

        FOREACH col_name IN ARRAY metric_cols LOOP
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name = view_name
                  AND c.column_name = col_name
            ) THEN
                missing_cols := array_append(missing_cols, col_name);
            END IF;
        END LOOP;

        IF coalesce(array_length(missing_cols, 1), 0) = 0 THEN
            RAISE NOTICE 'public.% already exposes hit/set value metrics', view_name;
            CONTINUE;
        END IF;

        SELECT string_agg(format('base.%I', c.column_name), E',\n    ' ORDER BY c.ordinal_position)
        INTO base_cols_select
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = view_name;

        SELECT string_agg(format('sdm.%I AS %I', c, c), E',\n    ')
        INTO appended_select
        FROM unnest(missing_cols) AS c;

        -- Important: pg_get_viewdef can return a trailing semicolon.
        -- That semicolon is invalid when the view definition is wrapped inside FROM (...).
        SELECT regexp_replace(
            pg_get_viewdef(format('public.%I', view_name)::regclass, true),
            ';\s*$',
            ''
        )
        INTO current_view_def;

        create_sql := format(
$view$
CREATE OR REPLACE VIEW public.%I AS
SELECT
    %s,
    %s
FROM (
%s
) AS base
LEFT JOIN (
    SELECT
        calculation_run_id,
        max(simulated_set_value) AS simulated_set_value,
        max(simulated_set_value_card_count) AS simulated_set_value_card_count,
        max(average_hit_value) AS average_hit_value,
        max(hit_ev_per_pack) AS hit_ev_per_pack,
        max(hit_pull_rate) AS hit_pull_rate,
        max(hit_cards_pulled) AS hit_cards_pulled
    FROM public.simulation_derived_metrics
    GROUP BY calculation_run_id
) AS sdm
    ON sdm.calculation_run_id = base.calculation_run_id
$view$,
            view_name,
            base_cols_select,
            appended_select,
            current_view_def
        );

        EXECUTE create_sql;
    END LOOP;
END $$;