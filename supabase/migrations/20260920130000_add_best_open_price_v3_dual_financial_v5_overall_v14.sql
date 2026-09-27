-- Best-Open Price V3: persist Financial RIP V5 + Overall RIP V14 thresholds.
--
-- MUST APPLY AFTER 20260916120000_add_best_open_price_v2_dual_threshold.sql (the V2
-- dual-threshold migration, currently unapplied in production). It uses the
-- financial_status / financial_best_open_price / ... columns that V2 introduced and
-- renames the function that V2 defines. Applied to a V1-only database first it fails
-- loudly on the missing V2 columns; it never duplicates V2 schema.
--
-- STRICTLY ADDITIVE / VERSION-PRESERVING
--   * V1/V2 columns keep their names and meaning; historical rows are untouched.
--   * V3 evidence lives in explicitly V5/V14-named columns. Nothing V5/V14 is ever
--     written to a *_v4_* / *_v12_* column.
--   * benchmark_overall_rip_v12_score / benchmark_financial_rip_v4_score (NOT NULL in V1)
--     become NULLABLE so a V3 row is not forced to carry a V12/V4 value; a row-shape
--     CHECK makes each row EITHER fully legacy-shaped OR fully V3-shaped, and the
--     unchanged V1/V2 body still refuses NULLs in those columns.
--   * overall_rip_v12_version on the snapshot becomes NULLABLE for the same reason;
--     V3 snapshots carry overall_rip_v14_version instead (financial_rip_version holds
--     the V5 identity). A snapshot-shape CHECK enforces the split.
--   * The published function is renamed, not rewritten: the V1/V2 body keeps running
--     verbatim behind a thin dispatcher; the V3 branch is a separate private function.
--     V1, V2 and V3 use distinct latest pointers (keyed by method version).
--
-- V3 must be sourced from a budget_product_ranking_v2 snapshot: the branch validates
-- every row against the LIVE Ranking V2 rows (ranks, scores, P(win), capital,
-- benchmark identity) and refuses V1/V12 sources.
--
-- SECURITY: RLS/grants unchanged. Only the dispatcher is executable, by service_role
-- only; the V1/V2 body and the V3 branch are internal (no grants to any API role).
--
-- ROLLBACK: drop the V3 columns/constraints, restore NOT NULL on the two benchmark
-- columns and overall_rip_v12_version (valid only once no V3 rows exist), and rename
-- publish_budget_product_best_open_price_snapshot_v1_v2 back.

BEGIN;

ALTER TABLE public.budget_product_best_open_price_snapshots
    ADD COLUMN overall_rip_v14_version TEXT,
    ALTER COLUMN overall_rip_v12_version DROP NOT NULL;

ALTER TABLE public.budget_product_best_open_price_snapshots
    ADD CONSTRAINT budget_best_open_snapshots_authority_shape CHECK (
        (best_open_price_method_version = 'budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14'
            AND overall_rip_v14_version IS NOT NULL AND overall_rip_v12_version IS NULL)
        OR
        (best_open_price_method_version <> 'budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14'
            AND overall_rip_v12_version IS NOT NULL AND overall_rip_v14_version IS NULL)
    ) NOT VALID;
ALTER TABLE public.budget_product_best_open_price_snapshots
    VALIDATE CONSTRAINT budget_best_open_snapshots_authority_shape;

ALTER TABLE public.budget_product_best_open_price_rows
    ADD COLUMN current_overall_rip_v14_score NUMERIC,
    ADD COLUMN current_financial_rip_v5_score NUMERIC,
    ADD COLUMN current_financial_only_rank_v5 INTEGER
        CHECK (current_financial_only_rank_v5 IS NULL OR current_financial_only_rank_v5 >= 1),
    ADD COLUMN benchmark_overall_rip_v14_score NUMERIC,
    ADD COLUMN benchmark_financial_rip_v5_score NUMERIC,
    ADD COLUMN threshold_financial_rip_v5_score NUMERIC,
    ADD COLUMN threshold_overall_rip_v14_score NUMERIC,
    ADD COLUMN financial_benchmark_financial_rip_v5_score NUMERIC,
    ADD COLUMN financial_benchmark_overall_rip_v14_score NUMERIC,
    ADD COLUMN financial_threshold_financial_rip_v5_score NUMERIC,
    ADD COLUMN financial_threshold_overall_rip_v14_score NUMERIC,
    -- Exact-search evidence the engine established (threshold cent wins; the next legal
    -- cent loses). SQL cannot re-run the search, so the flags are persisted and the
    -- publication branch requires both TRUE.
    ADD COLUMN threshold_exact_verified BOOLEAN,
    ADD COLUMN financial_threshold_exact_verified BOOLEAN;

ALTER TABLE public.budget_product_best_open_price_rows
    ALTER COLUMN benchmark_overall_rip_v12_score DROP NOT NULL,
    ALTER COLUMN benchmark_financial_rip_v4_score DROP NOT NULL;

