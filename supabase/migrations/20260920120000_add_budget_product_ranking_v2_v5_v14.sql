-- Budget Product Ranking V2: persist Financial RIP V5 + Overall RIP V14 rankings.
--
-- STRICTLY ADDITIVE / VERSION-PRESERVING
--   * Every V1/V12 column keeps its name, type and meaning. Historical rows are
--     untouched and stay valid.
--   * V2 evidence lives in NEW, explicitly V5/V14-named columns. Nothing V5/V14
--     is ever written into a financial_rip_v4_* / overall_rip_v10|v12_* /
--     budget_rank_v12 / financial_only_rank column.
--   * The four legacy rank/tier columns (budget_rank, budget_cohort_size,
--     budget_tier, financial_only_rank) become NULLABLE so a V2 row does not have
--     to carry a V2 rank inside a V1-named column. A row-shape CHECK makes every
--     row EITHER fully legacy-shaped OR fully V2-shaped, and the V1/V12 RPC body
--     (unchanged, see below) still refuses NULLs in those columns.
--   * The published function is renamed, not rewritten: the current V1/V12 body
--     keeps running verbatim behind a thin dispatcher. The V2 branch is a separate
--     private function. V1 and V2 use distinct (method, allocation) latest
--     pointers, so publishing V2 never moves the V1 pointer.
--
-- Nothing here changes which method is canonical or default.
--
-- SECURITY: SECURITY DEFINER + SET search_path = public (same as the existing
-- function). Only the dispatcher is executable, and only by service_role; the
-- renamed V1/V12 body and the V2 branch are internal (no grants to any API role).
--
-- ROLLBACK: DROP the V2 columns/constraints, restore NOT NULL on the four legacy
-- columns (only valid once no V2 rows exist), and rename the
-- publish_budget_product_ranking_snapshot_v1_v12 function back.

BEGIN;

ALTER TABLE public.budget_product_ranking_snapshots
    ADD COLUMN IF NOT EXISTS financial_rip_v5_version TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v14_version TEXT,
    ADD COLUMN IF NOT EXISTS ranked_under_v14_authority BOOLEAN;

COMMENT ON COLUMN public.budget_product_ranking_snapshots.ranked_under_v14_authority IS
    'TRUE only for a budget_product_ranking_v2 snapshot ranked under Overall RIP V14 (Financial RIP V5). NULL/FALSE for every V1/V12 snapshot. Never implicitly TRUE.';

ALTER TABLE public.budget_product_ranking_snapshots
    ADD CONSTRAINT budget_ranking_snapshots_v2_authority_shape CHECK (
        (ranking_method_version = 'budget_product_ranking_v2'
            AND ranked_under_v14_authority IS TRUE
            AND financial_rip_v5_version IS NOT NULL
            AND overall_rip_v14_version IS NOT NULL)
        OR
        (ranking_method_version <> 'budget_product_ranking_v2'
            AND ranked_under_v14_authority IS NOT TRUE
            AND financial_rip_v5_version IS NULL
            AND overall_rip_v14_version IS NULL)
    ) NOT VALID;
ALTER TABLE public.budget_product_ranking_snapshots
    VALIDATE CONSTRAINT budget_ranking_snapshots_v2_authority_shape;

ALTER TABLE public.budget_product_ranking_rows
    ADD COLUMN IF NOT EXISTS financial_rip_v5_score NUMERIC
        CHECK (financial_rip_v5_score IS NULL OR (financial_rip_v5_score >= 0 AND financial_rip_v5_score <= 100)),
    ADD COLUMN IF NOT EXISTS financial_rip_v5_status TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v5_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v14_score NUMERIC
        CHECK (overall_rip_v14_score IS NULL OR (overall_rip_v14_score >= 0 AND overall_rip_v14_score <= 100)),
    ADD COLUMN IF NOT EXISTS overall_rip_v14_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v14_status TEXT,
    ADD COLUMN IF NOT EXISTS budget_rank_v14 INTEGER CHECK (budget_rank_v14 IS NULL OR budget_rank_v14 >= 1),
    ADD COLUMN IF NOT EXISTS budget_cohort_size_v14 INTEGER CHECK (budget_cohort_size_v14 IS NULL OR budget_cohort_size_v14 >= 1),
    ADD COLUMN IF NOT EXISTS budget_tier_v14 TEXT CHECK (budget_tier_v14 IS NULL OR budget_tier_v14 IN ('S','A','B','C','D','F')),
    ADD COLUMN IF NOT EXISTS financial_only_rank_v5 INTEGER CHECK (financial_only_rank_v5 IS NULL OR financial_only_rank_v5 >= 1);

