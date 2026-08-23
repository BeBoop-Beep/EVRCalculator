-- Migration 20260823120000 - EV Representativeness research layer
-- (research_method_version = 'ev_representativeness_v1').
--
-- WHAT THIS ADDS
-- ==============
-- Four tables holding the output of a backend research layer that measures how
-- representative Expected Value is of the economic experience a real opener has
-- at the number of packs they actually open.
--
-- Nothing here is consumed by the public product. No publication gate, contract
-- audit, snapshot builder, leaderboard RPC or API reader touches these tables,
-- and none may until the research says a metric in here is defensible.
--
-- WHY FOUR TABLES AND NOT ONE, OR TWELVE
-- ======================================
-- The layer produces four genuinely different grains, and collapsing any two of
-- them would either bloat a hot row or force JSON digging in the analysis path:
--
--   run_summary          one row per (run, version)  - the scalar layer
--   curve                one row per (run, version, scope, pack count, metric)
--   card_contribution    one row per (run, version, sampling entity)
--   counterfactual       one row per (run, version, scenario)
--
-- `curve` is the only high-cardinality table (~22 sets x ~40 pack counts x ~25
-- metric keys). It is a TABLE rather than a JSONB blob specifically because the
-- cross-sectional analysis filters and joins on (pack_count, metric_key) - the
-- one access pattern JSONB would make expensive.
--
-- Conversely, the return-ratio buckets and the rarity-contribution breakdown are
-- JSONB columns on the summary rather than tables of their own: they are small,
-- always read whole, and never filtered on. A table per bucket would be
-- fragmentation for its own sake.
--
-- TIER A vs TIER B
-- ================
-- Tier A columns are derived from the exact persisted million-pack artifact
-- (`simulation_pack_outcome_artifacts`) and match the published EV/P50 exactly.
--
-- Tier B columns (prefixed `sim_`, plus the whole card_contribution table) come
-- from a SEEDED instrumented re-simulation, which is necessary because the
-- authoritative simulation is unseeded and records no per-card detail. Tier B is
-- an independent sample from the same model, so it differs from Tier A by Monte
-- Carlo error. That difference is PERSISTED - see the `reconciliation_*` columns
-- - rather than smoothed away, and card-level attribution is only marked
-- authoritative when the reconciliation z-test passes.
--
-- Every Tier B column is NULLABLE. A run analysed at Tier A only is a complete,
-- valid row with Tier B left NULL - never with a fabricated stand-in.
--
-- VERSIONING
-- ==========
-- `research_method_version` is part of every primary key, so a future
-- `ev_representativeness_v2` coexists with v1 rather than overwriting it and the
-- two remain comparable.
--
-- PRIVACY POSTURE
-- ===============
-- Backend-only, matching migrations 065/069/070: RLS enabled, no read policy, no
-- grants to `anon` or `authenticated`, full DML to `service_role`.
--
-- MANUAL APPLICATION
-- ==================
-- Follows this repository's convention: idempotent, safe to re-run, and NOT
-- applied to production by any automated process.

BEGIN;

