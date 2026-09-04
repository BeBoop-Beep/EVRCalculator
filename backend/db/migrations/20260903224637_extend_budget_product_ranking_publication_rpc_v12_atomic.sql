-- Extend the budget-ranking publication RPC to atomically persist Overall
-- RIP V12 / Chase Accessibility authority fields (Gate F closure).
--
-- SOURCE-ONLY IN THIS REPOSITORY CHANGE. The equivalent SQL has already been applied
-- to production externally, under the migration identity
-- `extend_budget_product_ranking_publication_rpc_v12_atomic`
-- (Supabase migration timestamp 20260903224637). This file is added to
-- repository history to match that already-live behavior; it must NOT be
-- (re)applied to any environment as part of this change.
--
-- Architecture preserved exactly as production has it (two functions, not
-- one):
--   * `public.publish_budget_product_ranking_snapshot_without_strategy_ev`
--     (untouched by this migration) — the original atomic snapshot/row
--     write, integrity checks, and `budget_product_ranking_latest` pointer
--     move.
--   * `public.publish_budget_product_ranking_snapshot` (the OUTER wrapper,
--     replaced here) — first persists `expected_value` exactly as
--     `20260825154658_expose_budget_product_strategy_expected_value.sql`
--     already made it do (that logic is copied verbatim below, not
--     rewritten), then, STILL INSIDE THE SAME TRANSACTION, if
--     `ranked_under_v12_authority = true` in `p_snapshot`, validates the
--     exact locked V12/Financial/Collector/Accessibility/transform identity
--     strings, UPDATEs the just-created snapshot/rows with the ten V12
--     authority fields added by
--     `20260902010000_add_budget_product_ranking_v12_authority_columns.sql`,
--     and validates persisted V12 row completeness and per-cohort V12 rank
--     contiguity. Any exception in the V12 branch (or anywhere else in this
--     function) rolls back the ENTIRE transaction — the snapshot insert,
--     row insert, expected_value update, and the inner helper's own
--     `latest` pointer move — via ordinary Postgres function-call
--     transaction semantics. No custom rollback logic is added.
--
-- The V12 branch is dormant (a no-op) whenever
-- `COALESCE((p_snapshot->>'ranked_under_v12_authority')::BOOLEAN, FALSE)`
-- is false, which is the default for every existing/explicit V10 caller —
-- V10 publication behavior is completely unchanged.

BEGIN;

CREATE OR REPLACE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_snapshot_id UUID;
    v_row_count INTEGER;
    v_ranked_v12 BOOLEAN;
    v_v12_row_count INTEGER;
BEGIN
    -- ---- Verbatim existing expected_value behavior (outer wrapper), from
    -- ---- 20260825154658_expose_budget_product_strategy_expected_value.sql.
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'budget ranking rows must be an array'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rows) AS row WHERE NULLIF(row->>'expected_value', '') IS NULL OR (row->>'expected_value')::NUMERIC < 0) THEN
        RAISE EXCEPTION 'a ranked budget row is missing its real strategy expected value';
    END IF;
    v_snapshot_id := public.publish_budget_product_ranking_snapshot_without_strategy_ev(p_snapshot, p_rows);
    UPDATE public.budget_product_ranking_rows AS persisted SET expected_value = (row->>'expected_value')::NUMERIC
    FROM jsonb_array_elements(p_rows) AS row WHERE persisted.snapshot_id = v_snapshot_id
      AND persisted.sealed_product_id = (row->>'sealed_product_id')::UUID
      AND persisted.target_budget = (row->>'target_budget')::NUMERIC AND persisted.budget_type = row->>'budget_type';
    SELECT count(*) INTO v_row_count FROM public.budget_product_ranking_rows WHERE snapshot_id = v_snapshot_id AND expected_value IS NOT NULL;
    IF v_row_count <> jsonb_array_length(p_rows) THEN RAISE EXCEPTION 'persisted strategy expected values do not reconcile with publication rows'; END IF;

    -- ---- NEW: explicit-opt-in Overall RIP V12 authority persistence,
    -- ---- added by this migration. Dormant unless the caller explicitly
    -- ---- flags this snapshot as ranked under V12 authority.
    v_ranked_v12 := COALESCE((p_snapshot->>'ranked_under_v12_authority')::BOOLEAN, FALSE);
    IF v_ranked_v12 THEN
        -- Locked-identity requirement: V12 authority may only be persisted
        -- under the exact canonical model identities. Any mismatch aborts
        -- the whole publication (including the V10 work already done
        -- above in this same transaction).
        IF p_snapshot->>'overall_rip_v12_version' IS DISTINCT FROM 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5' THEN
            RAISE EXCEPTION 'V12 publication requires the exact locked overall_rip_v12_version identity';
        END IF;
        IF p_snapshot->>'financial_rip_version' IS DISTINCT FROM 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5' THEN
            RAISE EXCEPTION 'V12 publication requires the exact locked financial_rip_version identity';
        END IF;
        IF p_snapshot->>'collector_appeal_version' IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2' THEN
            RAISE EXCEPTION 'V12 publication requires the exact locked collector_appeal_version identity';
        END IF;
        IF p_snapshot->>'chase_accessibility_version' IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability' THEN
            RAISE EXCEPTION 'V12 publication requires the exact locked chase_accessibility_version identity';
        END IF;
        IF p_snapshot->>'chase_accessibility_transform_version' IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002' THEN
            RAISE EXCEPTION 'V12 publication requires the exact locked chase_accessibility_transform_version identity';
        END IF;

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
          AND overall_rip_v12_rankable IS NOT NULL
          AND overall_rip_v12_status IS NOT NULL
          AND chase_accessibility_raw IS NOT NULL
          AND budget_rank_v12 IS NOT NULL
          AND budget_cohort_size_v12 IS NOT NULL;
        IF v_v12_row_count <> jsonb_array_length(p_rows) THEN
            RAISE EXCEPTION 'persisted V12 authority fields do not reconcile with publication rows';
        END IF;

        -- V12 rank/cohort-size contiguity per (target_budget, budget_type)
        -- cohort — the same shape of check the inner helper already
        -- performs for the V10 budget_rank/budget_cohort_size columns.
        IF EXISTS (
            SELECT 1
            FROM public.budget_product_ranking_rows
            WHERE snapshot_id = v_snapshot_id
            GROUP BY target_budget, budget_type
            HAVING count(*) <> min(budget_cohort_size_v12)
                OR min(budget_cohort_size_v12) <> max(budget_cohort_size_v12)
                OR min(budget_rank_v12) <> 1 OR max(budget_rank_v12) <> count(*)
                OR count(DISTINCT budget_rank_v12) <> count(*)
        ) THEN
            RAISE EXCEPTION 'persisted V12 budget ranking cohort size or rank contiguity validation failed';
        END IF;
    END IF;

    RETURN v_snapshot_id;
END; $$;

REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