ALTER TABLE public.budget_product_best_open_price_rows
    ADD CONSTRAINT budget_best_open_rows_authority_shape CHECK (
        -- Legacy (V1/V2) row: V12/V4 benchmark evidence present, no V5/V14 field.
        (benchmark_overall_rip_v12_score IS NOT NULL AND benchmark_financial_rip_v4_score IS NOT NULL
            AND current_overall_rip_v14_score IS NULL AND current_financial_rip_v5_score IS NULL
            AND current_financial_only_rank_v5 IS NULL AND benchmark_overall_rip_v14_score IS NULL
            AND benchmark_financial_rip_v5_score IS NULL AND threshold_financial_rip_v5_score IS NULL
            AND threshold_overall_rip_v14_score IS NULL AND financial_benchmark_financial_rip_v5_score IS NULL
            AND financial_benchmark_overall_rip_v14_score IS NULL
            AND financial_threshold_financial_rip_v5_score IS NULL
            AND financial_threshold_overall_rip_v14_score IS NULL
            AND threshold_exact_verified IS NULL AND financial_threshold_exact_verified IS NULL)
        OR
        -- V3 row: every V5/V14 field set, no V4/V12-named field set.
        (current_overall_rip_v12_score IS NULL AND current_financial_rip_v4_score IS NULL
            AND current_financial_only_rank IS NULL
            AND benchmark_overall_rip_v12_score IS NULL AND benchmark_financial_rip_v4_score IS NULL
            AND threshold_financial_rip_v4_score IS NULL AND threshold_overall_rip_v12_score IS NULL
            AND financial_benchmark_financial_rip_v4_score IS NULL
            AND financial_benchmark_overall_rip_v12_score IS NULL
            AND financial_threshold_financial_rip_v4_score IS NULL
            AND financial_threshold_overall_rip_v12_score IS NULL
            AND current_overall_rip_v14_score IS NOT NULL AND current_financial_rip_v5_score IS NOT NULL
            AND current_financial_only_rank_v5 IS NOT NULL
            AND benchmark_overall_rip_v14_score IS NOT NULL AND benchmark_financial_rip_v5_score IS NOT NULL
            AND threshold_financial_rip_v5_score IS NOT NULL AND threshold_overall_rip_v14_score IS NOT NULL
            AND financial_benchmark_financial_rip_v5_score IS NOT NULL
            AND financial_benchmark_overall_rip_v14_score IS NOT NULL
            AND financial_threshold_financial_rip_v5_score IS NOT NULL
            AND financial_threshold_overall_rip_v14_score IS NOT NULL
            AND threshold_exact_verified IS TRUE AND financial_threshold_exact_verified IS TRUE
            AND financial_status IS NOT NULL AND financial_best_open_price IS NOT NULL)
    ) NOT VALID;
ALTER TABLE public.budget_product_best_open_price_rows
    VALIDATE CONSTRAINT budget_best_open_rows_authority_shape;

ALTER FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB)
    RENAME TO publish_budget_product_best_open_price_snapshot_v1_v2;
