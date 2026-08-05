-- Migration 060: additive Financial RIP V3 outcome-profile metrics.
--
-- WHAT THIS ADDS
-- --------------
-- Financial RIP V3 is a financial-only, pack-level score computed entirely from
-- the simulated per-pack value vector X and the pack cost C that simulation ran
-- against:
--
--     Financial RIP V3 = 25% True Win Frequency
--                      + 20% Typical Retention
--                      + 15% Loss Resilience
--                      + 25% Realistic Upside
--                      + 10% Jackpot Upside
--                      +  5% Base Economic Efficiency
--
-- Two storage shapes are persisted side by side, on purpose:
--   1. SORTABLE SCALAR COLUMNS, for the ranking read path, SQL auditing and the
--      cheap API projection. Ranking on a JSONB expression would need a
--      functional index and would make every read path re-parse a document.
--   2. The COMPLETE JSONB audit payload (`financial_rip_v3_payload`), which
--      carries the sub-scores, the normalization records (raw value, transform
--      version, breakpoints, clip status) and the exact empirical tail-selection
--      record. The scalars are a projection OF this document, never a separate
--      source of truth.
--
-- STRICTLY ADDITIVE
-- -----------------
-- Nothing here drops, renames, repurposes or changes the meaning of an existing
-- column. Financial RIP V2's `pack_score` / `profit_score` / `safety_score` /
-- `stability_score` / `desirability_score` / `score_version` keep their exact
-- current semantics and keep being written by the same code path. Historical
-- rows remain valid with NULL V3 fields.
--
-- NO BACKFILL IS POSSIBLE FROM STORED PERCENTILES
-- -----------------------------------------------
-- V3's Realistic Upside and Jackpot Upside need CONDITIONAL MEANS over exact
-- empirical rank buckets (the mean of the 95th-99th percentile band, and the
-- mean of the top 1%). Those cannot be reconstructed from P50/P95/P99 - a
-- percentile is a threshold, and no arithmetic over thresholds recovers the mean
-- of the mass above one. A historical row may only be backfilled when the
-- ORIGINAL outcome vector is genuinely available; otherwise its V3 fields stay
-- NULL and the set is reported as requiring a simulation rerun. Approximating
-- these values would publish a number that looks like a measurement and is not.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process. Apply with the
-- same procedure used for migrations 047-059.

