-- Best-Open Price V2: additive dual-threshold columns. Historical V1 rows
-- remain valid with every column below NULL. No backfill required or
-- performed. See supabase/migrations/20260914184759_..._store.sql and
-- 20260914225000_harden_best_open_publication_review.sql for the V1
-- authority this extends.
--
-- V2 adds a second, independent Financial-only threshold search alongside
-- the existing (RIP-benchmarked) threshold, plus the raw dual
-- threshold-evidence (RIP set and Financial set) needed to reproduce both
-- comparisons without re-deriving them from budget_product_ranking_rows.
-- The publication RPC below is CREATE OR REPLACE'd to branch on
-- best_open_price_method_version: the V1 literal runs the existing
-- hardened V1 body completely unchanged; a new V2 literal runs a new,
-- parallel validation body requiring this migration's new columns.

BEGIN;

ALTER TABLE public.budget_product_best_open_price_rows
  ADD COLUMN current_financial_only_rank INTEGER
    CHECK (current_financial_only_rank IS NULL OR current_financial_only_rank >= 1),

  ADD COLUMN financial_status TEXT
    CHECK (financial_status IS NULL OR financial_status IN (
      'resolved_below_market', 'current_number_one_with_headroom', 'resolved_at_market'
    )),
  ADD COLUMN financial_best_open_price NUMERIC
    CHECK (financial_best_open_price IS NULL OR (
      financial_best_open_price > 0
      AND financial_best_open_price < 'Infinity'::NUMERIC
      AND financial_best_open_price = round(financial_best_open_price, 2)
    )),
  ADD COLUMN financial_threshold_quantity INTEGER
    CHECK (financial_threshold_quantity IS NULL OR financial_threshold_quantity > 0),
  ADD COLUMN financial_price_gap_dollars NUMERIC,
  ADD COLUMN financial_price_gap_percent NUMERIC,

  ADD COLUMN financial_benchmark_sealed_product_id UUID,
  ADD COLUMN financial_benchmark_financial_rip_v4_score NUMERIC,
  ADD COLUMN financial_benchmark_overall_rip_v12_score NUMERIC,

  ADD COLUMN threshold_financial_rip_v4_score NUMERIC,
  ADD COLUMN threshold_overall_rip_v12_score NUMERIC,
  ADD COLUMN threshold_chance_to_recover_capital NUMERIC
    CHECK (threshold_chance_to_recover_capital IS NULL OR (
      threshold_chance_to_recover_capital >= 0 AND threshold_chance_to_recover_capital <= 1
    )),
  ADD COLUMN threshold_actual_committed_capital NUMERIC
    CHECK (threshold_actual_committed_capital IS NULL OR (
      threshold_actual_committed_capital > 0
      AND threshold_actual_committed_capital < 'Infinity'::NUMERIC
    )),

  ADD COLUMN financial_threshold_financial_rip_v4_score NUMERIC,
  ADD COLUMN financial_threshold_overall_rip_v12_score NUMERIC,
  ADD COLUMN financial_threshold_chance_to_recover_capital NUMERIC
    CHECK (financial_threshold_chance_to_recover_capital IS NULL OR (
      financial_threshold_chance_to_recover_capital >= 0
      AND financial_threshold_chance_to_recover_capital <= 1
    )),
  ADD COLUMN financial_threshold_actual_committed_capital NUMERIC
    CHECK (financial_threshold_actual_committed_capital IS NULL OR (
      financial_threshold_actual_committed_capital > 0
      AND financial_threshold_actual_committed_capital < 'Infinity'::NUMERIC
    ));

ALTER TABLE public.budget_product_best_open_price_rows
  ADD CONSTRAINT budget_best_open_v2_gap_arithmetic
  CHECK (
    financial_best_open_price IS NULL
    OR (
      financial_price_gap_dollars = current_market_price - financial_best_open_price
      AND financial_price_gap_percent IS NOT NULL
      AND abs(financial_price_gap_percent - financial_price_gap_dollars / NULLIF(current_market_price, 0)) <= 0.000000000001
    )
  ),
  ADD CONSTRAINT budget_best_open_v2_direction
  CHECK (
    financial_best_open_price IS NULL
    OR current_financial_only_rank IS NULL
    OR (current_financial_only_rank = 1 AND financial_best_open_price >= current_market_price)
    OR (current_financial_only_rank <> 1 AND financial_best_open_price <= current_market_price)
  ),
  ADD CONSTRAINT budget_best_open_v2_not_self_financial_benchmark
  CHECK (financial_benchmark_sealed_product_id IS NULL OR sealed_product_id <> financial_benchmark_sealed_product_id);

