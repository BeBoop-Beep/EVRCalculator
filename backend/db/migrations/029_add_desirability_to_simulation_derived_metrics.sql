-- Migration 029: add independent Desirability pillar fields to simulation derived metrics.
--
-- Desirability V1 sources set-level hit-card intrinsic desirability from
-- pokemon_set_hit_desirability_summaries.weighted_average_hit_desirability_score.
-- It is intentionally independent of card price, sealed price, EV, pack value,
-- pull value, liquidity, and historical pricing.

ALTER TABLE IF EXISTS public.simulation_derived_metrics
    ADD COLUMN IF NOT EXISTS desirability_score NUMERIC
        CHECK (desirability_score IS NULL OR desirability_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS desirability_scoring_version TEXT,
    ADD COLUMN IF NOT EXISTS desirability_source_summary_id UUID,
    ADD COLUMN IF NOT EXISTS desirability_source_table TEXT,
    ADD COLUMN IF NOT EXISTS desirability_source_metric TEXT,
    ADD COLUMN IF NOT EXISTS desirability_is_fallback BOOLEAN,
    ADD COLUMN IF NOT EXISTS desirability_fallback_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_simulation_derived_metrics_desirability_score
    ON public.simulation_derived_metrics(desirability_score DESC NULLS LAST);

DO $$
DECLARE
    metric_cols text[] := ARRAY[
        'desirability_score',
        'relative_desirability_score',
        'desirability_rank',
        'desirability_tier',
        'desirability_scoring_version',
        'desirability_source_summary_id',
        'desirability_source_table',
        'desirability_source_metric',
        'desirability_is_fallback',
        'desirability_fallback_reason'
    ];
    view_name text;
    missing_cols text[] := ARRAY[]::text[];
    col_name text;
    has_desirability_score boolean;
    base_cols_select text;
    appended_select text;
    current_view_def text;
    create_sql text;
BEGIN
    FOREACH view_name IN ARRAY ARRAY[
        'simulation_latest_by_target',
        'explore_rip_statistics_latest',
        'set_pack_score_rankings_latest'
    ] LOOP
        IF to_regclass(format('public.%I', view_name)) IS NULL THEN
            RAISE NOTICE 'View public.% does not exist; skipping desirability passthrough', view_name;
            CONTINUE;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = view_name
              AND c.column_name = 'calculation_run_id'
        ) THEN
            RAISE EXCEPTION 'View public.% must expose calculation_run_id before desirability passthrough can be added', view_name;
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = view_name
              AND c.column_name = 'desirability_score'
        )
        INTO has_desirability_score;

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
            RAISE NOTICE 'public.% already exposes desirability fields', view_name;
            CONTINUE;
        END IF;

        SELECT string_agg(
            CASE c.column_name
                WHEN 'desirability_score' THEN 'ranked.__desirability_score_for_calc AS desirability_score'
                WHEN 'relative_desirability_score' THEN
                    $case$CASE
        WHEN ranked.__desirability_score_for_calc IS NULL THEN NULL::numeric
        WHEN ranked.__max_desirability_score_for_calc <= ranked.__min_desirability_score_for_calc THEN 50::numeric
        ELSE (100.0 * ((ranked.__desirability_score_for_calc - ranked.__min_desirability_score_for_calc) / (ranked.__max_desirability_score_for_calc - ranked.__min_desirability_score_for_calc)))
    END AS relative_desirability_score$case$
                WHEN 'desirability_rank' THEN 'ranked.__desirability_rank_for_calc AS desirability_rank'
                WHEN 'desirability_tier' THEN
                    $case$CASE
        WHEN ranked.__desirability_rank_for_calc IS NULL THEN NULL::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.05)) THEN 'S'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.15)) THEN 'A'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.30)) THEN 'B'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.50)) THEN 'C'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.75)) THEN 'D'::text
        ELSE 'F'::text
    END AS desirability_tier$case$
                WHEN 'desirability_scoring_version' THEN 'coalesce(ranked.desirability_scoring_version, ranked.__sdm_desirability_scoring_version) AS desirability_scoring_version'
                WHEN 'desirability_source_summary_id' THEN 'coalesce(ranked.desirability_source_summary_id, ranked.__sdm_desirability_source_summary_id) AS desirability_source_summary_id'
                WHEN 'desirability_source_table' THEN 'coalesce(ranked.desirability_source_table, ranked.__sdm_desirability_source_table) AS desirability_source_table'
                WHEN 'desirability_source_metric' THEN 'coalesce(ranked.desirability_source_metric, ranked.__sdm_desirability_source_metric) AS desirability_source_metric'
                WHEN 'desirability_is_fallback' THEN 'coalesce(ranked.desirability_is_fallback, ranked.__sdm_desirability_is_fallback) AS desirability_is_fallback'
                WHEN 'desirability_fallback_reason' THEN 'coalesce(ranked.desirability_fallback_reason, ranked.__sdm_desirability_fallback_reason) AS desirability_fallback_reason'
                ELSE format('ranked.%I', c.column_name)
            END,
            E',\n    ' ORDER BY c.ordinal_position
        )
        INTO base_cols_select
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = view_name;

        SELECT string_agg(
            CASE c
                WHEN 'desirability_score' THEN 'ranked.__desirability_score_for_calc AS desirability_score'
                WHEN 'relative_desirability_score' THEN
                    $case$CASE
        WHEN ranked.__desirability_score_for_calc IS NULL THEN NULL::numeric
        WHEN ranked.__max_desirability_score_for_calc <= ranked.__min_desirability_score_for_calc THEN 50::numeric
        ELSE (100.0 * ((ranked.__desirability_score_for_calc - ranked.__min_desirability_score_for_calc) / (ranked.__max_desirability_score_for_calc - ranked.__min_desirability_score_for_calc)))
    END AS relative_desirability_score$case$
                WHEN 'desirability_rank' THEN 'ranked.__desirability_rank_for_calc AS desirability_rank'
                WHEN 'desirability_tier' THEN
                    $case$CASE
        WHEN ranked.__desirability_rank_for_calc IS NULL THEN NULL::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.05)) THEN 'S'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.15)) THEN 'A'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.30)) THEN 'B'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.50)) THEN 'C'::text
        WHEN ranked.__desirability_rank_for_calc::numeric <= greatest(1::numeric, ceil(ranked.__desirability_ranked_count_for_calc::numeric * 0.75)) THEN 'D'::text
        ELSE 'F'::text
    END AS desirability_tier$case$
                WHEN 'desirability_scoring_version' THEN 'ranked.__sdm_desirability_scoring_version AS desirability_scoring_version'
                WHEN 'desirability_source_summary_id' THEN 'ranked.__sdm_desirability_source_summary_id AS desirability_source_summary_id'
                WHEN 'desirability_source_table' THEN 'ranked.__sdm_desirability_source_table AS desirability_source_table'
                WHEN 'desirability_source_metric' THEN 'ranked.__sdm_desirability_source_metric AS desirability_source_metric'
                WHEN 'desirability_is_fallback' THEN 'ranked.__sdm_desirability_is_fallback AS desirability_is_fallback'
                WHEN 'desirability_fallback_reason' THEN 'ranked.__sdm_desirability_fallback_reason AS desirability_fallback_reason'
            END,
            E',\n    '
        )
        INTO appended_select
        FROM unnest(missing_cols) AS c;

        SELECT regexp_replace(
            pg_get_viewdef(format('public.%I', view_name)::regclass, true),
            ';\s*$',
            ''
        )
        INTO current_view_def;

        create_sql := format(
$view$
CREATE OR REPLACE VIEW public.%I AS
WITH base AS (
%s
),
sdm AS (
    SELECT
        calculation_run_id,
        max(desirability_score) AS desirability_score,
        max(desirability_scoring_version) AS desirability_scoring_version,
        max(desirability_source_summary_id::text)::uuid AS desirability_source_summary_id,
        max(desirability_source_table) AS desirability_source_table,
        max(desirability_source_metric) AS desirability_source_metric,
        bool_or(desirability_is_fallback) AS desirability_is_fallback,
        max(desirability_fallback_reason) AS desirability_fallback_reason
    FROM public.simulation_derived_metrics
    GROUP BY calculation_run_id
),
joined AS (
    SELECT
        base.*,
        %s AS __desirability_score_for_calc,
        sdm.desirability_scoring_version AS __sdm_desirability_scoring_version,
        sdm.desirability_source_summary_id AS __sdm_desirability_source_summary_id,
        sdm.desirability_source_table AS __sdm_desirability_source_table,
        sdm.desirability_source_metric AS __sdm_desirability_source_metric,
        sdm.desirability_is_fallback AS __sdm_desirability_is_fallback,
        sdm.desirability_fallback_reason AS __sdm_desirability_fallback_reason
    FROM base
    LEFT JOIN sdm
        ON sdm.calculation_run_id = base.calculation_run_id
),
ranked AS (
    SELECT
        joined.*,
        CASE
            WHEN joined.__desirability_score_for_calc IS NULL THEN NULL::bigint
            ELSE rank() OVER (ORDER BY joined.__desirability_score_for_calc DESC NULLS LAST)
        END AS __desirability_rank_for_calc,
        count(joined.__desirability_score_for_calc) OVER () AS __desirability_ranked_count_for_calc,
        min(joined.__desirability_score_for_calc) OVER () AS __min_desirability_score_for_calc,
        max(joined.__desirability_score_for_calc) OVER () AS __max_desirability_score_for_calc
    FROM joined
)
SELECT
    %s,
    %s
FROM ranked
$view$,
            view_name,
            current_view_def,
            CASE
                WHEN has_desirability_score
                    THEN 'coalesce(base.desirability_score, sdm.desirability_score)'
                ELSE 'sdm.desirability_score'
            END,
            base_cols_select,
            appended_select
        );

        RAISE NOTICE 'Rewriting public.% for desirability passthrough with SQL: %', view_name, create_sql;
        EXECUTE create_sql;
    END LOOP;
END $$;
