-- Bucket 3A: PRIVATE durable persistence for Best-Open Price search results.
-- Separate authority from budget_product_ranking_rows: this store records,
-- per Full Market eligible product, the exact one-cent price threshold at
-- which that product's rank/leadership status against the engine's pinned
-- benchmark would change under the validated ExactBestOpenPriceSearch
-- (backend/calculations/evr/best_open_price.py, method version
-- budget_product_best_open_price_full_market_v1).
--
-- No public grants. No frontend/API surface. service_role only.

BEGIN;

CREATE TABLE public.budget_product_best_open_price_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    built_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Source-identity binding: the exact live budget-ranking authority this
    -- snapshot was computed against. Every field here is re-verified against
    -- the LIVE budget_product_ranking_snapshots/_rows row-by-row inside the
    -- publication RPC before anything is written (see migration RPC below).
    source_budget_snapshot_id UUID NOT NULL,
    source_budget_published_at TIMESTAMPTZ NOT NULL,
    source_market_date DATE NOT NULL,
    source_cohort_fingerprint TEXT NOT NULL,
    source_full_market_row_fingerprint TEXT NOT NULL,
    source_full_market_budget NUMERIC NOT NULL CHECK (source_full_market_budget > 0),
    source_eligible_cohort_count INTEGER NOT NULL CHECK (source_eligible_cohort_count > 0),

    -- Model-authority version identity. Every one must match the source
    -- ranking row-for-row; there is no partial-authority publication.
    ranking_method_version TEXT NOT NULL,
    allocation_method_version TEXT NOT NULL,
    comparison_scope_version TEXT NOT NULL,
    financial_rip_version TEXT NOT NULL,
    overall_rip_v12_version TEXT NOT NULL,
    collector_appeal_version TEXT NOT NULL,
    chase_accessibility_version TEXT NOT NULL,
    chase_accessibility_transform_version TEXT NOT NULL,
    best_open_price_method_version TEXT NOT NULL,

    -- Diagnostics: aggregate only. Per-candidate probe dumps are NOT stored
    -- here (row table keeps only light search diagnostics; see below).
    resolved_count INTEGER NOT NULL CHECK (resolved_count >= 0),
    unresolved_count INTEGER NOT NULL CHECK (unresolved_count >= 0),
    runtime_seconds NUMERIC NOT NULL CHECK (runtime_seconds >= 0),
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    CHECK (resolved_count + unresolved_count = source_eligible_cohort_count)
);

