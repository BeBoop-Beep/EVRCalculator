-- Persist the authoritative mean of each real multi-unit strategy distribution.
-- Historical rows remain nullable: reconstructing them from single-unit EV would be
-- statistically invalid. A canonical republish fills the current snapshot.
BEGIN;
ALTER TABLE public.budget_product_ranking_rows ADD COLUMN expected_value NUMERIC;
COMMENT ON COLUMN public.budget_product_ranking_rows.expected_value IS 'Mean of the real quantity-Q strategy outcome distribution; never reconstructed from single-unit EV.';
ALTER FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) RENAME TO publish_budget_product_ranking_snapshot_without_strategy_ev;
REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot_without_strategy_ev(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
CREATE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_snapshot_id UUID; v_row_count INTEGER;
BEGIN
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
    RETURN v_snapshot_id;
END; $$;
REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) TO service_role;
REVOKE ALL ON public.budget_product_ranking_snapshots, public.budget_product_ranking_rows, public.budget_product_ranking_latest FROM PUBLIC, anon, authenticated;
COMMIT;