COMMENT ON COLUMN public.budget_product_ranking_rows.financial_only_rank_v5 IS
    'Rank of this strategy by Financial RIP V5 alone within its budget cohort. Distinct from financial_only_rank, which is and remains the Financial RIP V4 rank of V1 snapshots.';

ALTER TABLE public.budget_product_ranking_rows
    ALTER COLUMN budget_rank DROP NOT NULL,
    ALTER COLUMN budget_cohort_size DROP NOT NULL,
    ALTER COLUMN budget_tier DROP NOT NULL,
    ALTER COLUMN financial_only_rank DROP NOT NULL;

ALTER TABLE public.budget_product_ranking_rows
    ADD CONSTRAINT budget_ranking_rows_authority_shape CHECK (
        -- Legacy (V1/V10/V12) row: the V4/V10 rank columns are set, no V5/V14 field is.
        (budget_rank IS NOT NULL AND budget_cohort_size IS NOT NULL
            AND budget_tier IS NOT NULL AND financial_only_rank IS NOT NULL
            AND financial_rip_v5_score IS NULL AND financial_rip_v5_status IS NULL
            AND financial_rip_v5_rankable IS NULL
            AND overall_rip_v14_score IS NULL AND overall_rip_v14_rankable IS NULL
            AND overall_rip_v14_status IS NULL
            AND budget_rank_v14 IS NULL AND budget_cohort_size_v14 IS NULL
            AND budget_tier_v14 IS NULL AND financial_only_rank_v5 IS NULL)
        OR
        -- V2 row: every V5/V14 field is set and no V4/V10/V12 field is.
        (budget_rank IS NULL AND budget_cohort_size IS NULL
            AND budget_tier IS NULL AND financial_only_rank IS NULL
            AND financial_rip_v4_score IS NULL AND overall_rip_v10_score IS NULL
            AND overall_rip_v12_score IS NULL AND overall_rip_v12_rankable IS NULL
            AND overall_rip_v12_status IS NULL AND budget_rank_v12 IS NULL
            AND budget_cohort_size_v12 IS NULL
            AND financial_rip_v5_score IS NOT NULL AND financial_rip_v5_status = 'ready'
            AND financial_rip_v5_rankable IS TRUE
            AND overall_rip_v14_score IS NOT NULL AND overall_rip_v14_rankable IS TRUE
            AND overall_rip_v14_status = 'ready'
            AND budget_rank_v14 IS NOT NULL AND budget_cohort_size_v14 IS NOT NULL
            AND budget_tier_v14 IS NOT NULL AND financial_only_rank_v5 IS NOT NULL
            AND budget_rank_v14 <= budget_cohort_size_v14
            AND financial_only_rank_v5 <= budget_cohort_size_v14)
    ) NOT VALID;
ALTER TABLE public.budget_product_ranking_rows
    VALIDATE CONSTRAINT budget_ranking_rows_authority_shape;

-- The current V1/V12 body keeps running verbatim behind the dispatcher below.
ALTER FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB)
    RENAME TO publish_budget_product_ranking_snapshot_v1_v12;
REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot_v1_v12(JSONB, JSONB)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.publish_budget_product_ranking_snapshot_v2(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_id UUID;
    v_expected INTEGER;
    v_row_count INTEGER;
    v_distinct_rows INTEGER;
BEGIN
    IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'budget ranking V2 snapshot must be an object';
    END IF;
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'budget ranking rows must be an array';
    END IF;
    v_row_count := jsonb_array_length(p_rows);
    IF v_row_count = 0 THEN
        RAISE EXCEPTION 'refusing to publish an empty budget ranking snapshot';
    END IF;

    -- Exact model/method identities. No fallback to any V1/V4/V10/V12 value.
    IF p_snapshot->>'ranking_method_version' IS DISTINCT FROM 'budget_product_ranking_v2'
       OR p_snapshot->>'allocation_method_version' IS DISTINCT FROM 'budget_allocation_floor_quantity_v1'
       OR p_snapshot->>'comparison_scope_version' IS DISTINCT FROM 'budget_constrained_whole_unit_cross_format_v1'
       OR p_snapshot->>'financial_rip_version' IS DISTINCT FROM 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
       OR p_snapshot->>'financial_rip_v5_version' IS DISTINCT FROM 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
       OR p_snapshot->>'overall_rip_version' IS DISTINCT FROM 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
       OR p_snapshot->>'overall_rip_v14_version' IS DISTINCT FROM 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
       OR p_snapshot->>'collector_appeal_version' IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
       OR p_snapshot->>'chase_accessibility_version' IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
       OR p_snapshot->>'chase_accessibility_transform_version' IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002'
       OR COALESCE((p_snapshot->>'ranked_under_v14_authority')::BOOLEAN, FALSE) IS NOT TRUE THEN
        RAISE EXCEPTION 'V2 budget snapshot authority metadata is missing or mismatched';
    END IF;
    IF p_snapshot ? 'overall_rip_v12_version' OR p_snapshot ? 'ranked_under_v12_authority' THEN
        RAISE EXCEPTION 'V2 budget snapshot must not carry V12 authority fields';
    END IF;

    v_expected := (p_snapshot->>'eligible_cohort_count')::INTEGER;

    SELECT count(*) INTO v_distinct_rows FROM (
        SELECT DISTINCT row->>'sealed_product_id', row->>'target_budget', row->>'budget_type'
        FROM jsonb_array_elements(p_rows) AS row
    ) AS distinct_keys;
    IF v_distinct_rows <> v_row_count THEN
        RAISE EXCEPTION 'duplicate (sealed_product_id, target_budget, budget_type) rows in one publication';
    END IF;

    -- Mixed-generation guard: a V2 row must not carry any V1/V4/V10/V12 value.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        CROSS JOIN unnest(ARRAY[
            'financial_rip_v4_score','overall_rip_v10_score','overall_rip_v12_score',
            'overall_rip_v12_rankable','overall_rip_v12_status','budget_rank_v12',
            'budget_cohort_size_v12','budget_rank','budget_cohort_size','budget_tier',
            'financial_only_rank'
        ]) AS f(name)
        WHERE row ? f.name AND jsonb_typeof(row->f.name) IS DISTINCT FROM 'null'
    ) THEN
        RAISE EXCEPTION 'a V2 budget row carries V1/V4/V10/V12 fields (mixed model generations)';
    END IF;

    -- Required V5/V14 evidence.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE NULLIF(row->>'financial_rip_v5_score', '') IS NULL
           OR NULLIF(row->>'overall_rip_v14_score', '') IS NULL
           OR row->>'financial_rip_v5_status' IS DISTINCT FROM 'ready'
           OR COALESCE((row->>'financial_rip_v5_rankable')::BOOLEAN, FALSE) IS NOT TRUE
           OR row->>'overall_rip_v14_status' IS DISTINCT FROM 'ready'
           OR COALESCE((row->>'overall_rip_v14_rankable')::BOOLEAN, FALSE) IS NOT TRUE
           OR NULLIF(row->>'budget_rank_v14', '') IS NULL
           OR NULLIF(row->>'budget_cohort_size_v14', '') IS NULL
           OR NULLIF(row->>'budget_tier_v14', '') IS NULL
           OR NULLIF(row->>'financial_only_rank_v5', '') IS NULL
           OR NULLIF(row->>'chase_accessibility_raw', '') IS NULL
           OR NULLIF(row->>'collector_appeal_score', '') IS NULL
           OR NULLIF(row->>'chance_to_recover_capital', '') IS NULL
           OR NULLIF(row->>'source_calculation_run_id', '') IS NULL
    ) THEN
        RAISE EXCEPTION 'a V2 budget row is missing required V5/V14 score, rank, or lineage evidence';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        CROSS JOIN unnest(ARRAY[
            'financial_rip_v5_score','overall_rip_v14_score','chase_accessibility_raw',
            'collector_appeal_score','chance_to_recover_capital','expected_value','median_value',
            'top1_outcome_value_share','actual_committed_capital','product_market_price',
            'target_budget','quantity','budget_rank_v14','budget_cohort_size_v14','financial_only_rank_v5'
        ]) AS f(name)
        WHERE NULLIF(row->>f.name, '') IS NULL
           OR (row->>f.name)::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
    ) THEN
        RAISE EXCEPTION 'a V2 budget row has a missing or non-finite numeric field';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE (row->>'financial_rip_v5_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (row->>'overall_rip_v14_score')::NUMERIC NOT BETWEEN 0 AND 100
           OR (row->>'chance_to_recover_capital')::NUMERIC NOT BETWEEN 0 AND 1
           OR (row->>'chase_accessibility_raw')::NUMERIC < 0
           OR (row->>'expected_value')::NUMERIC < 0
           OR (row->>'median_value')::NUMERIC < 0
           OR (row->>'top1_outcome_value_share')::NUMERIC NOT BETWEEN 0 AND 1
           OR (row->>'actual_committed_capital')::NUMERIC <= 0
           OR (row->>'product_market_price')::NUMERIC <= 0
           OR (row->>'target_budget')::NUMERIC <= 0
           OR (row->>'quantity')::NUMERIC < 1
           OR (row->>'quantity')::NUMERIC <> trunc((row->>'quantity')::NUMERIC)
           OR (row->>'budget_rank_v14')::NUMERIC <> trunc((row->>'budget_rank_v14')::NUMERIC)
           OR (row->>'financial_only_rank_v5')::NUMERIC <> trunc((row->>'financial_only_rank_v5')::NUMERIC)
           OR (row->>'budget_rank_v14')::INTEGER > (row->>'budget_cohort_size_v14')::INTEGER
           OR (row->>'financial_only_rank_v5')::INTEGER > (row->>'budget_cohort_size_v14')::INTEGER
    ) THEN
        RAISE EXCEPTION 'a V2 budget row has an out-of-range score, probability, capital, quantity, or rank';
    END IF;

    -- ONE PRICE AUTHORITY (same guarantee as V1).
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE NULLIF(row->>'price_as_of', '') IS DISTINCT FROM (p_snapshot->>'pinned_price_as_of')
    ) THEN
        RAISE EXCEPTION 'mixed price authority: a row''s price_as_of differs from the snapshot pinned_price_as_of (%)',
            p_snapshot->>'pinned_price_as_of';
    END IF;

    INSERT INTO public.budget_product_ranking_snapshots (
        market_date, built_at, published_at, publication_status,
        ranking_method_version, allocation_method_version, comparison_scope_version,
        financial_rip_version, overall_rip_version, collector_appeal_version,
        financial_rip_v5_version, overall_rip_v14_version, ranked_under_v14_authority,
        chase_accessibility_version, chase_accessibility_transform_version,
        eligible_cohort_count, cohort_fingerprint, diagnostics_json,
        pinned_price_as_of, full_market_budget, max_eligible_sku_price,
        full_market_rounding_increment, full_market_rounding_rule_version
    ) VALUES (
        (p_snapshot->>'market_date')::DATE, (p_snapshot->>'built_at')::TIMESTAMPTZ,
        timezone('utc', now()), 'published',
        p_snapshot->>'ranking_method_version', p_snapshot->>'allocation_method_version',
        p_snapshot->>'comparison_scope_version',
        p_snapshot->>'financial_rip_version', p_snapshot->>'overall_rip_version',
        p_snapshot->>'collector_appeal_version',
        p_snapshot->>'financial_rip_v5_version', p_snapshot->>'overall_rip_v14_version', TRUE,
        p_snapshot->>'chase_accessibility_version', p_snapshot->>'chase_accessibility_transform_version',
        v_expected, p_snapshot->>'cohort_fingerprint', COALESCE(p_snapshot->'diagnostics_json', '{}'::jsonb),
        (p_snapshot->>'pinned_price_as_of')::DATE, (p_snapshot->>'full_market_budget')::NUMERIC,
        (p_snapshot->>'max_eligible_sku_price')::NUMERIC,
        (p_snapshot->>'full_market_rounding_increment')::NUMERIC,
        p_snapshot->>'full_market_rounding_rule_version'
    )
    ON CONFLICT (market_date, ranking_method_version, allocation_method_version) DO UPDATE SET
        built_at = EXCLUDED.built_at, published_at = timezone('utc', now()), publication_status = 'published',
        comparison_scope_version = EXCLUDED.comparison_scope_version,
        financial_rip_version = EXCLUDED.financial_rip_version,
        overall_rip_version = EXCLUDED.overall_rip_version,
        collector_appeal_version = EXCLUDED.collector_appeal_version,
        financial_rip_v5_version = EXCLUDED.financial_rip_v5_version,
        overall_rip_v14_version = EXCLUDED.overall_rip_v14_version,
        ranked_under_v14_authority = TRUE,
        chase_accessibility_version = EXCLUDED.chase_accessibility_version,
        chase_accessibility_transform_version = EXCLUDED.chase_accessibility_transform_version,
        eligible_cohort_count = EXCLUDED.eligible_cohort_count,
        cohort_fingerprint = EXCLUDED.cohort_fingerprint,
        diagnostics_json = EXCLUDED.diagnostics_json,
        pinned_price_as_of = EXCLUDED.pinned_price_as_of,
        full_market_budget = EXCLUDED.full_market_budget,
        max_eligible_sku_price = EXCLUDED.max_eligible_sku_price,
        full_market_rounding_increment = EXCLUDED.full_market_rounding_increment,
        full_market_rounding_rule_version = EXCLUDED.full_market_rounding_rule_version
    RETURNING id INTO v_id;

    DELETE FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id;
    INSERT INTO public.budget_product_ranking_rows (
        snapshot_id, sealed_product_id, set_id, product_family,
        target_budget, budget_type, quantity, actual_committed_capital, unused_capital,
        unused_capital_percent, capital_utilization,
        financial_rip_v5_score, financial_rip_v5_status, financial_rip_v5_rankable,
        overall_rip_v14_score, overall_rip_v14_rankable, overall_rip_v14_status,
        budget_rank_v14, budget_cohort_size_v14, budget_tier_v14, financial_only_rank_v5,
        collector_appeal_score, chase_accessibility_raw, chance_to_recover_capital,
        expected_value, median_value, top1_outcome_value_share,
        product_market_price, price_as_of,
        full_market_anchor, max_eligible_sku_price, full_market_rounding_rule,
        full_market_rounding_increment, full_market_rounding_rule_version,
        source_calculation_run_id
    )
    SELECT
        v_id, (x->>'sealed_product_id')::UUID, (x->>'set_id')::UUID, x->>'product_family',
        (x->>'target_budget')::NUMERIC, x->>'budget_type', (x->>'quantity')::INTEGER,
        (x->>'actual_committed_capital')::NUMERIC, (x->>'unused_capital')::NUMERIC,
        (x->>'unused_capital_percent')::NUMERIC, (x->>'capital_utilization')::NUMERIC,
        (x->>'financial_rip_v5_score')::NUMERIC, x->>'financial_rip_v5_status',
        (x->>'financial_rip_v5_rankable')::BOOLEAN,
        (x->>'overall_rip_v14_score')::NUMERIC, (x->>'overall_rip_v14_rankable')::BOOLEAN,
        x->>'overall_rip_v14_status',
        (x->>'budget_rank_v14')::INTEGER, (x->>'budget_cohort_size_v14')::INTEGER,
        x->>'budget_tier_v14', (x->>'financial_only_rank_v5')::INTEGER,
        (x->>'collector_appeal_score')::NUMERIC, (x->>'chase_accessibility_raw')::NUMERIC,
        (x->>'chance_to_recover_capital')::NUMERIC,
        (x->>'expected_value')::NUMERIC, (x->>'median_value')::NUMERIC,
        (x->>'top1_outcome_value_share')::NUMERIC,
        (x->>'product_market_price')::NUMERIC, NULLIF(x->>'price_as_of', '')::DATE,
        NULLIF(x->>'full_market_anchor', '')::NUMERIC, NULLIF(x->>'max_eligible_sku_price', '')::NUMERIC,
        x->>'full_market_rounding_rule',
        NULLIF(x->>'full_market_rounding_increment', '')::NUMERIC, x->>'full_market_rounding_rule_version',
        (x->>'source_calculation_run_id')::UUID
    FROM jsonb_array_elements(p_rows) AS x;

    IF (SELECT count(*) FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id) <> v_row_count THEN
        RAISE EXCEPTION 'persisted budget ranking row count does not reconcile with the publication payload';
    END IF;

    -- Persisted integrity, checked before the latest pointer moves. Any exception
    -- rolls back the snapshot replacement and its rows.
    IF EXISTS (
        SELECT 1
        FROM public.budget_product_ranking_rows
        WHERE snapshot_id = v_id
        GROUP BY target_budget, budget_type
        HAVING count(*) <> min(budget_cohort_size_v14)
            OR min(budget_cohort_size_v14) <> max(budget_cohort_size_v14)
            OR min(budget_rank_v14) <> 1 OR max(budget_rank_v14) <> count(*)
            OR count(DISTINCT budget_rank_v14) <> count(*)
            OR min(financial_only_rank_v5) <> 1 OR max(financial_only_rank_v5) <> count(*)
            OR count(DISTINCT financial_only_rank_v5) <> count(*)
    ) THEN
        RAISE EXCEPTION 'persisted V2 budget cohort size or rank contiguity validation failed';
    END IF;

    IF (SELECT count(DISTINCT price_as_of) FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id) <> 1
       OR EXISTS (SELECT 1 FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id AND price_as_of IS NULL)
       OR (SELECT min(price_as_of) FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id)
          IS DISTINCT FROM (p_snapshot->>'pinned_price_as_of')::DATE THEN
        RAISE EXCEPTION 'persisted budget ranking pinned price authority validation failed';
    END IF;

    IF (SELECT count(DISTINCT target_budget) FROM public.budget_product_ranking_rows
        WHERE snapshot_id = v_id AND budget_type = 'full_market') <> 1
       OR (SELECT count(*) FROM public.budget_product_ranking_rows
           WHERE snapshot_id = v_id AND budget_type = 'full_market') <> v_expected
       OR EXISTS (
           SELECT 1 FROM public.budget_product_ranking_rows
           WHERE snapshot_id = v_id AND budget_type = 'full_market'
             AND (budget_cohort_size_v14 <> v_expected
               OR target_budget IS DISTINCT FROM (p_snapshot->>'full_market_budget')::NUMERIC
               OR full_market_anchor IS DISTINCT FROM (p_snapshot->>'full_market_budget')::NUMERIC
               OR max_eligible_sku_price IS DISTINCT FROM (p_snapshot->>'max_eligible_sku_price')::NUMERIC
               OR full_market_rounding_increment IS DISTINCT FROM (p_snapshot->>'full_market_rounding_increment')::NUMERIC
               OR full_market_rounding_rule_version IS DISTINCT FROM (p_snapshot->>'full_market_rounding_rule_version'))
       ) THEN
        RAISE EXCEPTION 'persisted Full Market count, cohort, anchor, or rounding metadata validation failed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id
          AND (abs((capital_utilization + unused_capital_percent) - 1) >= 0.000001
            OR abs((actual_committed_capital + unused_capital) - target_budget) >= 0.01)
    ) THEN
        RAISE EXCEPTION 'persisted budget ranking capital reconciliation validation failed';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.budget_product_ranking_snapshots
        WHERE id = v_id
          AND ranking_method_version = 'budget_product_ranking_v2'
          AND ranked_under_v14_authority IS TRUE
          AND financial_rip_v5_version = 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
          AND overall_rip_v14_version = 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
    ) THEN
        RAISE EXCEPTION 'persisted V2 budget snapshot authority validation failed';
    END IF;

    INSERT INTO public.budget_product_ranking_latest (ranking_method_version, allocation_method_version, snapshot_id, market_date, updated_at)
    VALUES (p_snapshot->>'ranking_method_version', p_snapshot->>'allocation_method_version', v_id,
            (p_snapshot->>'market_date')::DATE, timezone('utc', now()))
    ON CONFLICT (ranking_method_version, allocation_method_version) DO UPDATE SET
        snapshot_id = EXCLUDED.snapshot_id, market_date = EXCLUDED.market_date, updated_at = timezone('utc', now());

    RETURN v_id;