CREATE TABLE public.budget_product_best_open_price_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES public.budget_product_best_open_price_snapshots(id) ON DELETE CASCADE,

    -- Identity.
    sealed_product_id UUID NOT NULL,
    set_id UUID NOT NULL,
    product_family TEXT NOT NULL,
    source_calculation_run_id UUID,

    -- Current source state at computation time (cross-checked against the
    -- live budget_product_ranking_rows row for this product by the RPC).
    current_market_price NUMERIC NOT NULL CHECK (current_market_price >= 0
        AND current_market_price = round(current_market_price, 2)),
    current_quantity INTEGER NOT NULL CHECK (current_quantity > 0),
    current_budget_rank INTEGER NOT NULL CHECK (current_budget_rank >= 1),
    current_overall_rip_v12_score NUMERIC,
    -- Raw source + benchmark evidence: enough to reproduce the canonical
    -- comparison even if budget_product_ranking_rows is later replaced or
    -- mutated. Version-string-only cross-checks are NOT equivalent to
    -- raw-value cross-checks -- these are the raw component inputs to the
    -- Overall RIP V12 comparator (see
    -- backend/calculations/evr/budget_normalized_product_ranking.py
    -- ``_tier_sort_key_v12``: Overall RIP V12 -> Financial RIP V4 ->
    -- chance-to-recover-capital -> committed-capital-closeness-to-target).
    current_financial_rip_v4_score NUMERIC,
    current_collector_appeal_score NUMERIC,
    current_chase_accessibility_raw NUMERIC,
    current_chance_to_recover_capital NUMERIC CHECK (current_chance_to_recover_capital IS NULL
        OR (current_chance_to_recover_capital >= 0 AND current_chance_to_recover_capital <= 1)),
    -- Committed-capital tie-break evidence, named to match the source
    -- column (budget_product_ranking_rows.actual_committed_capital) that
    -- the canonical comparator's utilisation tie-break actually reads.
    current_actual_committed_capital NUMERIC NOT NULL CHECK (current_actual_committed_capital > 0),

    -- Status taxonomy locked to engine-supported values only.
    status TEXT NOT NULL CHECK (status IN (
        'resolved_below_market', 'current_number_one_with_headroom', 'resolved_at_market'
    )),

    -- Threshold fields. NULL together iff status is unresolved -- but the
    -- taxonomy above admits no unresolved value, so an approved-unavailable
    -- product simply has no row in this table for this snapshot.
    best_open_price NUMERIC NOT NULL CHECK (best_open_price >= 0
        AND best_open_price = round(best_open_price, 2)),
    threshold_quantity INTEGER NOT NULL CHECK (threshold_quantity > 0),
    price_gap_dollars NUMERIC NOT NULL,
    price_gap_percent NUMERIC,

    -- Benchmark fields.
    benchmark_sealed_product_id UUID NOT NULL,
    benchmark_overall_rip_v12_score NUMERIC NOT NULL,
    -- Same raw-evidence discipline as the current_* fields above, but for
    -- the pinned benchmark row the engine compared against, so a historical
    -- publication carries the full comparator input on BOTH sides.
    benchmark_financial_rip_v4_score NUMERIC NOT NULL,
    benchmark_chance_to_recover_capital NUMERIC CHECK (benchmark_chance_to_recover_capital IS NULL
        OR (benchmark_chance_to_recover_capital >= 0 AND benchmark_chance_to_recover_capital <= 1)),
    benchmark_actual_committed_capital NUMERIC NOT NULL CHECK (benchmark_actual_committed_capital > 0),

    -- Light search diagnostics only -- no per-candidate probe dump.
    candidate_price_evaluations INTEGER NOT NULL CHECK (candidate_price_evaluations >= 0),
    bracket_expansions INTEGER NOT NULL CHECK (bracket_expansions >= 0),
    bracket_refinements INTEGER NOT NULL CHECK (bracket_refinements >= 0),
    monotonicity_fallback_count INTEGER NOT NULL CHECK (monotonicity_fallback_count >= 0),
    search_wall_seconds NUMERIC NOT NULL CHECK (search_wall_seconds >= 0),

    -- Status invariants: resolved_below_market strictly below current
    -- market with a positive gap; current_number_one_with_headroom at or
    -- above current market (headroom is NOT a discount); resolved_at_market
    -- exactly equal.
    CHECK (
        (status = 'resolved_below_market'
            AND best_open_price < current_market_price AND price_gap_dollars > 0)
        OR (status = 'current_number_one_with_headroom'
            AND best_open_price >= current_market_price AND price_gap_dollars <= 0)
        OR (status = 'resolved_at_market'
            AND best_open_price = current_market_price AND price_gap_dollars = 0)
    ),

    UNIQUE (snapshot_id, sealed_product_id)
);

CREATE INDEX idx_budget_product_best_open_price_rows_snapshot
    ON public.budget_product_best_open_price_rows(snapshot_id);