-- =============================================================================
-- 1. Scalar layer - Parts 1-5, 7, 8, 13, 14, 25
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.ev_representativeness_run_summary (
    calculation_run_id      UUID NOT NULL
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    research_method_version TEXT NOT NULL,

    set_id           UUID NULL REFERENCES public.sets(id) ON DELETE SET NULL,
    set_canonical_key TEXT NULL,
    market_date      DATE NULL,

    -- ---- provenance (Part 26) -----------------------------------------------
    -- Enough to reproduce the row, and enough to explain it if it disagrees with
    -- something. `source_artifact_sha256` pins the EXACT outcome vector read.
    source_artifact_sha256 TEXT   NOT NULL,
    source_outcome_count   INTEGER NOT NULL CHECK (source_outcome_count > 0),
    pack_cost              NUMERIC NOT NULL CHECK (pack_cost > 0),
    simulation_engine_version TEXT NULL,
    session_model_version  TEXT   NOT NULL,
    session_seed           BIGINT NULL,
    session_count_coarse   INTEGER NULL,
    session_count_confirm  INTEGER NULL,
    metric_config          JSONB  NOT NULL,

    -- ---- Part 1: baseline distribution --------------------------------------
    sample_size              INTEGER NOT NULL,
    ev                       NUMERIC NOT NULL,
    variance                 NUMERIC NOT NULL,
    std_dev                  NUMERIC NOT NULL,
    coefficient_of_variation NUMERIC NULL,
    p10 NUMERIC NULL, p25 NUMERIC NULL, p50 NUMERIC NULL, p75 NUMERIC NULL,
    p90 NUMERIC NULL, p95 NUMERIC NULL, p99 NUMERIC NULL,

    -- ---- Part 2: EV vs Typical ----------------------------------------------
    -- typical_capture and relative_gap are algebraic complements (r = 1 - t).
    -- Both are stored because the report needs both readings and deriving one on
    -- the fly invites two callers rounding it differently.
    ev_typical_gap_absolute        NUMERIC NULL,
    ev_typical_gap_cost_normalized NUMERIC NULL,
    typical_capture                NUMERIC NULL,
    relative_gap                   NUMERIC NULL,

    -- ---- Part 3: skewness diagnostics (research only, never scored) ----------
    mean_abs_dev_about_median NUMERIC NULL,
    pearson_skew_2            NUMERIC NULL,
    groeneveld_meeden_skew    NUMERIC NULL,

    -- ---- Part 4: outcome-level tail concentration ---------------------------
    -- Rank-exact selection, reusing Financial RIP V3's TailBuckets rule; the
    -- contract version it was produced under is stamped so a future change to
    -- that rule is visible in the data.
    top10_outcome_ev_share NUMERIC NULL,
    top5_outcome_ev_share  NUMERIC NULL,
    top1_outcome_ev_share  NUMERIC NULL,
    top10_conditional_tail_mean NUMERIC NULL,
    top5_conditional_tail_mean  NUMERIC NULL,
    top1_conditional_tail_mean  NUMERIC NULL,
    tail_selection_method  TEXT NULL,

    -- ---- Part 5 / Part 8: small, always-read-whole blocks --------------------
    return_ratio_buckets_json  JSONB NULL,
    rarity_contributions_json  JSONB NULL,

    -- ---- Parts 6/7/9/10: Tier B, NULL until the re-simulation runs -----------
    sim_top_card_ev_share   NUMERIC NULL,
    sim_top5_card_ev_share  NUMERIC NULL,
    sim_top10_card_ev_share NUMERIC NULL,
    sim_card_hhi            NUMERIC NULL,
    sim_effective_card_count NUMERIC NULL,
    sim_card_count          INTEGER NULL,
    sim_pack_count          INTEGER NULL,
    sim_seed                BIGINT NULL,
    collective_hit_frequencies_json JSONB NULL,
    economic_hit_frequencies_json   JSONB NULL,

    -- ---- Tier A <-> Tier B reconciliation ------------------------------------
    -- The user requirement, made explicit in columns rather than buried in JSON:
    -- Tier A EV, Tier B EV, the absolute and relative difference, the quantile
    -- differences, and the z-scored verdict that gates whether card-level
    -- attribution may be treated as authoritative for this run.
    reconciliation_status         TEXT NULL,
    reconciliation_tier_a_ev      NUMERIC NULL,
    reconciliation_tier_b_ev      NUMERIC NULL,
    reconciliation_absolute_diff  NUMERIC NULL,
    reconciliation_relative_diff  NUMERIC NULL,
    reconciliation_z              NUMERIC NULL,
    reconciliation_z_tolerance    NUMERIC NULL,
    reconciliation_p50_diff       NUMERIC NULL,
    reconciliation_p50_relative_diff NUMERIC NULL,
    reconciliation_p95_diff       NUMERIC NULL,
    reconciliation_p95_relative_diff NUMERIC NULL,
    card_attribution_authoritative BOOLEAN NULL,

    -- ---- Parts 13/14: headline horizons -------------------------------------
    -- Promoted to columns so the cohort can be ranked without unpacking JSON.
    -- Column names stay parametric on purpose: no public metric name is being
    -- committed to at this phase.
    horizon_r80_c80_first_crossing   INTEGER NULL,
    horizon_r80_c80_stable           INTEGER NULL,
    horizon_r80_c80_status           TEXT NULL,
    horizon_tau20_c80_first_crossing INTEGER NULL,
    horizon_tau20_c80_stable         INTEGER NULL,
    horizon_tau20_c80_status         TEXT NULL,
    horizon_search_cap               INTEGER NULL,
    horizons_json                    JSONB NULL,

    -- ---- Part 25: CLT comparison --------------------------------------------
    clt_comparison_json JSONB NULL,

    -- ---- monotonicity audit (the brief's explicit warning) -------------------
    monotonicity_violation_count INTEGER NULL,
    monotonicity_max_decrease    NUMERIC NULL,
    monotonicity_json            JSONB NULL,

    diagnostics_json JSONB NULL,
    runtime_seconds  NUMERIC NULL,
    built_at         TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    CONSTRAINT ev_representativeness_run_summary_pkey
        PRIMARY KEY (calculation_run_id, research_method_version)
);

CREATE INDEX IF NOT EXISTS ev_representativeness_run_summary_market_date_idx
    ON public.ev_representativeness_run_summary (market_date DESC, research_method_version);
CREATE INDEX IF NOT EXISTS ev_representativeness_run_summary_set_idx
    ON public.ev_representativeness_run_summary (set_id, research_method_version);

COMMENT ON TABLE public.ev_representativeness_run_summary IS
    'EV Representativeness research: per-run scalar metrics. Backend research '
    'only - not consumed by any public product surface. Tier A columns come '
    'from the exact persisted pack-outcome artifact; sim_* columns come from a '
    'seeded research re-simulation and are NULL until it runs.';

COMMENT ON COLUMN public.ev_representativeness_run_summary.reconciliation_z IS
    'z = (tier_b_ev - tier_a_ev) / (sigma * sqrt(1/n_a + 1/n_b)). Tier A and '
    'Tier B are independent estimates of the same mean, so this is standard '
    'normal when the re-simulation reproduces the authoritative configuration. '
    'Scales with each set volatility automatically, unlike a fixed dollar or '
    'percentage tolerance.';

COMMENT ON COLUMN public.ev_representativeness_run_summary.card_attribution_authoritative IS
    'FALSE when the Tier B distribution failed the reconciliation tolerance '
    'against its Tier A artifact. Card-level rows are still written for audit, '
    'but must not be read as this run''s decomposition.';

-- =============================================================================
-- 2. Finite-sample curves - Parts 11, 12, 16, 17, 22
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.ev_representativeness_curve (
    calculation_run_id      UUID NOT NULL
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    research_method_version TEXT NOT NULL,

    -- 'pack_grid' for the research grid; 'product' for a real SKU evaluated at
    -- its own pack count and its own market cost.
    scope_kind        TEXT NOT NULL CHECK (scope_kind IN ('pack_grid', 'product')),
    -- The all-zero UUID is the sentinel for pack_grid rows. A nullable column
    -- cannot carry a primary key, and a partial unique index would let a NULL
    -- and a non-NULL row collide on rerun, which is exactly the duplicate this
    -- table must not accumulate.
    sealed_product_key UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',

    pack_count  INTEGER NOT NULL CHECK (pack_count >= 1),
    metric_key  TEXT NOT NULL,

    estimate    NUMERIC NOT NULL,
    session_count INTEGER NOT NULL CHECK (session_count > 0),
    -- NULL for non-probability metrics (session percentiles, ratios, costs).
    successes   INTEGER NULL,
    monte_carlo_standard_error NUMERIC NULL,
    ci_lower    NUMERIC NULL,
    ci_upper    NUMERIC NULL,
    ci_method   TEXT NULL,
    stage       TEXT NOT NULL CHECK (stage IN ('coarse', 'refine', 'confirm')),
    seed        BIGINT NULL,
    built_at    TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    CONSTRAINT ev_representativeness_curve_pkey
        PRIMARY KEY (calculation_run_id, research_method_version, scope_kind,
                     sealed_product_key, pack_count, metric_key, stage),
    CONSTRAINT ev_representativeness_curve_successes_bounds
        CHECK (successes IS NULL OR (successes >= 0 AND successes <= session_count))
);

CREATE INDEX IF NOT EXISTS ev_representativeness_curve_metric_idx
    ON public.ev_representativeness_curve (research_method_version, metric_key, pack_count);
CREATE INDEX IF NOT EXISTS ev_representativeness_curve_product_idx
    ON public.ev_representativeness_curve (sealed_product_key)
    WHERE scope_kind = 'product';

COMMENT ON TABLE public.ev_representativeness_curve IS
    'EV Representativeness research: one estimate per (pack count, metric, '
    'stage). Probability rows carry a Wilson 95% interval; distribution rows '
    'carry a point value with NULL successes. `stage` is part of the key so a '
    'confirmation-stage estimate does not overwrite the coarse curve that '
    'located it - the difference between them is itself a research result.';

-- =============================================================================
-- 3. Card-level contribution - Part 6 (Tier B only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.ev_representativeness_card_contribution (
    calculation_run_id      UUID NOT NULL
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    research_method_version TEXT NOT NULL,

    -- The sampling ENTITY, not the card: one card is two distinct draws if it
    -- can be pulled at both its normal and its reverse price.
    source_row_index INTEGER NOT NULL,
    price_column     TEXT NOT NULL,

    card_name   TEXT NULL,
    card_number TEXT NULL,
    rarity_key  TEXT NULL,

    price_used               NUMERIC NULL,
    observed_pull_count      BIGINT  NULL,
    expected_copies_per_pack NUMERIC NULL,
    ev_contribution_per_pack NUMERIC NULL,
    ev_share                 NUMERIC NULL,
    ev_rank                  INTEGER NULL,
    sim_pack_count           INTEGER NULL,
    built_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    CONSTRAINT ev_representativeness_card_contribution_pkey
        PRIMARY KEY (calculation_run_id, research_method_version,
                     source_row_index, price_column)
);

CREATE INDEX IF NOT EXISTS ev_representativeness_card_contribution_rank_idx
    ON public.ev_representativeness_card_contribution
       (calculation_run_id, research_method_version, ev_rank);

COMMENT ON TABLE public.ev_representativeness_card_contribution IS
    'EV Representativeness research: measured expected copies per pack and EV '
    'contribution per card, from a seeded instrumented re-simulation. This is '
    'NOT simulation_input_cards.ev_contribution, which is the analytic model '
    'Price/Effective_Pull_Rate and was measured 47% below the simulator mean. '
    'Only trustworthy for runs whose summary row has '
    'card_attribution_authoritative = TRUE.';

-- =============================================================================
-- 4. Counterfactuals - Parts 18, 19 (Tier B only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.ev_representativeness_counterfactual (
    calculation_run_id      UUID NOT NULL
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    research_method_version TEXT NOT NULL,
    scenario_key            TEXT NOT NULL,

    scenario_family TEXT NOT NULL,
    scenario_params JSONB NOT NULL,

    ev      NUMERIC NULL,
    p50     NUMERIC NULL,
    p95     NUMERIC NULL,
    std_dev NUMERIC NULL,
    coefficient_of_variation NUMERIC NULL,
    ev_typical_gap_absolute  NUMERIC NULL,
    typical_capture          NUMERIC NULL,
    top1_outcome_ev_share    NUMERIC NULL,
    top5_outcome_ev_share    NUMERIC NULL,
    top10_outcome_ev_share   NUMERIC NULL,

    delta_vs_baseline JSONB NULL,
    -- Always 'tier_b_paired': scenarios re-value the SAME sampled openings as
    -- the baseline, so the delta contains no resampling noise at all.
    baseline_kind TEXT NOT NULL DEFAULT 'tier_b_paired',
    built_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    CONSTRAINT ev_representativeness_counterfactual_pkey
        PRIMARY KEY (calculation_run_id, research_method_version, scenario_key)
);

CREATE INDEX IF NOT EXISTS ev_representativeness_counterfactual_family_idx
    ON public.ev_representativeness_counterfactual
       (research_method_version, scenario_family);

COMMENT ON TABLE public.ev_representativeness_counterfactual IS
    'EV Representativeness research: rarity ablation, top-card ablation, tail '
    'winsorization and chase price-shock scenarios. Counterfactual arithmetic '
    'on a copy of the run price vector - no market price is ever written back.';

-- =============================================================================
-- 5. Access posture - backend only
-- =============================================================================

ALTER TABLE public.ev_representativeness_run_summary        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ev_representativeness_curve              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ev_representativeness_card_contribution  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ev_representativeness_counterfactual     ENABLE ROW LEVEL SECURITY;

-- Stated explicitly so re-running leaves the intended state even if something
-- created a policy out of band.
DROP POLICY IF EXISTS ev_representativeness_run_summary_read_policy
    ON public.ev_representativeness_run_summary;
DROP POLICY IF EXISTS ev_representativeness_curve_read_policy
    ON public.ev_representativeness_curve;
DROP POLICY IF EXISTS ev_representativeness_card_contribution_read_policy
    ON public.ev_representativeness_card_contribution;
DROP POLICY IF EXISTS ev_representativeness_counterfactual_read_policy
    ON public.ev_representativeness_counterfactual;

REVOKE ALL ON public.ev_representativeness_run_summary       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ev_representativeness_curve             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ev_representativeness_card_contribution FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ev_representativeness_counterfactual    FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.ev_representativeness_run_summary       TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.ev_representativeness_curve             TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.ev_representativeness_card_contribution TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.ev_representativeness_counterfactual    TO service_role;

COMMIT;
