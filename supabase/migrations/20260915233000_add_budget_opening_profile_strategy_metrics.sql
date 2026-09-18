-- Opening Profile: persist exact q-unit strategy median and outcome-value concentration.
-- Existing historical snapshots remain readable with NULLs; every NEW publication
-- through the canonical RPC must provide both values from the exact strategy
-- distribution that produced expected_value / Financial RIP.
BEGIN;

ALTER TABLE public.budget_product_ranking_rows
    ADD COLUMN median_value NUMERIC,
    ADD COLUMN top1_outcome_value_share NUMERIC;

COMMENT ON COLUMN public.budget_product_ranking_rows.median_value IS
    'Median of the exact whole-unit quantity-Q strategy outcome distribution used for this budget row.';
COMMENT ON COLUMN public.budget_product_ranking_rows.top1_outcome_value_share IS
    'Share of total modeled strategy value contributed by the highest-value 1% of outcomes; sourced from Financial RIP distributionDisclosures.jackpotValueShare, never card-attribution top1EvShare.';

ALTER TABLE public.budget_product_ranking_rows
    ADD CONSTRAINT budget_product_ranking_rows_median_value_check
        CHECK (
            median_value IS NULL
            OR (
                median_value >= 0
                AND median_value::TEXT NOT IN ('NaN', 'Infinity', '-Infinity')
            )
        ),
    ADD CONSTRAINT budget_product_ranking_rows_top1_outcome_value_share_check
        CHECK (
            top1_outcome_value_share IS NULL
            OR (
                top1_outcome_value_share >= 0
                AND top1_outcome_value_share <= 1
                AND top1_outcome_value_share::TEXT NOT IN ('NaN', 'Infinity', '-Infinity')
            )
        );