CREATE TABLE public.budget_product_best_open_price_latest (
    best_open_price_method_version TEXT PRIMARY KEY,
    snapshot_id UUID NOT NULL REFERENCES public.budget_product_best_open_price_snapshots(id),
    source_budget_snapshot_id UUID NOT NULL,
    source_budget_published_at TIMESTAMPTZ NOT NULL,
    source_market_date DATE NOT NULL,
    source_cohort_fingerprint TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

ALTER TABLE public.budget_product_best_open_price_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_product_best_open_price_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_product_best_open_price_latest ENABLE ROW LEVEL SECURITY;

-- No permissive policies are created: with RLS enabled and no policy, only
-- roles that bypass RLS (service_role, table owner) can read/write at all.
REVOKE ALL ON public.budget_product_best_open_price_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.budget_product_best_open_price_rows FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.budget_product_best_open_price_latest FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------
-- Atomic SECURITY DEFINER publication RPC. service_role only. ONE
-- transaction: source-identity re-verification, row-count/1:1 identity
-- check, per-row cross-check against the LIVE budget_product_ranking_rows,
-- status-invariant enforcement (already CHECK-enforced at insert, but also
-- defensively re-verified post-insert below), snapshot+rows insert, and the
-- latest-pointer move. Any failure rolls back everything.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publish_budget_product_best_open_price_snapshot(
    p_snapshot JSONB, p_rows JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions
AS $$
DECLARE
    v_id UUID;
    v_existing_id UUID;
    v_row_count INTEGER;
    v_distinct_rows INTEGER;
    v_live_snapshot RECORD;
    v_content_fingerprint TEXT;
    v_existing_content_fingerprint TEXT;
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'best-open-price rows must be an array';
    END IF;
    v_row_count := jsonb_array_length(p_rows);
    IF v_row_count = 0 THEN
        RAISE EXCEPTION 'refusing to publish an empty best-open-price snapshot';
    END IF;

    -- 1:1 row identity: no duplicates, count matches resolved_count.
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

    -- 2. Re-verify current LIVE source identity/versions/fingerprints
    -- exactly match the payload. Never trust the payload's self-reported
    -- source binding without cross-checking the live authority.
    SELECT s.id, s.published_at, s.market_date, s.cohort_fingerprint, s.eligible_cohort_count, s.full_market_budget,
           s.ranking_method_version, s.allocation_method_version, s.comparison_scope_version,
           s.financial_rip_version, s.overall_rip_version, s.collector_appeal_version,
           s.chase_accessibility_version, s.chase_accessibility_transform_version
    INTO v_live_snapshot
    FROM public.budget_product_ranking_latest lp
    JOIN public.budget_product_ranking_snapshots s ON s.id = lp.snapshot_id
    WHERE lp.ranking_method_version = p_snapshot->>'ranking_method_version'
      AND lp.allocation_method_version = p_snapshot->>'allocation_method_version'
    LIMIT 1;

    IF v_live_snapshot.id IS NULL THEN
        RAISE EXCEPTION 'no live budget ranking source found for the requested method/allocation versions';
    END IF;
    IF v_live_snapshot.id IS DISTINCT FROM (p_snapshot->>'source_budget_snapshot_id')::UUID
       OR v_live_snapshot.published_at IS DISTINCT FROM (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ
       OR v_live_snapshot.market_date IS DISTINCT FROM (p_snapshot->>'source_market_date')::DATE
       OR v_live_snapshot.cohort_fingerprint IS DISTINCT FROM (p_snapshot->>'source_cohort_fingerprint')
       OR v_live_snapshot.eligible_cohort_count IS DISTINCT FROM (p_snapshot->>'source_eligible_cohort_count')::INTEGER
       OR v_live_snapshot.full_market_budget IS DISTINCT FROM (p_snapshot->>'source_full_market_budget')::NUMERIC
       OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM (p_snapshot->>'comparison_scope_version')
       OR v_live_snapshot.financial_rip_version IS DISTINCT FROM (p_snapshot->>'financial_rip_version')
       OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM (p_snapshot->>'collector_appeal_version')
       OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM (p_snapshot->>'chase_accessibility_version')
       OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM (p_snapshot->>'chase_accessibility_transform_version')
    THEN
        RAISE EXCEPTION 'best-open-price payload source binding no longer matches the live budget ranking authority (stale or non-deterministic input)';
    END IF;

    -- 3. Cross-check each incoming row's current-source-state fields
    -- DIRECTLY against the live budget_product_ranking_rows for that
    -- product -- not just trusting the snapshot-level fingerprint match.
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        LEFT JOIN public.budget_product_ranking_rows live
          ON live.snapshot_id = v_live_snapshot.id
         AND live.sealed_product_id = (row->>'sealed_product_id')::UUID
         AND live.budget_type = 'full_market'
        WHERE live.sealed_product_id IS NULL
           OR live.product_market_price IS DISTINCT FROM (row->>'current_market_price')::NUMERIC
           OR live.quantity IS DISTINCT FROM (row->>'current_quantity')::INTEGER
           OR live.budget_rank_v12 IS DISTINCT FROM (row->>'current_budget_rank')::INTEGER
           OR live.overall_rip_v12_score IS DISTINCT FROM (row->>'current_overall_rip_v12_score')::NUMERIC
           OR live.set_id IS DISTINCT FROM (row->>'set_id')::UUID
           OR live.source_calculation_run_id IS DISTINCT FROM NULLIF(row->>'source_calculation_run_id', '')::UUID
           OR live.financial_rip_v4_score IS DISTINCT FROM (row->>'current_financial_rip_v4_score')::NUMERIC
           OR live.collector_appeal_score IS DISTINCT FROM (row->>'current_collector_appeal_score')::NUMERIC
           OR live.chase_accessibility_raw IS DISTINCT FROM (row->>'current_chase_accessibility_raw')::NUMERIC
           OR live.chance_to_recover_capital IS DISTINCT FROM (row->>'current_chance_to_recover_capital')::NUMERIC
           OR live.actual_committed_capital IS DISTINCT FROM (row->>'current_actual_committed_capital')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live Full Market ranking rows';
    END IF;

    -- 3b. Cross-check each incoming row's BENCHMARK evidence directly
    -- against the live budget_product_ranking_rows for the pinned benchmark
    -- product -- the same raw-value discipline as 3 above, applied to the
    -- comparator's other side.
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_rows) AS row
        LEFT JOIN public.budget_product_ranking_rows bench
          ON bench.snapshot_id = v_live_snapshot.id
         AND bench.sealed_product_id = (row->>'benchmark_sealed_product_id')::UUID
         AND bench.budget_type = 'full_market'
        WHERE bench.sealed_product_id IS NULL
           OR bench.overall_rip_v12_score IS DISTINCT FROM (row->>'benchmark_overall_rip_v12_score')::NUMERIC
           OR bench.financial_rip_v4_score IS DISTINCT FROM (row->>'benchmark_financial_rip_v4_score')::NUMERIC
           OR bench.chance_to_recover_capital IS DISTINCT FROM (row->>'benchmark_chance_to_recover_capital')::NUMERIC
           OR bench.actual_committed_capital IS DISTINCT FROM (row->>'benchmark_actual_committed_capital')::NUMERIC
    ) THEN
        RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live benchmark ranking row';
    END IF;

    -- 4. Cohort membership must equal the full live Full Market cohort size
    -- (some products may be legitimately absent only as pre-approved
    -- unresolved statuses accounted for in unresolved_count -- resolved
    -- rows plus unresolved_count must equal the live cohort size).
    IF (v_row_count + (p_snapshot->>'unresolved_count')::INTEGER) <> v_live_snapshot.eligible_cohort_count THEN
        RAISE EXCEPTION 'resolved_count + unresolved_count does not equal the live eligible cohort count';
    END IF;

    -- 5. Cent-precision guard defense-in-depth (also CHECK-enforced at
    -- table level): reject any fractional-cent money field in the payload.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) AS row
        WHERE (row->>'current_market_price')::NUMERIC <> round((row->>'current_market_price')::NUMERIC, 2)
           OR (row->>'best_open_price')::NUMERIC <> round((row->>'best_open_price')::NUMERIC, 2)
    ) THEN
        RAISE EXCEPTION 'a best-open-price money field is not exact-cent precision';
    END IF;

    -- Idempotency / non-determinism guard: if a snapshot already exists for
    -- this exact (source identity, method version), and its content
    -- fingerprint differs from this payload's, refuse loudly rather than
    -- silently replacing a differing publication under the same identity.
    v_content_fingerprint := encode(digest(p_rows::TEXT, 'sha256'), 'hex');
    SELECT s.id, s.diagnostics_json->>'content_fingerprint'
    INTO v_existing_id, v_existing_content_fingerprint
    FROM public.budget_product_best_open_price_snapshots s
    WHERE s.source_budget_snapshot_id = (p_snapshot->>'source_budget_snapshot_id')::UUID
      AND s.source_budget_published_at = (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ
      AND s.best_open_price_method_version = p_snapshot->>'best_open_price_method_version'
    ORDER BY s.built_at DESC
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        IF v_existing_content_fingerprint = v_content_fingerprint THEN
            -- Identical republish under identical source identity: idempotent no-op.
            RETURN v_existing_id;
        ELSE
            RAISE EXCEPTION 'non-deterministic content for identical source identity and method version (existing snapshot %); refusing silent replace',
                v_existing_id;
        END IF;
    END IF;

    INSERT INTO public.budget_product_best_open_price_snapshots (
        built_at, source_budget_snapshot_id, source_budget_published_at, source_market_date,
        source_cohort_fingerprint, source_full_market_row_fingerprint, source_full_market_budget,
        source_eligible_cohort_count,
        ranking_method_version, allocation_method_version, comparison_scope_version,
        financial_rip_version, overall_rip_v12_version, collector_appeal_version,
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
        p_snapshot->>'financial_rip_version', p_snapshot->>'overall_rip_v12_version', p_snapshot->>'collector_appeal_version',
        p_snapshot->>'chase_accessibility_version', p_snapshot->>'chase_accessibility_transform_version',
        p_snapshot->>'best_open_price_method_version',
        (p_snapshot->>'resolved_count')::INTEGER, (p_snapshot->>'unresolved_count')::INTEGER,
        (p_snapshot->>'runtime_seconds')::NUMERIC,
        COALESCE(p_snapshot->'diagnostics_json', '{}'::jsonb) || jsonb_build_object('content_fingerprint', v_content_fingerprint)
    ) RETURNING id INTO v_id;

    INSERT INTO public.budget_product_best_open_price_rows (
        snapshot_id, sealed_product_id, set_id, product_family, source_calculation_run_id,
        current_market_price, current_quantity, current_budget_rank, current_overall_rip_v12_score,
        current_financial_rip_v4_score, current_collector_appeal_score, current_chase_accessibility_raw,
        current_chance_to_recover_capital, current_actual_committed_capital,
        status, best_open_price, threshold_quantity, price_gap_dollars, price_gap_percent,
        benchmark_sealed_product_id, benchmark_overall_rip_v12_score,
        benchmark_financial_rip_v4_score, benchmark_chance_to_recover_capital, benchmark_actual_committed_capital,
        candidate_price_evaluations, bracket_expansions, bracket_refinements,
        monotonicity_fallback_count, search_wall_seconds
    )
    SELECT
        v_id, (x->>'sealed_product_id')::UUID, (x->>'set_id')::UUID, x->>'product_family',
        NULLIF(x->>'source_calculation_run_id', '')::UUID,
        (x->>'current_market_price')::NUMERIC, (x->>'current_quantity')::INTEGER,
        (x->>'current_budget_rank')::INTEGER, (x->>'current_overall_rip_v12_score')::NUMERIC,
        (x->>'current_financial_rip_v4_score')::NUMERIC, (x->>'current_collector_appeal_score')::NUMERIC,
        (x->>'current_chase_accessibility_raw')::NUMERIC,
        (x->>'current_chance_to_recover_capital')::NUMERIC, (x->>'current_actual_committed_capital')::NUMERIC,
        x->>'status', (x->>'best_open_price')::NUMERIC, (x->>'threshold_quantity')::INTEGER,
        (x->>'price_gap_dollars')::NUMERIC, NULLIF(x->>'price_gap_percent', '')::NUMERIC,
        (x->>'benchmark_sealed_product_id')::UUID, (x->>'benchmark_overall_rip_v12_score')::NUMERIC,
        (x->>'benchmark_financial_rip_v4_score')::NUMERIC, (x->>'benchmark_chance_to_recover_capital')::NUMERIC,
        (x->>'benchmark_actual_committed_capital')::NUMERIC,
        (x->>'candidate_price_evaluations')::INTEGER, (x->>'bracket_expansions')::INTEGER,
        (x->>'bracket_refinements')::INTEGER, (x->>'monotonicity_fallback_count')::INTEGER,
        (x->>'search_wall_seconds')::NUMERIC
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

REVOKE ALL ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