REVOKE ALL ON FUNCTION public.publish_budget_product_best_open_price_snapshot_v1_v2(JSONB, JSONB)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.publish_budget_product_best_open_price_snapshot_v3(
    p_snapshot JSONB, p_rows JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, extensions, pg_temp
AS $$
DECLARE
    v_id UUID;
    v_existing_id UUID;
    v_row_count INTEGER;
    v_distinct_rows INTEGER;
    v_live_snapshot RECORD;
    v_content_fingerprint TEXT;
    v_candidate_source_id UUID;
    v_locked_pointer_id UUID;
    v_live_count INTEGER;
    v_incoming_content JSONB;
    v_stored_content JSONB;
BEGIN
    IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'best-open-price snapshot must be an object';
    END IF;
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'best-open-price rows must be an array';
    END IF;
    v_row_count := jsonb_array_length(p_rows);
    IF v_row_count = 0 THEN
        RAISE EXCEPTION 'refusing to publish an empty best-open-price snapshot';
    END IF;

    -- Exact model/method identities. The source MUST be a Ranking V2 snapshot.
    IF p_snapshot->>'best_open_price_method_version' IS DISTINCT FROM 'budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14'
       OR p_snapshot->>'ranking_method_version' IS DISTINCT FROM 'budget_product_ranking_v2'
       OR p_snapshot->>'allocation_method_version' IS DISTINCT FROM 'budget_allocation_floor_quantity_v1'
       OR p_snapshot->>'comparison_scope_version' IS DISTINCT FROM 'budget_constrained_whole_unit_cross_format_v1'
       OR p_snapshot->>'financial_rip_version' IS DISTINCT FROM 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
       OR p_snapshot->>'overall_rip_v14_version' IS DISTINCT FROM 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
       OR p_snapshot->>'collector_appeal_version' IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
       OR p_snapshot->>'chase_accessibility_version' IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
       OR p_snapshot->>'chase_accessibility_transform_version' IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002' THEN
        RAISE EXCEPTION 'Best-Open V3 snapshot authority metadata is missing or mismatched';
    END IF;
    IF p_snapshot ? 'overall_rip_v12_version' THEN
        RAISE EXCEPTION 'Best-Open V3 snapshot must not carry V12 authority fields';
    END IF;

    IF (p_snapshot->>'runtime_seconds')::NUMERIC IS NULL
       OR (p_snapshot->>'runtime_seconds')::NUMERIC < 0
       OR (p_snapshot->>'runtime_seconds')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
       OR NULLIF(p_snapshot->>'source_full_market_row_fingerprint','') IS NULL THEN
        RAISE EXCEPTION 'invalid snapshot timing/source fingerprint';
    END IF;

    SELECT count(*) INTO v_distinct_rows FROM (
        SELECT DISTINCT row->>'sealed_product_id' FROM jsonb_array_elements(p_rows) AS row
    ) AS distinct_ids;
    IF v_distinct_rows <> v_row_count THEN
        RAISE EXCEPTION 'duplicate sealed_product_id rows in one best-open-price publication';
    END IF;
    IF v_row_count <> (p_snapshot->>'resolved_count')::INTEGER THEN
        RAISE EXCEPTION 'best-open-price row count (%) does not equal resolved_count (%)',
            v_row_count, p_snapshot->>'resolved_count';
    END IF;

    -- Mixed-generation guard: a V3 row must not carry any V4/V12-named evidence.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        CROSS JOIN unnest(ARRAY[
            'current_overall_rip_v12_score','current_financial_rip_v4_score','current_financial_only_rank',
            'benchmark_overall_rip_v12_score','benchmark_financial_rip_v4_score',
            'threshold_financial_rip_v4_score','threshold_overall_rip_v12_score',
            'financial_benchmark_financial_rip_v4_score','financial_benchmark_overall_rip_v12_score',
            'financial_threshold_financial_rip_v4_score','financial_threshold_overall_rip_v12_score'
        ]) AS f(name)
        WHERE x ? f.name AND jsonb_typeof(x->f.name) IS DISTINCT FROM 'null'
    ) THEN
        RAISE EXCEPTION 'a Best-Open V3 row carries V4/V12 evidence (mixed model generations)';
    END IF;

    -- Live Ranking V2 authority lookup and locking sequence (same order as V1/V2).
    SELECT lp.snapshot_id INTO v_candidate_source_id
    FROM public.budget_product_ranking_latest lp
    WHERE lp.ranking_method_version = p_snapshot->>'ranking_method_version'
      AND lp.allocation_method_version = p_snapshot->>'allocation_method_version';
    IF v_candidate_source_id IS NULL THEN
        RAISE EXCEPTION 'no live budget ranking source found';
    END IF;

    SELECT s.* INTO v_live_snapshot
    FROM public.budget_product_ranking_snapshots s
    WHERE s.id = v_candidate_source_id
    FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'source snapshot is missing'; END IF;

    SELECT lp.snapshot_id INTO v_locked_pointer_id
    FROM public.budget_product_ranking_latest lp
    WHERE lp.ranking_method_version = p_snapshot->>'ranking_method_version'
      AND lp.allocation_method_version = p_snapshot->>'allocation_method_version'
    FOR UPDATE;
    IF v_locked_pointer_id IS DISTINCT FROM v_candidate_source_id THEN
        RAISE EXCEPTION 'source pointer advanced while acquiring publication locks';
    END IF;

    IF v_live_snapshot.ranked_under_v14_authority IS DISTINCT FROM TRUE
       OR v_live_snapshot.ranking_method_version IS DISTINCT FROM 'budget_product_ranking_v2'
       OR v_live_snapshot.allocation_method_version IS DISTINCT FROM 'budget_allocation_floor_quantity_v1'
       OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM 'budget_constrained_whole_unit_cross_format_v1'
       OR v_live_snapshot.financial_rip_version IS DISTINCT FROM 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
       OR v_live_snapshot.financial_rip_v5_version IS DISTINCT FROM v_live_snapshot.financial_rip_version
       OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
       OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
       OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002'
       OR v_live_snapshot.overall_rip_version IS DISTINCT FROM
          'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
       OR v_live_snapshot.overall_rip_v14_version IS DISTINCT FROM v_live_snapshot.overall_rip_version
       OR v_live_snapshot.overall_rip_version IS DISTINCT FROM p_snapshot->>'overall_rip_v14_version'
       OR v_live_snapshot.id IS DISTINCT FROM (p_snapshot->>'source_budget_snapshot_id')::UUID
       OR v_live_snapshot.published_at IS DISTINCT FROM (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ
       OR v_live_snapshot.market_date IS DISTINCT FROM (p_snapshot->>'source_market_date')::DATE
       OR v_live_snapshot.cohort_fingerprint IS DISTINCT FROM p_snapshot->>'source_cohort_fingerprint'
       OR v_live_snapshot.eligible_cohort_count IS DISTINCT FROM (p_snapshot->>'source_eligible_cohort_count')::INTEGER
       OR v_live_snapshot.full_market_budget IS DISTINCT FROM (p_snapshot->>'source_full_market_budget')::NUMERIC
    THEN
        RAISE EXCEPTION 'best-open-price source binding no longer matches live V14 authority';
    END IF;

    PERFORM 1 FROM public.budget_product_ranking_rows r
    WHERE r.snapshot_id = v_live_snapshot.id AND r.budget_type = 'full_market'
    ORDER BY r.sealed_product_id FOR SHARE;
    SELECT count(*) INTO v_live_count FROM public.budget_product_ranking_rows r
    WHERE r.snapshot_id = v_live_snapshot.id AND r.budget_type = 'full_market'
      AND r.target_budget = v_live_snapshot.full_market_budget;
    IF v_live_count < 2 OR v_live_count IS DISTINCT FROM v_live_snapshot.eligible_cohort_count
       OR v_live_count IS DISTINCT FROM v_row_count
       OR (p_snapshot->>'unresolved_count')::INTEGER IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'complete Full Market source cohort is required';
    END IF;

    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rows) AS x
               WHERE x->>'financial_status' IS NULL OR x->>'status' IS NULL) THEN
        RAISE EXCEPTION 'status and financial_status are required on every Best-Open Price V3 row';
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        CROSS JOIN unnest(ARRAY[
            'current_market_price','best_open_price','current_quantity','threshold_quantity',
            'current_budget_rank','current_financial_only_rank_v5',
            'current_overall_rip_v14_score','current_financial_rip_v5_score',
            'current_collector_appeal_score','current_chase_accessibility_raw',
            'current_chance_to_recover_capital','current_actual_committed_capital',
            'benchmark_overall_rip_v14_score','benchmark_financial_rip_v5_score',
            'benchmark_chance_to_recover_capital','benchmark_actual_committed_capital',
            'price_gap_dollars','price_gap_percent','candidate_price_evaluations',
            'bracket_expansions','bracket_refinements','monotonicity_fallback_count','search_wall_seconds',
            'financial_best_open_price','financial_threshold_quantity',
            'financial_price_gap_dollars','financial_price_gap_percent',
            'financial_benchmark_financial_rip_v5_score','financial_benchmark_overall_rip_v14_score',
            'threshold_financial_rip_v5_score','threshold_overall_rip_v14_score',
            'threshold_chance_to_recover_capital','threshold_actual_committed_capital',
            'financial_threshold_financial_rip_v5_score','financial_threshold_overall_rip_v14_score',
            'financial_threshold_chance_to_recover_capital','financial_threshold_actual_committed_capital'
        ]) AS f(name)
        WHERE x->>f.name IS NULL OR (x->>f.name)::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
    ) THEN RAISE EXCEPTION 'missing or non-finite numeric source/threshold evidence'; END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        CROSS JOIN unnest(ARRAY['current_quantity','threshold_quantity','current_budget_rank',
                               'current_financial_only_rank_v5','candidate_price_evaluations',
                               'bracket_expansions','bracket_refinements','monotonicity_fallback_count',
                               'financial_threshold_quantity']) AS f(name)
        WHERE (x->>f.name)::NUMERIC <> trunc((x->>f.name)::NUMERIC)
    ) THEN RAISE EXCEPTION 'non-integral count/rank/quantity'; END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        WHERE COALESCE((x->>'threshold_exact_verified')::BOOLEAN, FALSE) IS NOT TRUE
           OR COALESCE((x->>'financial_threshold_exact_verified')::BOOLEAN, FALSE) IS NOT TRUE
    ) THEN RAISE EXCEPTION 'every Best-Open V3 threshold must carry verified exact-search evidence'; END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        WHERE (x->>'current_market_price')::NUMERIC <= 0
           OR (x->>'best_open_price')::NUMERIC <= 0
           OR (x->>'current_market_price')::NUMERIC > v_live_snapshot.full_market_budget
           OR (x->>'best_open_price')::NUMERIC > v_live_snapshot.full_market_budget
           OR (x->>'current_quantity')::NUMERIC IS DISTINCT FROM floor(v_live_snapshot.full_market_budget / NULLIF((x->>'current_market_price')::NUMERIC, 0))
           OR (x->>'threshold_quantity')::NUMERIC IS DISTINCT FROM floor(v_live_snapshot.full_market_budget / NULLIF((x->>'best_open_price')::NUMERIC, 0))
           OR (x->>'price_gap_dollars')::NUMERIC IS DISTINCT FROM (x->>'current_market_price')::NUMERIC - (x->>'best_open_price')::NUMERIC
           OR abs((x->>'price_gap_percent')::NUMERIC - ((x->>'current_market_price')::NUMERIC - (x->>'best_open_price')::NUMERIC) / NULLIF((x->>'current_market_price')::NUMERIC, 0)) > 0.000000000001
           OR (x->>'current_actual_committed_capital')::NUMERIC IS DISTINCT FROM (x->>'current_quantity')::NUMERIC * (x->>'current_market_price')::NUMERIC
           OR ((x->>'current_budget_rank')::INTEGER = 1 AND (x->>'best_open_price')::NUMERIC < (x->>'current_market_price')::NUMERIC)
           OR ((x->>'current_budget_rank')::INTEGER <> 1 AND (x->>'best_open_price')::NUMERIC > (x->>'current_market_price')::NUMERIC)
           OR (x->>'status' = 'current_number_one_with_headroom' AND (x->>'current_budget_rank')::INTEGER <> 1)
           OR (x->>'financial_best_open_price')::NUMERIC <= 0
           OR (x->>'financial_best_open_price')::NUMERIC > v_live_snapshot.full_market_budget
           OR (x->>'financial_threshold_quantity')::NUMERIC IS DISTINCT FROM floor(v_live_snapshot.full_market_budget / NULLIF((x->>'financial_best_open_price')::NUMERIC, 0))
           OR (x->>'financial_price_gap_dollars')::NUMERIC IS DISTINCT FROM (x->>'current_market_price')::NUMERIC - (x->>'financial_best_open_price')::NUMERIC
           OR abs((x->>'financial_price_gap_percent')::NUMERIC - ((x->>'current_market_price')::NUMERIC - (x->>'financial_best_open_price')::NUMERIC) / NULLIF((x->>'current_market_price')::NUMERIC, 0)) > 0.000000000001
           OR ((x->>'current_financial_only_rank_v5')::INTEGER = 1 AND (x->>'financial_best_open_price')::NUMERIC < (x->>'current_market_price')::NUMERIC)
           OR ((x->>'current_financial_only_rank_v5')::INTEGER <> 1 AND (x->>'financial_best_open_price')::NUMERIC > (x->>'current_market_price')::NUMERIC)
           OR (x->>'financial_status' = 'current_number_one_with_headroom' AND (x->>'current_financial_only_rank_v5')::INTEGER <> 1)
    ) THEN RAISE EXCEPTION 'invalid threshold money/allocation/direction arithmetic'; END IF;

    -- Current side: every value reconciles against the live Ranking V2 row.
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        LEFT JOIN public.budget_product_ranking_rows live
          ON live.snapshot_id = v_live_snapshot.id
         AND live.sealed_product_id = (row->>'sealed_product_id')::UUID
         AND live.budget_type = 'full_market'
         AND live.target_budget = v_live_snapshot.full_market_budget
        WHERE live.sealed_product_id IS NULL
           OR live.product_family IS DISTINCT FROM row->>'product_family'
           OR live.product_market_price IS DISTINCT FROM (row->>'current_market_price')::NUMERIC
           OR live.quantity IS DISTINCT FROM (row->>'current_quantity')::INTEGER
           OR live.budget_rank_v14 IS DISTINCT FROM (row->>'current_budget_rank')::INTEGER
           OR live.financial_only_rank_v5 IS DISTINCT FROM (row->>'current_financial_only_rank_v5')::INTEGER
           OR live.overall_rip_v14_score IS DISTINCT FROM (row->>'current_overall_rip_v14_score')::NUMERIC
           OR live.financial_rip_v5_score IS DISTINCT FROM (row->>'current_financial_rip_v5_score')::NUMERIC
           OR live.set_id IS DISTINCT FROM (row->>'set_id')::UUID
           OR live.source_calculation_run_id IS DISTINCT FROM NULLIF(row->>'source_calculation_run_id', '')::UUID
           OR live.collector_appeal_score IS DISTINCT FROM (row->>'current_collector_appeal_score')::NUMERIC
           OR live.chase_accessibility_raw IS DISTINCT FROM (row->>'current_chase_accessibility_raw')::NUMERIC
           OR live.chance_to_recover_capital IS DISTINCT FROM (row->>'current_chance_to_recover_capital')::NUMERIC
           OR live.actual_committed_capital IS DISTINCT FROM (row->>'current_actual_committed_capital')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live Full Market ranking rows';
    END IF;

    -- Overall (V14) benchmark = the live rank-1 row (or rank-2 for the leader).
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        LEFT JOIN public.budget_product_ranking_rows bench
          ON bench.snapshot_id = v_live_snapshot.id
         AND bench.sealed_product_id = (row->>'benchmark_sealed_product_id')::UUID
         AND bench.budget_type = 'full_market'
         AND bench.target_budget = v_live_snapshot.full_market_budget
        WHERE bench.sealed_product_id IS NULL
           OR bench.sealed_product_id = (row->>'sealed_product_id')::UUID
           OR bench.budget_rank_v14 IS DISTINCT FROM CASE WHEN (row->>'current_budget_rank')::INTEGER = 1 THEN 2 ELSE 1 END
           OR bench.overall_rip_v14_score IS DISTINCT FROM (row->>'benchmark_overall_rip_v14_score')::NUMERIC
           OR bench.financial_rip_v5_score IS DISTINCT FROM (row->>'benchmark_financial_rip_v5_score')::NUMERIC
           OR bench.chance_to_recover_capital IS DISTINCT FROM (row->>'benchmark_chance_to_recover_capital')::NUMERIC
           OR bench.actual_committed_capital IS DISTINCT FROM (row->>'benchmark_actual_committed_capital')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live benchmark ranking row';
    END IF;

    -- Financial (V5) benchmark = the live Financial-V5 rank-1 row (rank-2 for the leader).
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        LEFT JOIN public.budget_product_ranking_rows fbench
          ON fbench.snapshot_id = v_live_snapshot.id
         AND fbench.sealed_product_id = (row->>'financial_benchmark_sealed_product_id')::UUID
         AND fbench.budget_type = 'full_market'
         AND fbench.target_budget = v_live_snapshot.full_market_budget
        WHERE fbench.sealed_product_id IS NULL
           OR fbench.sealed_product_id = (row->>'sealed_product_id')::UUID
           OR fbench.financial_only_rank_v5 IS DISTINCT FROM CASE WHEN (row->>'current_financial_only_rank_v5')::INTEGER = 1 THEN 2 ELSE 1 END
           OR fbench.financial_rip_v5_score IS DISTINCT FROM (row->>'financial_benchmark_financial_rip_v5_score')::NUMERIC
           OR fbench.overall_rip_v14_score IS DISTINCT FROM (row->>'financial_benchmark_overall_rip_v14_score')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live Financial benchmark ranking row';
    END IF;

    -- Threshold evidence range/economics, and the necessary condition of a win: on each
    -- axis the threshold's primary score is at least the benchmark's (the comparator
    -- orders by that score first). The exact tie-break chain is proven by the engine.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS x
        WHERE (x->>'threshold_chance_to_recover_capital')::NUMERIC NOT BETWEEN 0 AND 1
           OR (x->>'threshold_actual_committed_capital')::NUMERIC <= 0
           OR abs((x->>'threshold_actual_committed_capital')::NUMERIC
                  - (x->>'threshold_quantity')::NUMERIC * (x->>'best_open_price')::NUMERIC) > 0.01
           OR (x->>'financial_threshold_chance_to_recover_capital')::NUMERIC NOT BETWEEN 0 AND 1
           OR (x->>'financial_threshold_actual_committed_capital')::NUMERIC <= 0
           OR abs((x->>'financial_threshold_actual_committed_capital')::NUMERIC
                  - (x->>'financial_threshold_quantity')::NUMERIC * (x->>'financial_best_open_price')::NUMERIC) > 0.01
           OR (x->>'threshold_financial_rip_v5_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (x->>'threshold_overall_rip_v14_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (x->>'financial_threshold_financial_rip_v5_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (x->>'financial_threshold_overall_rip_v14_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (x->>'threshold_overall_rip_v14_score')::NUMERIC < (x->>'benchmark_overall_rip_v14_score')::NUMERIC
           OR (x->>'financial_threshold_financial_rip_v5_score')::NUMERIC < (x->>'financial_benchmark_financial_rip_v5_score')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'invalid dual threshold-evidence range, economic reconciliation, or benchmark win';
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE (row->>'current_market_price')::NUMERIC <> round((row->>'current_market_price')::NUMERIC, 2)
           OR (row->>'best_open_price')::NUMERIC <> round((row->>'best_open_price')::NUMERIC, 2)
           OR (row->>'financial_best_open_price')::NUMERIC <> round((row->>'financial_best_open_price')::NUMERIC, 2)
    ) THEN
        RAISE EXCEPTION 'a best-open-price money field is not exact-cent precision';
    END IF;

    IF (v_row_count + (p_snapshot->>'unresolved_count')::INTEGER) <> v_live_snapshot.eligible_cohort_count THEN
        RAISE EXCEPTION 'resolved_count + unresolved_count does not equal the live eligible cohort count';
    END IF;

    -- Idempotency: identical source identity + method version must carry identical content.
    SELECT jsonb_agg(to_jsonb(r) - 'id' - 'snapshot_id' ORDER BY r.sealed_product_id)
    INTO v_incoming_content
    FROM jsonb_populate_recordset(NULL::public.budget_product_best_open_price_rows, p_rows) r;
    v_content_fingerprint := encode(extensions.digest(v_incoming_content::TEXT, 'sha256'), 'hex');
    SELECT s.id INTO v_existing_id
    FROM public.budget_product_best_open_price_snapshots s
    WHERE s.source_budget_snapshot_id = v_live_snapshot.id
      AND s.source_budget_published_at = v_live_snapshot.published_at
      AND s.best_open_price_method_version = p_snapshot->>'best_open_price_method_version';
    IF v_existing_id IS NOT NULL THEN
        SELECT jsonb_agg(to_jsonb(r) - 'id' - 'snapshot_id' ORDER BY r.sealed_product_id)
        INTO v_stored_content
        FROM public.budget_product_best_open_price_rows r WHERE r.snapshot_id = v_existing_id;
        IF v_stored_content IS DISTINCT FROM v_incoming_content THEN
            RAISE EXCEPTION 'non-deterministic content for identical source identity and method version';
        END IF;
        RETURN v_existing_id;
    END IF;

    INSERT INTO public.budget_product_best_open_price_snapshots (
        built_at, source_budget_snapshot_id, source_budget_published_at, source_market_date,
        source_cohort_fingerprint, source_full_market_row_fingerprint, source_full_market_budget,
        source_eligible_cohort_count,
        ranking_method_version, allocation_method_version, comparison_scope_version,
        financial_rip_version, overall_rip_v14_version, collector_appeal_version,
        chase_accessibility_version, chase_accessibility_transform_version,
        best_open_price_method_version,
        resolved_count, unresolved_count, runtime_seconds, diagnostics_json
    ) VALUES (
        (p_snapshot->>'built_at')::TIMESTAMPTZ,
        (p_snapshot->>'source_budget_snapshot_id')::UUID, (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ,
        (p_snapshot->>'source_market_date')::DATE,
        p_snapshot->>'source_cohort_fingerprint', p_snapshot->>'source_full_market_row_fingerprint',
        (p_snapshot->>'source_full_market_budget')::NUMERIC, (p_snapshot->>'source_eligible_cohort_count')::INTEGER,
        p_snapshot->>'ranking_method_version', p_snapshot->>'allocation_method_version', p_snapshot->>'comparison_scope_version',
        p_snapshot->>'financial_rip_version', p_snapshot->>'overall_rip_v14_version', p_snapshot->>'collector_appeal_version',
        p_snapshot->>'chase_accessibility_version', p_snapshot->>'chase_accessibility_transform_version',
        p_snapshot->>'best_open_price_method_version',
        (p_snapshot->>'resolved_count')::INTEGER, (p_snapshot->>'unresolved_count')::INTEGER,
        (p_snapshot->>'runtime_seconds')::NUMERIC,
        COALESCE(p_snapshot->'diagnostics_json', '{}'::jsonb) || jsonb_build_object('content_fingerprint', v_content_fingerprint)
    ) RETURNING id INTO v_id;

    INSERT INTO public.budget_product_best_open_price_rows (
        snapshot_id, sealed_product_id, set_id, product_family, source_calculation_run_id,
        current_market_price, current_quantity, current_budget_rank,
        current_overall_rip_v14_score, current_financial_rip_v5_score, current_financial_only_rank_v5,
        current_collector_appeal_score, current_chase_accessibility_raw,
        current_chance_to_recover_capital, current_actual_committed_capital,
        status, best_open_price, threshold_quantity, price_gap_dollars, price_gap_percent,
        benchmark_sealed_product_id, benchmark_overall_rip_v14_score, benchmark_financial_rip_v5_score,
        benchmark_chance_to_recover_capital, benchmark_actual_committed_capital,
        candidate_price_evaluations, bracket_expansions, bracket_refinements,
        monotonicity_fallback_count, search_wall_seconds,
        financial_status, financial_best_open_price, financial_threshold_quantity,
        financial_price_gap_dollars, financial_price_gap_percent,
        financial_benchmark_sealed_product_id, financial_benchmark_financial_rip_v5_score,
        financial_benchmark_overall_rip_v14_score,
        threshold_financial_rip_v5_score, threshold_overall_rip_v14_score,
        threshold_chance_to_recover_capital, threshold_actual_committed_capital,
        financial_threshold_financial_rip_v5_score, financial_threshold_overall_rip_v14_score,
        financial_threshold_chance_to_recover_capital, financial_threshold_actual_committed_capital,
        threshold_exact_verified, financial_threshold_exact_verified
    )
    SELECT
        v_id, (x->>'sealed_product_id')::UUID, (x->>'set_id')::UUID, x->>'product_family',
        NULLIF(x->>'source_calculation_run_id', '')::UUID,
        (x->>'current_market_price')::NUMERIC, (x->>'current_quantity')::INTEGER,
        (x->>'current_budget_rank')::INTEGER,
        (x->>'current_overall_rip_v14_score')::NUMERIC, (x->>'current_financial_rip_v5_score')::NUMERIC,
        (x->>'current_financial_only_rank_v5')::INTEGER,
        (x->>'current_collector_appeal_score')::NUMERIC, (x->>'current_chase_accessibility_raw')::NUMERIC,
        (x->>'current_chance_to_recover_capital')::NUMERIC, (x->>'current_actual_committed_capital')::NUMERIC,
        x->>'status', (x->>'best_open_price')::NUMERIC, (x->>'threshold_quantity')::INTEGER,
        (x->>'price_gap_dollars')::NUMERIC, NULLIF(x->>'price_gap_percent', '')::NUMERIC,
        (x->>'benchmark_sealed_product_id')::UUID, (x->>'benchmark_overall_rip_v14_score')::NUMERIC,
        (x->>'benchmark_financial_rip_v5_score')::NUMERIC,
        (x->>'benchmark_chance_to_recover_capital')::NUMERIC, (x->>'benchmark_actual_committed_capital')::NUMERIC,
        (x->>'candidate_price_evaluations')::INTEGER, (x->>'bracket_expansions')::INTEGER,
        (x->>'bracket_refinements')::INTEGER, (x->>'monotonicity_fallback_count')::INTEGER,
        (x->>'search_wall_seconds')::NUMERIC,
        x->>'financial_status', (x->>'financial_best_open_price')::NUMERIC, (x->>'financial_threshold_quantity')::INTEGER,
        (x->>'financial_price_gap_dollars')::NUMERIC, NULLIF(x->>'financial_price_gap_percent', '')::NUMERIC,
        (x->>'financial_benchmark_sealed_product_id')::UUID, (x->>'financial_benchmark_financial_rip_v5_score')::NUMERIC,
        (x->>'financial_benchmark_overall_rip_v14_score')::NUMERIC,
        (x->>'threshold_financial_rip_v5_score')::NUMERIC, (x->>'threshold_overall_rip_v14_score')::NUMERIC,
        (x->>'threshold_chance_to_recover_capital')::NUMERIC, (x->>'threshold_actual_committed_capital')::NUMERIC,
        (x->>'financial_threshold_financial_rip_v5_score')::NUMERIC, (x->>'financial_threshold_overall_rip_v14_score')::NUMERIC,
        (x->>'financial_threshold_chance_to_recover_capital')::NUMERIC, (x->>'financial_threshold_actual_committed_capital')::NUMERIC,
        (x->>'threshold_exact_verified')::BOOLEAN, (x->>'financial_threshold_exact_verified')::BOOLEAN
    FROM jsonb_array_elements(p_rows) AS x;

    IF (SELECT count(*) FROM public.budget_product_best_open_price_rows WHERE snapshot_id = v_id) <> v_row_count THEN
        RAISE EXCEPTION 'persisted best-open-price row count does not reconcile with the publication payload';
    END IF;

    INSERT INTO public.budget_product_best_open_price_latest (
        best_open_price_method_version, snapshot_id, source_budget_snapshot_id,
        source_budget_published_at, source_market_date, source_cohort_fingerprint, updated_at
    ) VALUES (
        p_snapshot->>'best_open_price_method_version', v_id,
        (p_snapshot->>'source_budget_snapshot_id')::UUID, (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ,
        (p_snapshot->>'source_market_date')::DATE, p_snapshot->>'source_cohort_fingerprint',
        timezone('utc', now())
    )
    ON CONFLICT (best_open_price_method_version) DO UPDATE SET
        snapshot_id = EXCLUDED.snapshot_id,
        source_budget_snapshot_id = EXCLUDED.source_budget_snapshot_id,
        source_budget_published_at = EXCLUDED.source_budget_published_at,
        source_market_date = EXCLUDED.source_market_date,
        source_cohort_fingerprint = EXCLUDED.source_cohort_fingerprint,
        updated_at = timezone('utc', now());

    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION public.publish_budget_product_best_open_price_snapshot_v3(JSONB, JSONB)
    FROM PUBLIC, anon, authenticated, service_role;

-- Dispatcher: the only entry point. V3 is routed by method version; V1/V2 run the
-- unchanged body. V5/V14 fields on a non-V3 publication fail closed.
CREATE FUNCTION public.publish_budget_product_best_open_price_snapshot(
    p_snapshot JSONB, p_rows JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, extensions, pg_temp
AS $$
BEGIN
    IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'best-open-price snapshot must be an object';
    END IF;
    IF p_snapshot->>'best_open_price_method_version' = 'budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14' THEN
        RETURN public.publish_budget_product_best_open_price_snapshot_v3(p_snapshot, p_rows);
    END IF;

    IF p_snapshot ? 'overall_rip_v14_version'
       OR (jsonb_typeof(p_rows) = 'array' AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            CROSS JOIN unnest(ARRAY[
                'current_overall_rip_v14_score','current_financial_rip_v5_score','current_financial_only_rank_v5',
                'benchmark_overall_rip_v14_score','benchmark_financial_rip_v5_score',
                'threshold_financial_rip_v5_score','threshold_overall_rip_v14_score',
                'financial_benchmark_financial_rip_v5_score','financial_benchmark_overall_rip_v14_score',
                'financial_threshold_financial_rip_v5_score','financial_threshold_overall_rip_v14_score',
                'threshold_exact_verified','financial_threshold_exact_verified'
            ]) AS f(name)
            WHERE x ? f.name AND jsonb_typeof(x->f.name) IS DISTINCT FROM 'null'
       )) THEN
        RAISE EXCEPTION 'V5/V14 best-open-price fields require the V3 method version';
    END IF;

    RETURN public.publish_budget_product_best_open_price_snapshot_v1_v2(p_snapshot, p_rows);
END;
$$;

REVOKE ALL ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