CREATE OR REPLACE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_snapshot_id UUID;
    v_row_count INTEGER;
    v_v12_row_count INTEGER;
    v_is_v12 BOOLEAN := COALESCE((p_snapshot->>'ranked_under_v12_authority')::BOOLEAN, FALSE);
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'budget ranking rows must be an array';
    END IF;

    -- Exact strategy evidence required for every new publication. Historical
    -- rows may remain NULL because they predate this contract; no backfill is
    -- inferred from single-unit data.
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        WHERE NULLIF(row->>'expected_value', '') IS NULL
           OR NULLIF(row->>'median_value', '') IS NULL
           OR NULLIF(row->>'top1_outcome_value_share', '') IS NULL
           OR (row->>'expected_value')::NUMERIC < 0
           OR (row->>'median_value')::NUMERIC < 0
           OR (row->>'top1_outcome_value_share')::NUMERIC < 0
           OR (row->>'top1_outcome_value_share')::NUMERIC > 1
           OR (row->>'expected_value')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
           OR (row->>'median_value')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
           OR (row->>'top1_outcome_value_share')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
    ) THEN
        RAISE EXCEPTION 'a ranked budget row is missing or has invalid exact strategy opening-profile evidence';
    END IF;

    IF v_is_v12 THEN
        IF p_snapshot->>'overall_rip_version' IS DISTINCT FROM 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
           OR p_snapshot->>'overall_rip_v12_version' IS DISTINCT FROM 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
           OR p_snapshot->>'financial_rip_version' IS DISTINCT FROM 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
           OR p_snapshot->>'collector_appeal_version' IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
           OR p_snapshot->>'chase_accessibility_version' IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
           OR p_snapshot->>'chase_accessibility_transform_version' IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002' THEN
            RAISE EXCEPTION 'V12 budget snapshot authority metadata is missing or mismatched';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM jsonb_array_elements(p_rows) AS row
            WHERE NULLIF(row->>'overall_rip_v12_score', '') IS NULL
               OR COALESCE((row->>'overall_rip_v12_rankable')::BOOLEAN, FALSE) IS NOT TRUE
               OR row->>'overall_rip_v12_status' IS DISTINCT FROM 'ready'
               OR NULLIF(row->>'chase_accessibility_raw', '') IS NULL
               OR NULLIF(row->>'budget_rank_v12', '') IS NULL
               OR NULLIF(row->>'budget_cohort_size_v12', '') IS NULL
               OR (row->>'budget_rank_v12')::INTEGER < 1
               OR (row->>'budget_cohort_size_v12')::INTEGER < 1
               OR (row->>'budget_rank_v12')::INTEGER > (row->>'budget_cohort_size_v12')::INTEGER
        ) THEN
            RAISE EXCEPTION 'a canonical V12 budget row is missing required V12 score, authority, or rank fields';
        END IF;
    END IF;

    -- The established helper owns the original atomic V10-compatible
    -- snapshot/row write and latest-pointer move. Any exception below rolls
    -- the entire PostgreSQL transaction back, including that helper call.
    v_snapshot_id := public.publish_budget_product_ranking_snapshot_without_strategy_ev(p_snapshot, p_rows);

    UPDATE public.budget_product_ranking_rows AS persisted
    SET expected_value = (row->>'expected_value')::NUMERIC,
        median_value = (row->>'median_value')::NUMERIC,
        top1_outcome_value_share = (row->>'top1_outcome_value_share')::NUMERIC
    FROM jsonb_array_elements(p_rows) AS row
    WHERE persisted.snapshot_id = v_snapshot_id
      AND persisted.sealed_product_id = (row->>'sealed_product_id')::UUID
      AND persisted.target_budget = (row->>'target_budget')::NUMERIC
      AND persisted.budget_type = row->>'budget_type';

    SELECT count(*) INTO v_row_count
    FROM public.budget_product_ranking_rows
    WHERE snapshot_id = v_snapshot_id
      AND expected_value IS NOT NULL
      AND median_value IS NOT NULL
      AND top1_outcome_value_share IS NOT NULL;

    IF v_row_count <> jsonb_array_length(p_rows) THEN
        RAISE EXCEPTION 'persisted strategy opening-profile values do not reconcile with publication rows';
    END IF;

    IF v_is_v12 THEN
        UPDATE public.budget_product_ranking_snapshots
        SET overall_rip_v12_version = p_snapshot->>'overall_rip_v12_version',
            chase_accessibility_version = p_snapshot->>'chase_accessibility_version',
            chase_accessibility_transform_version = p_snapshot->>'chase_accessibility_transform_version',
            ranked_under_v12_authority = TRUE
        WHERE id = v_snapshot_id;

        UPDATE public.budget_product_ranking_rows AS persisted
        SET overall_rip_v12_score = (row->>'overall_rip_v12_score')::NUMERIC,
            overall_rip_v12_rankable = (row->>'overall_rip_v12_rankable')::BOOLEAN,
            overall_rip_v12_status = row->>'overall_rip_v12_status',
            chase_accessibility_raw = (row->>'chase_accessibility_raw')::NUMERIC,
            budget_rank_v12 = (row->>'budget_rank_v12')::INTEGER,
            budget_cohort_size_v12 = (row->>'budget_cohort_size_v12')::INTEGER
        FROM jsonb_array_elements(p_rows) AS row
        WHERE persisted.snapshot_id = v_snapshot_id
          AND persisted.sealed_product_id = (row->>'sealed_product_id')::UUID
          AND persisted.target_budget = (row->>'target_budget')::NUMERIC
          AND persisted.budget_type = row->>'budget_type';

        SELECT count(*) INTO v_v12_row_count
        FROM public.budget_product_ranking_rows
        WHERE snapshot_id = v_snapshot_id
          AND overall_rip_v12_score IS NOT NULL
          AND overall_rip_v12_rankable IS TRUE
          AND overall_rip_v12_status = 'ready'
          AND chase_accessibility_raw IS NOT NULL
          AND budget_rank_v12 IS NOT NULL
          AND budget_cohort_size_v12 IS NOT NULL;

        IF v_v12_row_count <> jsonb_array_length(p_rows) THEN
            RAISE EXCEPTION 'persisted V12 budget fields do not reconcile with publication rows';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM public.budget_product_ranking_rows
            WHERE snapshot_id = v_snapshot_id
            GROUP BY target_budget, budget_type
            HAVING count(*) <> min(budget_cohort_size_v12)
                OR min(budget_cohort_size_v12) <> max(budget_cohort_size_v12)
                OR min(budget_rank_v12) <> 1
                OR max(budget_rank_v12) <> count(*)
                OR count(DISTINCT budget_rank_v12) <> count(*)
        ) THEN
            RAISE EXCEPTION 'persisted V12 budget cohort size or rank contiguity validation failed';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM public.budget_product_ranking_snapshots
            WHERE id = v_snapshot_id
              AND overall_rip_version = 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
              AND overall_rip_v12_version = 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
              AND chase_accessibility_version = 'chase_accessibility_v1_hc_value_squared_modeled_probability'
              AND chase_accessibility_transform_version = 'chase_accessibility_overall_score_v1_saturating_k002'
              AND ranked_under_v12_authority IS TRUE
        ) THEN
            RAISE EXCEPTION 'persisted V12 budget snapshot authority validation failed';
        END IF;
    END IF;

    RETURN v_snapshot_id;
END;
$function$;

COMMIT;