-- ---------------------------------------------------------------------------
-- 1. Scalar columns
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS public.simulation_derived_metrics
    -- Headline score and identity -------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_score NUMERIC
        CHECK (financial_rip_v3_score IS NULL OR financial_rip_v3_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_score_version TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_normalization_version TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_status TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_simulation_count INTEGER
        CHECK (financial_rip_v3_simulation_count IS NULL OR financial_rip_v3_simulation_count >= 0),

    -- The six component scores ----------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_true_win_frequency_score NUMERIC
        CHECK (financial_rip_v3_true_win_frequency_score IS NULL
               OR financial_rip_v3_true_win_frequency_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_typical_retention_score NUMERIC
        CHECK (financial_rip_v3_typical_retention_score IS NULL
               OR financial_rip_v3_typical_retention_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_loss_resilience_score NUMERIC
        CHECK (financial_rip_v3_loss_resilience_score IS NULL
               OR financial_rip_v3_loss_resilience_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_realistic_upside_score NUMERIC
        CHECK (financial_rip_v3_realistic_upside_score IS NULL
               OR financial_rip_v3_realistic_upside_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_jackpot_upside_score NUMERIC
        CHECK (financial_rip_v3_jackpot_upside_score IS NULL
               OR financial_rip_v3_jackpot_upside_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_base_economic_efficiency_score NUMERIC
        CHECK (financial_rip_v3_base_economic_efficiency_score IS NULL
               OR financial_rip_v3_base_economic_efficiency_score BETWEEN 0 AND 100),

    -- True Win Frequency raw -------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_true_win_probability NUMERIC
        CHECK (financial_rip_v3_true_win_probability IS NULL
               OR financial_rip_v3_true_win_probability BETWEEN 0 AND 1),

    -- Typical Retention raw --------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_typical_pack_value NUMERIC,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_typical_retention_ratio NUMERIC
        CHECK (financial_rip_v3_typical_retention_ratio IS NULL
               OR financial_rip_v3_typical_retention_ratio >= 0),

    -- Loss Resilience raw ----------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_average_retention_given_loss NUMERIC
        CHECK (financial_rip_v3_average_retention_given_loss IS NULL
               OR financial_rip_v3_average_retention_given_loss BETWEEN 0 AND 1),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_soft_loss_share_given_loss NUMERIC
        CHECK (financial_rip_v3_soft_loss_share_given_loss IS NULL
               OR financial_rip_v3_soft_loss_share_given_loss BETWEEN 0 AND 1),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_hard_loss_probability NUMERIC
        CHECK (financial_rip_v3_hard_loss_probability IS NULL
               OR financial_rip_v3_hard_loss_probability BETWEEN 0 AND 1),

    -- Realistic Upside raw ---------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_p95_threshold_value NUMERIC,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_p95_threshold_ratio NUMERIC
        CHECK (financial_rip_v3_p95_threshold_ratio IS NULL
               OR financial_rip_v3_p95_threshold_ratio >= 0),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_realistic_tail_mean_value NUMERIC,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_realistic_tail_mean_ratio NUMERIC
        CHECK (financial_rip_v3_realistic_tail_mean_ratio IS NULL
               OR financial_rip_v3_realistic_tail_mean_ratio >= 0),

    -- Jackpot Upside raw -----------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_p99_threshold_value NUMERIC,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_p99_threshold_ratio NUMERIC
        CHECK (financial_rip_v3_p99_threshold_ratio IS NULL
               OR financial_rip_v3_p99_threshold_ratio >= 0),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_jackpot_tail_mean_value NUMERIC,
    ADD COLUMN IF NOT EXISTS financial_rip_v3_jackpot_tail_mean_ratio NUMERIC
        CHECK (financial_rip_v3_jackpot_tail_mean_ratio IS NULL
               OR financial_rip_v3_jackpot_tail_mean_ratio >= 0),

    -- Base Economic Efficiency raw ------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_total_rtp_ratio NUMERIC
        CHECK (financial_rip_v3_total_rtp_ratio IS NULL OR financial_rip_v3_total_rtp_ratio >= 0),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_base_rtp_excluding_top_1pct NUMERIC
        CHECK (financial_rip_v3_base_rtp_excluding_top_1pct IS NULL
               OR financial_rip_v3_base_rtp_excluding_top_1pct >= 0),
    ADD COLUMN IF NOT EXISTS financial_rip_v3_jackpot_value_share NUMERIC
        CHECK (financial_rip_v3_jackpot_value_share IS NULL
               OR financial_rip_v3_jackpot_value_share BETWEEN 0 AND 1),

    -- Depth and Robustness (UNWEIGHTED diagnostic) ---------------------------
    -- Top-1/3/5 EV shares already exist. Top-2 is new: it is what separates a
    -- genuine one-card set from a two-card set, which top-1 and top-3 alone
    -- cannot distinguish.
    ADD COLUMN IF NOT EXISTS top2_ev_share NUMERIC
        CHECK (top2_ev_share IS NULL OR top2_ev_share BETWEEN 0 AND 1),

    -- Complete audit document ------------------------------------------------
    ADD COLUMN IF NOT EXISTS financial_rip_v3_payload JSONB;

-- ---------------------------------------------------------------------------
-- 2. Consistency constraint
-- ---------------------------------------------------------------------------
-- A row that claims status='ready' must actually carry a score and all six
-- component scores. A partially-populated "ready" V3 row is exactly the failure
-- this constraint exists to make impossible: it would rank, it would render, and
-- it would be wrong. Anything other than 'ready' is unconstrained so an
-- unavailable row can be stored with its reason and NULL numerics.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'simulation_derived_metrics_financial_rip_v3_ready_complete'
    ) THEN
        ALTER TABLE public.simulation_derived_metrics
            ADD CONSTRAINT simulation_derived_metrics_financial_rip_v3_ready_complete
            CHECK (
                financial_rip_v3_status IS DISTINCT FROM 'ready'
                OR (
                    financial_rip_v3_score IS NOT NULL
                    AND financial_rip_v3_score_version IS NOT NULL
                    AND financial_rip_v3_normalization_version IS NOT NULL
                    AND financial_rip_v3_true_win_frequency_score IS NOT NULL
                    AND financial_rip_v3_typical_retention_score IS NOT NULL
                    AND financial_rip_v3_loss_resilience_score IS NOT NULL
                    AND financial_rip_v3_realistic_upside_score IS NOT NULL
                    AND financial_rip_v3_jackpot_upside_score IS NOT NULL
                    AND financial_rip_v3_base_economic_efficiency_score IS NOT NULL
                    AND financial_rip_v3_payload IS NOT NULL
                )
            )
            NOT VALID;
    END IF;
END
$$;

-- Existing historical rows all have financial_rip_v3_status IS NULL, so they
-- satisfy the constraint. Validating separately keeps the ALTER lock short.
DO $$
BEGIN
    ALTER TABLE public.simulation_derived_metrics
        VALIDATE CONSTRAINT simulation_derived_metrics_financial_rip_v3_ready_complete;
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Could not validate financial_rip_v3 ready-completeness constraint: %', SQLERRM;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Indexes
-- ---------------------------------------------------------------------------
-- Only indexes that back a REAL read path:
--   * the canonical Financial RIP V3 ranking (ORDER BY score DESC),
--   * the freshness/completeness audit, which filters by score version.

CREATE INDEX IF NOT EXISTS idx_simulation_derived_metrics_financial_rip_v3_score
    ON public.simulation_derived_metrics(financial_rip_v3_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_simulation_derived_metrics_financial_rip_v3_version
    ON public.simulation_derived_metrics(financial_rip_v3_score_version)
    WHERE financial_rip_v3_score_version IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. Column comments
-- ---------------------------------------------------------------------------

COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_score IS
    'Financial RIP V3 absolute score (0-100), fixed-anchor normalization. Adding or removing another set NEVER changes this value.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_score_version IS
    'Expected: financial_rip_v3_outcome_profile_25_20_15_25_10_5. Distinct from rip_v3_weighted_four_component, which names a different historical model.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_normalization_version IS
    'Fixed-transform version, e.g. financial_rip_v3_fixed_absolute_piecewise_v1. Bump when any anchor changes.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_status IS
    'ready | unavailable. Never a partially-populated ready row - see the ready-completeness constraint.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_rankable IS
    'False whenever a required V3 metric was unavailable. An unrankable row is excluded from the canonical V3 ranking rather than scored as neutral.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_true_win_probability IS
    'P(pack value >= pack cost). A tie at exactly pack cost counts as a true win because it recovers cost.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_typical_pack_value IS
    'P50 of the simulated pack value. The TYPICAL pack, not a floor.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_average_retention_given_loss IS
    'E[value/cost | value < cost]. Loss Resilience input; P05 carries zero V3 weight.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_hard_loss_probability IS
    'Unconditional P(value/cost < 0.50). Disclosed only - deliberately NOT a weighted subcomponent, to avoid double-counting the same distribution buckets.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_p95_threshold_value IS
    'Q95 of pack value: where the top 5% BEGINS. A threshold, not an average.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_realistic_tail_mean_value IS
    'Mean of the 95th-to-99th percentile band, selected by exact empirical rank (empirical_rank_exact_mass_v1). EXCLUDES the top 1%. Not reconstructible from stored percentiles.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_jackpot_tail_mean_value IS
    'Mean of the top 1% of outcomes, selected by exact empirical rank. Not reconstructible from stored percentiles.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_total_rtp_ratio IS
    'mean(pack value) / pack cost. DISCLOSURE ONLY - Base Economic Efficiency scores the top-1%-excluded RTP instead.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_base_rtp_excluding_top_1pct IS
    'Mean of all outcomes outside the top 1% / pack cost. The SCORED Base Economic Efficiency input; stops one extreme chase from making ordinary opening economics look stronger than they are.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_jackpot_value_share IS
    'Share of all simulated value carried by the top 1% of packs.';
COMMENT ON COLUMN public.simulation_derived_metrics.top2_ev_share IS
    'Top-2 card EV share. Depth and Robustness diagnostic only; carries no Financial RIP V3 weight.';
COMMENT ON COLUMN public.simulation_derived_metrics.financial_rip_v3_payload IS
    'Complete Financial RIP V3 audit document: component sub-scores, per-metric normalization records (raw value, transform, breakpoints, clip status), exact tail-selection record, depth and robustness, distribution disclosures. The scalar columns are a projection of this document.';

-- ---------------------------------------------------------------------------
-- 5. Read-path passthrough on explore_rip_statistics_latest
-- ---------------------------------------------------------------------------
-- The explore/ranking read path selects from this view, not from the base table,
-- so the V3 columns must be exposed there or the canonical ranking cannot see
-- them. The view is wrapped rather than rewritten by hand: its current
-- definition is preserved verbatim as `base` and the V3 columns are LEFT JOINed
-- on calculation_run_id. Every added column is a plain passthrough - no ranking,
-- no min-max, no tiering happens in SQL, because V3 ranks are computed in the
-- Python publication layer against the fixed public cohort.

DO $$
DECLARE
    v3_cols text[] := ARRAY[
        'financial_rip_v3_score',
        'financial_rip_v3_score_version',
        'financial_rip_v3_normalization_version',
        'financial_rip_v3_status',
        'financial_rip_v3_rankable',
        'financial_rip_v3_simulation_count',
        'financial_rip_v3_true_win_frequency_score',
        'financial_rip_v3_typical_retention_score',
        'financial_rip_v3_loss_resilience_score',
        'financial_rip_v3_realistic_upside_score',
        'financial_rip_v3_jackpot_upside_score',
        'financial_rip_v3_base_economic_efficiency_score',
        'financial_rip_v3_true_win_probability',
        'financial_rip_v3_typical_pack_value',
        'financial_rip_v3_typical_retention_ratio',
        'financial_rip_v3_average_retention_given_loss',
        'financial_rip_v3_soft_loss_share_given_loss',
        'financial_rip_v3_hard_loss_probability',
        'financial_rip_v3_p95_threshold_value',
        'financial_rip_v3_p95_threshold_ratio',
        'financial_rip_v3_realistic_tail_mean_value',
        'financial_rip_v3_realistic_tail_mean_ratio',
        'financial_rip_v3_p99_threshold_value',
        'financial_rip_v3_p99_threshold_ratio',
        'financial_rip_v3_jackpot_tail_mean_value',
        'financial_rip_v3_jackpot_tail_mean_ratio',
        'financial_rip_v3_total_rtp_ratio',
        'financial_rip_v3_base_rtp_excluding_top_1pct',
        'financial_rip_v3_jackpot_value_share',
        'top2_ev_share',
        'financial_rip_v3_payload'
    ];
    view_name text;
    col_name text;
    missing_cols text[];
    base_cols_select text;
    appended_select text;
    sdm_select text;
    current_view_def text;
    create_sql text;
BEGIN
    FOREACH view_name IN ARRAY ARRAY[
        'simulation_latest_by_target',
        'explore_rip_statistics_latest'
    ] LOOP
        IF to_regclass(format('public.%I', view_name)) IS NULL THEN
            RAISE NOTICE 'View public.% does not exist; skipping Financial RIP V3 passthrough', view_name;
            CONTINUE;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = view_name
              AND c.column_name = 'calculation_run_id'
        ) THEN
            RAISE EXCEPTION 'View public.% must expose calculation_run_id before Financial RIP V3 passthrough can be added', view_name;
        END IF;

        missing_cols := ARRAY[]::text[];
        FOREACH col_name IN ARRAY v3_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name = view_name
                  AND c.column_name = col_name
            ) THEN
                missing_cols := array_append(missing_cols, col_name);
            END IF;
        END LOOP;

        IF coalesce(array_length(missing_cols, 1), 0) = 0 THEN
            RAISE NOTICE 'public.% already exposes the Financial RIP V3 columns', view_name;
            CONTINUE;
        END IF;

        SELECT string_agg(format('base.%I', c.column_name), E',\n    ' ORDER BY c.ordinal_position)
        INTO base_cols_select
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = view_name;

        SELECT string_agg(format('v3.%I AS %I', c, c), E',\n    ')
        INTO appended_select
        FROM unnest(missing_cols) AS c;

        -- One derived-metrics row per calculation run is the norm, but the
        -- aggregate makes the join total regardless, exactly as migration 029
        -- does for the desirability passthrough.
        SELECT string_agg(
            CASE
                WHEN c = 'financial_rip_v3_rankable' THEN format('bool_or(%I) AS %I', c, c)
                WHEN c = 'financial_rip_v3_payload' THEN format('(array_agg(%I ORDER BY %I NULLS LAST))[1] AS %I', c, c, c)
                WHEN c IN (
                    'financial_rip_v3_score_version',
                    'financial_rip_v3_normalization_version',
                    'financial_rip_v3_status'
                ) THEN format('max(%I) AS %I', c, c)
                ELSE format('max(%I) AS %I', c, c)
            END,
            E',\n        '
        )
        INTO sdm_select
        FROM unnest(v3_cols) AS c;

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
v3 AS (
    SELECT
        calculation_run_id,
        %s
    FROM public.simulation_derived_metrics
    GROUP BY calculation_run_id
)
SELECT
    %s,
    %s
FROM base
LEFT JOIN v3 ON v3.calculation_run_id = base.calculation_run_id
$view$,
            view_name,
            current_view_def,
            sdm_select,
            base_cols_select,
            appended_select
        );

        EXECUTE create_sql;
        RAISE NOTICE 'Added Financial RIP V3 passthrough to public.%: %', view_name, missing_cols;
    END LOOP;
END
$$;
