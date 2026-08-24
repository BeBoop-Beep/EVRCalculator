-- Strengthen the already-applied private Budget Ranking publication RPC.
-- Source-only in this change: do not apply as part of implementation work.
-- The function remains one PostgreSQL transaction and service-role-only.

BEGIN;

CREATE OR REPLACE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_id UUID;
    v_expected INTEGER;
    v_row_count INTEGER;
    v_distinct_rows INTEGER;
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'budget ranking rows must be an array';
    END IF;
    v_expected := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    v_row_count := jsonb_array_length(p_rows);
    IF v_row_count = 0 THEN
        RAISE EXCEPTION 'refusing to publish an empty budget ranking snapshot';
    END IF;

    -- One coherent authority: every row must carry the SAME model versions
    -- as the snapshot it belongs to, and every (product, budget, type)
    -- triple must be unique within this publication. Mixed authority fails
    -- the publish rather than silently constructing an inconsistent
    -- snapshot.
    SELECT count(*) INTO v_distinct_rows FROM (
        SELECT DISTINCT row->>'sealed_product_id', row->>'target_budget', row->>'budget_type'
        FROM jsonb_array_elements(p_rows) AS row
    ) AS distinct_keys;
    IF v_distinct_rows <> v_row_count THEN
        RAISE EXCEPTION 'duplicate (sealed_product_id, target_budget, budget_type) rows in one publication';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE (row->>'financial_rip_v4_score') IS NULL
           OR (row->>'overall_rip_v10_score') IS NULL
    ) THEN
        RAISE EXCEPTION 'a ranked budget row is missing its financial or overall score';
    END IF;

    -- ONE PRICE AUTHORITY. Every row must trace to the snapshot's pinned
    -- price_as_of. This is the storage-level guarantee against the
    -- "newest row wins per SKU" failure mode, which yields a full-looking
    -- cohort silently blended across market states.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE NULLIF(row->>'price_as_of', '') IS DISTINCT FROM (p_snapshot->>'pinned_price_as_of')
    ) THEN
        RAISE EXCEPTION 'mixed price authority: a row''s price_as_of differs from the snapshot pinned_price_as_of (%)',
            p_snapshot->>'pinned_price_as_of';
    END IF;

    -- Rank/cohort integrity within each budget cohort.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE (row->>'budget_rank')::INTEGER > (row->>'budget_cohort_size')::INTEGER
           OR (row->>'financial_only_rank')::INTEGER > (row->>'budget_cohort_size')::INTEGER
    ) THEN
        RAISE EXCEPTION 'a ranked budget row has a rank greater than its cohort size';
    END IF;

    INSERT INTO public.budget_product_ranking_snapshots (
        market_date, built_at, published_at, publication_status,
        ranking_method_version, allocation_method_version, comparison_scope_version,
        financial_rip_version, overall_rip_version, collector_appeal_version,
        eligible_cohort_count, cohort_fingerprint, diagnostics_json,
        pinned_price_as_of, full_market_budget, max_eligible_sku_price,
        full_market_rounding_increment, full_market_rounding_rule_version
    ) VALUES (
        (p_snapshot->>'market_date')::DATE, (p_snapshot->>'built_at')::TIMESTAMPTZ,
        timezone('utc', now()), 'published',
        p_snapshot->>'ranking_method_version', p_snapshot->>'allocation_method_version', p_snapshot->>'comparison_scope_version',
        p_snapshot->>'financial_rip_version', p_snapshot->>'overall_rip_version', p_snapshot->>'collector_appeal_version',
        v_expected, p_snapshot->>'cohort_fingerprint', COALESCE(p_snapshot->'diagnostics_json', '{}'::jsonb),
        (p_snapshot->>'pinned_price_as_of')::DATE, (p_snapshot->>'full_market_budget')::NUMERIC,
        (p_snapshot->>'max_eligible_sku_price')::NUMERIC,
        (p_snapshot->>'full_market_rounding_increment')::NUMERIC,
        p_snapshot->>'full_market_rounding_rule_version'
    )
    ON CONFLICT (market_date, ranking_method_version, allocation_method_version) DO UPDATE SET
        built_at = EXCLUDED.built_at, published_at = timezone('utc', now()), publication_status = 'published',
        comparison_scope_version = EXCLUDED.comparison_scope_version,
        financial_rip_version = EXCLUDED.financial_rip_version, overall_rip_version = EXCLUDED.overall_rip_version,
        collector_appeal_version = EXCLUDED.collector_appeal_version,
        eligible_cohort_count = EXCLUDED.eligible_cohort_count, cohort_fingerprint = EXCLUDED.cohort_fingerprint,
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
        target_budget, budget_type, quantity, actual_committed_capital, unused_capital, unused_capital_percent,
        capital_utilization,
        budget_rank, budget_cohort_size, budget_tier, financial_only_rank,
        financial_rip_v4_score, overall_rip_v10_score, collector_appeal_score, chance_to_recover_capital,
        product_market_price, price_as_of,
        full_market_anchor, max_eligible_sku_price, full_market_rounding_rule,
        full_market_rounding_increment, full_market_rounding_rule_version,
        source_calculation_run_id
    )
    SELECT
        v_id, (x->>'sealed_product_id')::UUID, (x->>'set_id')::UUID, x->>'product_family',
        (x->>'target_budget')::NUMERIC, x->>'budget_type', (x->>'quantity')::INTEGER,
        (x->>'actual_committed_capital')::NUMERIC, (x->>'unused_capital')::NUMERIC, (x->>'unused_capital_percent')::NUMERIC,
        (x->>'capital_utilization')::NUMERIC,
        (x->>'budget_rank')::INTEGER, (x->>'budget_cohort_size')::INTEGER, x->>'budget_tier',
        (x->>'financial_only_rank')::INTEGER,
        (x->>'financial_rip_v4_score')::NUMERIC, (x->>'overall_rip_v10_score')::NUMERIC, (x->>'collector_appeal_score')::NUMERIC,
        (x->>'chance_to_recover_capital')::NUMERIC,
        (x->>'product_market_price')::NUMERIC, NULLIF(x->>'price_as_of', '')::DATE,
        (x->>'full_market_anchor')::NUMERIC, (x->>'max_eligible_sku_price')::NUMERIC, x->>'full_market_rounding_rule',
        (x->>'full_market_rounding_increment')::NUMERIC, x->>'full_market_rounding_rule_version',
        (x->>'source_calculation_run_id')::UUID
    FROM jsonb_array_elements(p_rows) AS x;

    IF (SELECT count(*) FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id) <> v_row_count THEN
        RAISE EXCEPTION 'persisted budget ranking row count does not reconcile with the publication payload';
    END IF;

    -- Persisted integrity is checked inside this transaction before the latest
    -- pointer moves. Any exception rolls back the snapshot replacement and rows.
    IF EXISTS (
        SELECT 1
        FROM public.budget_product_ranking_rows
        WHERE snapshot_id = v_id
        GROUP BY target_budget, budget_type
        HAVING count(*) <> min(budget_cohort_size)
            OR min(budget_cohort_size) <> max(budget_cohort_size)
            OR min(budget_rank) <> 1 OR max(budget_rank) <> count(*)
            OR count(DISTINCT budget_rank) <> count(*)
            OR min(financial_only_rank) <> 1 OR max(financial_only_rank) <> count(*)
            OR count(DISTINCT financial_only_rank) <> count(*)
    ) THEN
        RAISE EXCEPTION 'persisted budget ranking cohort size or rank contiguity validation failed';
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
             AND (budget_cohort_size <> v_expected
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
          AND (financial_rip_v4_score IS NULL OR overall_rip_v10_score IS NULL
            OR collector_appeal_score IS NULL OR chance_to_recover_capital IS NULL
            OR budget_rank IS NULL OR financial_only_rank IS NULL OR budget_tier IS NULL)
    ) THEN
        RAISE EXCEPTION 'persisted budget ranking required value validation failed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.budget_product_ranking_rows WHERE snapshot_id = v_id
          AND (abs((capital_utilization + unused_capital_percent) - 1) >= 0.000001
            OR abs((actual_committed_capital + unused_capital) - target_budget) >= 0.01)
    ) THEN
        RAISE EXCEPTION 'persisted budget ranking capital reconciliation validation failed';
    END IF;

    INSERT INTO public.budget_product_ranking_latest (ranking_method_version, allocation_method_version, snapshot_id, market_date, updated_at)
    VALUES (p_snapshot->>'ranking_method_version', p_snapshot->>'allocation_method_version', v_id, (p_snapshot->>'market_date')::DATE, timezone('utc', now()))
    ON CONFLICT (ranking_method_version, allocation_method_version) DO UPDATE SET
        snapshot_id = EXCLUDED.snapshot_id, market_date = EXCLUDED.market_date, updated_at = timezone('utc', now());

    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