END;
$function$;

REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot_v2(JSONB, JSONB)
    FROM PUBLIC, anon, authenticated, service_role;

-- Dispatcher: the only entry point. V2 is routed by method version; everything
-- else runs the unchanged V1/V12 body. A V1/V12 publication carrying any V5/V14
-- field, or a V2 publication routed as anything else, fails closed.
CREATE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
    IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'budget ranking snapshot must be an object';
    END IF;
    IF p_snapshot->>'ranking_method_version' = 'budget_product_ranking_v2' THEN
        RETURN public.publish_budget_product_ranking_snapshot_v2(p_snapshot, p_rows);
    END IF;

    IF p_snapshot ? 'financial_rip_v5_version' OR p_snapshot ? 'overall_rip_v14_version'
       OR p_snapshot ? 'ranked_under_v14_authority'
       OR (jsonb_typeof(p_rows) = 'array' AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS row
            CROSS JOIN unnest(ARRAY[
                'financial_rip_v5_score','overall_rip_v14_score','budget_rank_v14',
                'budget_cohort_size_v14','budget_tier_v14','financial_only_rank_v5',
                'financial_rip_v5_status','financial_rip_v5_rankable',
                'overall_rip_v14_status','overall_rip_v14_rankable'
            ]) AS f(name)
            WHERE row ? f.name AND jsonb_typeof(row->f.name) IS DISTINCT FROM 'null'
       )) THEN
        RAISE EXCEPTION 'V5/V14 budget fields require ranking_method_version budget_product_ranking_v2';
    END IF;

    RETURN public.publish_budget_product_ranking_snapshot_v1_v12(p_snapshot, p_rows);
END;
$function$;

REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