-- ---------------------------------------------------------------------
-- CREATE OR REPLACE the publication RPC to branch on
-- best_open_price_method_version. The V1 branch below is a byte-for-byte
-- verbatim copy of the current hardened V1 body from
-- 20260914225000_harden_best_open_publication_review.sql -- every
-- condition, message, and column reference is unchanged. Only the DECLARE
-- block was merged (all V1 variable names preserved; V2-only variables
-- added with no name collisions) and the top-level method-version gate was
-- converted from a single hard literal check into an IF/ELSIF/ELSE
-- dispatch, since PL/pgSQL requires one shared DECLARE block per function.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.publish_budget_product_best_open_price_snapshot(
    p_snapshot JSONB, p_rows JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, extensions, pg_temp
AS $$
DECLARE
    v_method_version TEXT := p_snapshot->>'best_open_price_method_version';
    -- V1 DECLARE block, verbatim.
    v_id UUID;
    v_existing_id UUID;
    v_row_count INTEGER;
    v_distinct_rows INTEGER;
    v_live_snapshot RECORD;
    v_content_fingerprint TEXT;
    v_existing_content_fingerprint TEXT;
    v_candidate_source_id UUID;
    v_locked_pointer_id UUID;
    v_live_count INTEGER;
    v_source_columns TEXT[];
    v_incoming_content JSONB;
    v_stored_content JSONB;
    -- V2-only DECLARE additions (no name collisions with the V1 block above).
    v_financial_incoming_content JSONB;
BEGIN
    IF v_method_version = 'budget_product_best_open_price_full_market_v1' THEN
        -- =================================================================
        -- V1 BRANCH: verbatim copy of the current hardened V1 body.
        -- =================================================================
        IF jsonb_typeof(p_snapshot) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'best-open-price snapshot must be an object';
        END IF;
        IF p_snapshot->>'best_open_price_method_version' IS DISTINCT FROM
           'budget_product_best_open_price_full_market_v1' THEN
            RAISE EXCEPTION 'unsupported Best-Open Price method version';
        END IF;
        IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'best-open-price rows must be an array';
        END IF;
        v_row_count := jsonb_array_length(p_rows);
        IF v_row_count = 0 THEN
            RAISE EXCEPTION 'refusing to publish an empty best-open-price snapshot';
        END IF;

        IF (p_snapshot->>'runtime_seconds')::NUMERIC IS NULL
           OR (p_snapshot->>'runtime_seconds')::NUMERIC < 0
           OR (p_snapshot->>'runtime_seconds')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
           OR NULLIF(p_snapshot->>'source_full_market_row_fingerprint','') IS NULL THEN
            RAISE EXCEPTION 'invalid snapshot timing/source fingerprint';
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

        -- Lock in the upstream writer's order: source snapshot, then latest pointer.
        -- A plain SELECT followed by validation permits a concurrent same-ID
        -- republish to commit between validation and publication. These short
        -- transaction locks serialize both source replacement and identical builds.
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

        IF v_live_snapshot.ranked_under_v12_authority IS DISTINCT FROM TRUE
           OR v_live_snapshot.ranking_method_version IS DISTINCT FROM 'budget_product_ranking_v1'
           OR v_live_snapshot.allocation_method_version IS DISTINCT FROM 'budget_allocation_floor_quantity_v1'
           OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM 'budget_constrained_whole_unit_cross_format_v1'
           OR v_live_snapshot.financial_rip_version IS DISTINCT FROM 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
           OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
           OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
           OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002'
           OR v_live_snapshot.overall_rip_version IS DISTINCT FROM
              'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
           OR v_live_snapshot.overall_rip_v12_version IS DISTINCT FROM v_live_snapshot.overall_rip_version
           OR v_live_snapshot.overall_rip_version IS DISTINCT FROM p_snapshot->>'overall_rip_v12_version'
           OR v_live_snapshot.id IS DISTINCT FROM (p_snapshot->>'source_budget_snapshot_id')::UUID
           OR v_live_snapshot.published_at IS DISTINCT FROM (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ
           OR v_live_snapshot.market_date IS DISTINCT FROM (p_snapshot->>'source_market_date')::DATE
           OR v_live_snapshot.cohort_fingerprint IS DISTINCT FROM p_snapshot->>'source_cohort_fingerprint'
           OR v_live_snapshot.eligible_cohort_count IS DISTINCT FROM (p_snapshot->>'source_eligible_cohort_count')::INTEGER
           OR v_live_snapshot.full_market_budget IS DISTINCT FROM (p_snapshot->>'source_full_market_budget')::NUMERIC
           OR v_live_snapshot.ranking_method_version IS DISTINCT FROM p_snapshot->>'ranking_method_version'
           OR v_live_snapshot.allocation_method_version IS DISTINCT FROM p_snapshot->>'allocation_method_version'
           OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM p_snapshot->>'comparison_scope_version'
           OR v_live_snapshot.financial_rip_version IS DISTINCT FROM p_snapshot->>'financial_rip_version'
           OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM p_snapshot->>'collector_appeal_version'
           OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM p_snapshot->>'chase_accessibility_version'
           OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM p_snapshot->>'chase_accessibility_transform_version'
        THEN
            RAISE EXCEPTION 'best-open-price source binding no longer matches live V12 authority';
        END IF;

        -- Freeze the small source row population as well. No locks are held during
        -- the hour-long Python computation; all of these are publication-time only.
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

        -- Numeric input must be finite, non-null and genuinely integral where
        -- required. Casting NUMERIC to INTEGER alone silently rounds fractional q.
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            CROSS JOIN unnest(ARRAY[
                'current_market_price','best_open_price','current_quantity','threshold_quantity',
                'current_budget_rank','current_overall_rip_v12_score','current_financial_rip_v4_score',
                'current_collector_appeal_score','current_chase_accessibility_raw',
                'current_chance_to_recover_capital','current_actual_committed_capital',
                'benchmark_overall_rip_v12_score','benchmark_financial_rip_v4_score',
                'benchmark_chance_to_recover_capital','benchmark_actual_committed_capital',
                'price_gap_dollars','price_gap_percent','candidate_price_evaluations',
                'bracket_expansions','bracket_refinements','monotonicity_fallback_count','search_wall_seconds'
            ]) AS f(name)
            WHERE x->>f.name IS NULL OR (x->>f.name)::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
        ) THEN RAISE EXCEPTION 'missing or non-finite numeric source/threshold evidence'; END IF;
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            CROSS JOIN unnest(ARRAY['current_quantity','threshold_quantity','current_budget_rank',
                                   'candidate_price_evaluations','bracket_expansions','bracket_refinements',
                                   'monotonicity_fallback_count']) AS f(name)
            WHERE (x->>f.name)::NUMERIC <> trunc((x->>f.name)::NUMERIC)
        ) THEN RAISE EXCEPTION 'non-integral count/rank/quantity'; END IF;
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
        ) THEN RAISE EXCEPTION 'invalid threshold money/allocation/direction arithmetic'; END IF;

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
             AND live.target_budget = v_live_snapshot.full_market_budget
            WHERE live.sealed_product_id IS NULL
               OR live.product_family IS DISTINCT FROM row->>'product_family'
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
             AND bench.target_budget = v_live_snapshot.full_market_budget
            WHERE bench.sealed_product_id IS NULL
               OR bench.sealed_product_id = (row->>'sealed_product_id')::UUID
               OR bench.budget_rank_v12 IS DISTINCT FROM CASE WHEN (row->>'current_budget_rank')::INTEGER = 1 THEN 2 ELSE 1 END
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
        -- Compare actual persisted content, not differently serialized Python/SQL
        -- digests. Array order and numeric spelling do not create false conflicts.
        -- Populate the real row type to normalize exactly as INSERT will; strip
        -- generated IDs. This also supports retrying the existing imported canary.
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

    ELSIF v_method_version = 'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' THEN
        -- =================================================================
        -- V2 BRANCH: new dual-threshold (RIP + Financial) validation body.
        -- Mirrors the V1 body's structure step-for-step, extended for the
        -- second (Financial-only) threshold search and its benchmark.
        -- =================================================================
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

        IF (p_snapshot->>'runtime_seconds')::NUMERIC IS NULL
           OR (p_snapshot->>'runtime_seconds')::NUMERIC < 0
           OR (p_snapshot->>'runtime_seconds')::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
           OR NULLIF(p_snapshot->>'source_full_market_row_fingerprint','') IS NULL THEN
            RAISE EXCEPTION 'invalid snapshot timing/source fingerprint';
        END IF;

        -- 1. Structural guards: 1:1 row identity, no duplicates, count
        -- matches resolved_count -- identical to V1.
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

        -- 2. Live-authority lookup and locking sequence -- identical to V1:
        -- the underlying Budget Ranking authority contract does not change
        -- between the V1 and V2 Best-Open methods.
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

        IF v_live_snapshot.ranked_under_v12_authority IS DISTINCT FROM TRUE
           OR v_live_snapshot.ranking_method_version IS DISTINCT FROM 'budget_product_ranking_v1'
           OR v_live_snapshot.allocation_method_version IS DISTINCT FROM 'budget_allocation_floor_quantity_v1'
           OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM 'budget_constrained_whole_unit_cross_format_v1'
           OR v_live_snapshot.financial_rip_version IS DISTINCT FROM 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
           OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
           OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM 'chase_accessibility_v1_hc_value_squared_modeled_probability'
           OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM 'chase_accessibility_overall_score_v1_saturating_k002'
           OR v_live_snapshot.overall_rip_version IS DISTINCT FROM
              'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
           OR v_live_snapshot.overall_rip_v12_version IS DISTINCT FROM v_live_snapshot.overall_rip_version
           OR v_live_snapshot.overall_rip_version IS DISTINCT FROM p_snapshot->>'overall_rip_v12_version'
           OR v_live_snapshot.id IS DISTINCT FROM (p_snapshot->>'source_budget_snapshot_id')::UUID
           OR v_live_snapshot.published_at IS DISTINCT FROM (p_snapshot->>'source_budget_published_at')::TIMESTAMPTZ
           OR v_live_snapshot.market_date IS DISTINCT FROM (p_snapshot->>'source_market_date')::DATE
           OR v_live_snapshot.cohort_fingerprint IS DISTINCT FROM p_snapshot->>'source_cohort_fingerprint'
           OR v_live_snapshot.eligible_cohort_count IS DISTINCT FROM (p_snapshot->>'source_eligible_cohort_count')::INTEGER
           OR v_live_snapshot.full_market_budget IS DISTINCT FROM (p_snapshot->>'source_full_market_budget')::NUMERIC
           OR v_live_snapshot.ranking_method_version IS DISTINCT FROM p_snapshot->>'ranking_method_version'
           OR v_live_snapshot.allocation_method_version IS DISTINCT FROM p_snapshot->>'allocation_method_version'
           OR v_live_snapshot.comparison_scope_version IS DISTINCT FROM p_snapshot->>'comparison_scope_version'
           OR v_live_snapshot.financial_rip_version IS DISTINCT FROM p_snapshot->>'financial_rip_version'
           OR v_live_snapshot.collector_appeal_version IS DISTINCT FROM p_snapshot->>'collector_appeal_version'
           OR v_live_snapshot.chase_accessibility_version IS DISTINCT FROM p_snapshot->>'chase_accessibility_version'
           OR v_live_snapshot.chase_accessibility_transform_version IS DISTINCT FROM p_snapshot->>'chase_accessibility_transform_version'
        THEN
            RAISE EXCEPTION 'best-open-price source binding no longer matches live V12 authority';
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

        -- 3/4. New: current_financial_only_rank must be present on every
        -- row and is cross-checked (with everything else V1 checks) against
        -- the live budget_product_ranking_rows.financial_only_rank for that
        -- (sealed_product_id, budget_type='full_market', target_budget).
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            WHERE x->>'current_financial_only_rank' IS NULL
        ) THEN
            RAISE EXCEPTION 'current_financial_only_rank is required on every Best-Open Price V2 row';
        END IF;

        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            CROSS JOIN unnest(ARRAY[
                'current_market_price','best_open_price','current_quantity','threshold_quantity',
                'current_budget_rank','current_financial_only_rank',
                'current_overall_rip_v12_score','current_financial_rip_v4_score',
                'current_collector_appeal_score','current_chase_accessibility_raw',
                'current_chance_to_recover_capital','current_actual_committed_capital',
                'benchmark_overall_rip_v12_score','benchmark_financial_rip_v4_score',
                'benchmark_chance_to_recover_capital','benchmark_actual_committed_capital',
                'price_gap_dollars','price_gap_percent','candidate_price_evaluations',
                'bracket_expansions','bracket_refinements','monotonicity_fallback_count','search_wall_seconds',
                'financial_best_open_price','financial_threshold_quantity',
                'financial_price_gap_dollars','financial_price_gap_percent',
                'financial_benchmark_financial_rip_v4_score',
                'threshold_financial_rip_v4_score','threshold_chance_to_recover_capital',
                'threshold_actual_committed_capital',
                'financial_threshold_financial_rip_v4_score','financial_threshold_chance_to_recover_capital',
                'financial_threshold_actual_committed_capital'
            ]) AS f(name)
            WHERE x->>f.name IS NULL OR (x->>f.name)::NUMERIC::TEXT IN ('NaN','Infinity','-Infinity')
        ) THEN RAISE EXCEPTION 'missing or non-finite numeric source/threshold evidence'; END IF;
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            CROSS JOIN unnest(ARRAY['current_quantity','threshold_quantity','current_budget_rank',
                                   'current_financial_only_rank',
                                   'candidate_price_evaluations','bracket_expansions','bracket_refinements',
                                   'monotonicity_fallback_count','financial_threshold_quantity']) AS f(name)
            WHERE (x->>f.name)::NUMERIC <> trunc((x->>f.name)::NUMERIC)
        ) THEN RAISE EXCEPTION 'non-integral count/rank/quantity'; END IF;
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
               -- New: Financial-only direction/status arithmetic, keyed off
               -- current_financial_only_rank rather than current_budget_rank.
               OR (x->>'financial_best_open_price')::NUMERIC <= 0
               OR (x->>'financial_best_open_price')::NUMERIC > v_live_snapshot.full_market_budget
               OR (x->>'financial_threshold_quantity')::NUMERIC IS DISTINCT FROM floor(v_live_snapshot.full_market_budget / NULLIF((x->>'financial_best_open_price')::NUMERIC, 0))
               OR (x->>'financial_price_gap_dollars')::NUMERIC IS DISTINCT FROM (x->>'current_market_price')::NUMERIC - (x->>'financial_best_open_price')::NUMERIC
               OR abs((x->>'financial_price_gap_percent')::NUMERIC - ((x->>'current_market_price')::NUMERIC - (x->>'financial_best_open_price')::NUMERIC) / NULLIF((x->>'current_market_price')::NUMERIC, 0)) > 0.000000000001
               OR ((x->>'current_financial_only_rank')::INTEGER = 1 AND (x->>'financial_best_open_price')::NUMERIC < (x->>'current_market_price')::NUMERIC)
               OR ((x->>'current_financial_only_rank')::INTEGER <> 1 AND (x->>'financial_best_open_price')::NUMERIC > (x->>'current_market_price')::NUMERIC)
               OR (x->>'financial_status' = 'current_number_one_with_headroom' AND (x->>'current_financial_only_rank')::INTEGER <> 1)
        ) THEN RAISE EXCEPTION 'invalid threshold money/allocation/direction arithmetic'; END IF;

        -- 4. Row cross-check (current side): everything V1 checks, PLUS
        -- financial_only_rank.
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
               OR live.budget_rank_v12 IS DISTINCT FROM (row->>'current_budget_rank')::INTEGER
               OR live.financial_only_rank IS DISTINCT FROM (row->>'current_financial_only_rank')::INTEGER
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

        -- 5. RIP benchmark cross-check: identical to V1's benchmark
        -- cross-check (benchmark_sealed_product_id / benchmark_overall_rip_v12_score /
        -- benchmark_financial_rip_v4_score continue to mean the RIP benchmark).
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
               OR bench.budget_rank_v12 IS DISTINCT FROM CASE WHEN (row->>'current_budget_rank')::INTEGER = 1 THEN 2 ELSE 1 END
               OR bench.overall_rip_v12_score IS DISTINCT FROM (row->>'benchmark_overall_rip_v12_score')::NUMERIC
               OR bench.financial_rip_v4_score IS DISTINCT FROM (row->>'benchmark_financial_rip_v4_score')::NUMERIC
               OR bench.chance_to_recover_capital IS DISTINCT FROM (row->>'benchmark_chance_to_recover_capital')::NUMERIC
               OR bench.actual_committed_capital IS DISTINCT FROM (row->>'benchmark_actual_committed_capital')::NUMERIC
        ) THEN
            RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live benchmark ranking row';
        END IF;

        -- 6. New: Financial benchmark cross-check, structurally identical
        -- to the RIP benchmark cross-check above but keyed on
        -- financial_benchmark_sealed_product_id, checked against the live
        -- benchmark row's financial_only_rank, and INDEPENDENT of the RIP
        -- no-self-benchmark check (the Financial benchmark is not required
        -- to differ from the RIP benchmark; they may legitimately be the
        -- same product) -- only self-benchmarking against the row's own
        -- sealed_product_id is forbidden.
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
               OR fbench.financial_only_rank IS DISTINCT FROM CASE WHEN (row->>'current_financial_only_rank')::INTEGER = 1 THEN 2 ELSE 1 END
               OR fbench.financial_rip_v4_score IS DISTINCT FROM (row->>'financial_benchmark_financial_rip_v4_score')::NUMERIC
               OR (
                    NULLIF(row->>'financial_benchmark_overall_rip_v12_score', '') IS NOT NULL
                    AND fbench.overall_rip_v12_score IS DISTINCT FROM (row->>'financial_benchmark_overall_rip_v12_score')::NUMERIC
               )
        ) THEN
            RAISE EXCEPTION 'one or more best-open-price rows do not reconcile against the live Financial benchmark ranking row';
        END IF;

        -- 7. New: dual threshold-evidence validation. Non-null and finite
        -- are already enforced by the finiteness check above; here we
        -- validate range and the economic-reconciliation tolerance (NOT
        -- exact equality -- Python's float operation order can leave an
        -- IEEE-754 tail) for BOTH the RIP set and the Financial set.
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS x
            WHERE (x->>'threshold_chance_to_recover_capital')::NUMERIC < 0
               OR (x->>'threshold_chance_to_recover_capital')::NUMERIC > 1
               OR (x->>'threshold_actual_committed_capital')::NUMERIC <= 0
               OR abs(
                    (x->>'threshold_actual_committed_capital')::NUMERIC
                    - (x->>'threshold_quantity')::NUMERIC * (x->>'best_open_price')::NUMERIC
                  ) > 0.01
               OR (x->>'financial_threshold_chance_to_recover_capital')::NUMERIC < 0
               OR (x->>'financial_threshold_chance_to_recover_capital')::NUMERIC > 1
               OR (x->>'financial_threshold_actual_committed_capital')::NUMERIC <= 0
               OR abs(
                    (x->>'financial_threshold_actual_committed_capital')::NUMERIC
                    - (x->>'financial_threshold_quantity')::NUMERIC * (x->>'financial_best_open_price')::NUMERIC
                  ) > 0.01
        ) THEN
            RAISE EXCEPTION 'invalid dual threshold-evidence range or economic reconciliation';
        END IF;

        -- 8. Cent-precision guards on financial_best_open_price, same
        -- round(...,2) idiom as V1's best_open_price, plus the existing
        -- current_market_price/best_open_price checks.
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_rows) AS row
            WHERE (row->>'current_market_price')::NUMERIC <> round((row->>'current_market_price')::NUMERIC, 2)
               OR (row->>'best_open_price')::NUMERIC <> round((row->>'best_open_price')::NUMERIC, 2)
               OR (row->>'financial_best_open_price')::NUMERIC <> round((row->>'financial_best_open_price')::NUMERIC, 2)
        ) THEN
            RAISE EXCEPTION 'a best-open-price money field is not exact-cent precision';
        END IF;

        -- 9. Cohort completeness -- identical to V1's.
        IF (v_row_count + (p_snapshot->>'unresolved_count')::INTEGER) <> v_live_snapshot.eligible_cohort_count THEN
            RAISE EXCEPTION 'resolved_count + unresolved_count does not equal the live eligible cohort count';
        END IF;

        -- 10. Idempotency fingerprint -- same jsonb_populate_recordset-based
        -- content-fingerprint pattern as V1's hardened version. This
        -- automatically covers ALL columns including the new V2 ones since
        -- it operates on the whole row type, scoped by
        -- (source_budget_snapshot_id, source_budget_published_at,
        -- best_open_price_method_version) exactly like V1 -- different
        -- best_open_price_method_version values never collide on this
        -- lookup key, so V1 and V2 snapshots for the same source identity
        -- coexist.
        SELECT jsonb_agg(to_jsonb(r) - 'id' - 'snapshot_id' ORDER BY r.sealed_product_id)
        INTO v_financial_incoming_content
        FROM jsonb_populate_recordset(NULL::public.budget_product_best_open_price_rows, p_rows) r;
        v_content_fingerprint := encode(extensions.digest(v_financial_incoming_content::TEXT, 'sha256'), 'hex');
        SELECT s.id INTO v_existing_id
        FROM public.budget_product_best_open_price_snapshots s
        WHERE s.source_budget_snapshot_id = v_live_snapshot.id
          AND s.source_budget_published_at = v_live_snapshot.published_at
          AND s.best_open_price_method_version = p_snapshot->>'best_open_price_method_version';
        IF v_existing_id IS NOT NULL THEN
            SELECT jsonb_agg(to_jsonb(r) - 'id' - 'snapshot_id' ORDER BY r.sealed_product_id)
            INTO v_stored_content
            FROM public.budget_product_best_open_price_rows r WHERE r.snapshot_id = v_existing_id;
            IF v_stored_content IS DISTINCT FROM v_financial_incoming_content THEN
                RAISE EXCEPTION 'non-deterministic content for identical source identity and method version';
            END IF;
            RETURN v_existing_id;
        END IF;

        -- 11. INSERT into snapshots/rows (same explicit-column-list INSERT
        -- idiom as V1, now including all V2 columns), post-insert count
        -- check, latest upsert (identical ON CONFLICT idiom, already scoped
        -- by method version so V1's and V2's latest rows coexist).
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
            monotonicity_fallback_count, search_wall_seconds,
            current_financial_only_rank,
            financial_status, financial_best_open_price, financial_threshold_quantity,
            financial_price_gap_dollars, financial_price_gap_percent,
            financial_benchmark_sealed_product_id, financial_benchmark_financial_rip_v4_score,
            financial_benchmark_overall_rip_v12_score,
            threshold_financial_rip_v4_score, threshold_overall_rip_v12_score,
            threshold_chance_to_recover_capital, threshold_actual_committed_capital,
            financial_threshold_financial_rip_v4_score, financial_threshold_overall_rip_v12_score,
            financial_threshold_chance_to_recover_capital, financial_threshold_actual_committed_capital
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
            (x->>'search_wall_seconds')::NUMERIC,
            (x->>'current_financial_only_rank')::INTEGER,
            x->>'financial_status', (x->>'financial_best_open_price')::NUMERIC, (x->>'financial_threshold_quantity')::INTEGER,
            (x->>'financial_price_gap_dollars')::NUMERIC, NULLIF(x->>'financial_price_gap_percent', '')::NUMERIC,
            (x->>'financial_benchmark_sealed_product_id')::UUID, (x->>'financial_benchmark_financial_rip_v4_score')::NUMERIC,
            NULLIF(x->>'financial_benchmark_overall_rip_v12_score', '')::NUMERIC,
            (x->>'threshold_financial_rip_v4_score')::NUMERIC, NULLIF(x->>'threshold_overall_rip_v12_score', '')::NUMERIC,
            (x->>'threshold_chance_to_recover_capital')::NUMERIC, (x->>'threshold_actual_committed_capital')::NUMERIC,
            (x->>'financial_threshold_financial_rip_v4_score')::NUMERIC, NULLIF(x->>'financial_threshold_overall_rip_v12_score', '')::NUMERIC,
            (x->>'financial_threshold_chance_to_recover_capital')::NUMERIC, (x->>'financial_threshold_actual_committed_capital')::NUMERIC
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

    ELSE
        RAISE EXCEPTION 'unsupported Best-Open Price method version';
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_budget_product_best_open_price_snapshot(JSONB, JSONB) TO service_role;

COMMIT;
