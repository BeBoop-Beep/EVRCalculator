-- Budget-Constrained Whole-Unit Product Ranking — INTERNAL storage only.
--
-- WHY THIS EXISTS
-- ---------------
-- The validated cross-format ranking capability (budget CEILING, whole
-- retail units) is NOT a public feature yet. It is precomputed here so
-- a future higher-tier "given my budget, what should I open" experience can
-- read cheaply, without exposing it through any current public payload.
--
-- METHOD (frozen V1): quantity = floor(target_budget / unit_price), whole
-- units only. Strategies at the same budget generally commit DIFFERENT
-- amounts of capital — this is a spending ceiling, NOT equal committed
-- capital. `unused_capital` is disclosure, never opening value, and is never
-- folded into any score.
--
-- Every record is explicitly budget-qualified: (sealed_product_id, budget)
-- together are the ranking identity, never a bare product rank. There is a
-- DIFFERENT comparison-scope identity for this table
-- (`comparison_scope_version = 'budget_constrained_whole_unit_cross_format_v1'`)
-- than natural-unit RIP's `within_product_family_only` — the two must never
-- be conflated, and neither this migration nor its RPC touches the
-- natural-unit comparison-scope contract in any way.
--
-- INTERNAL ONLY. `anon`/`authenticated` receive NO grants on any object this
-- migration creates. Only `service_role` may read or write. This is a
-- deliberate mirror of every other internal-analytics table's access
-- pattern, and the opposite of the public `..._latest` tables that grant
-- `SELECT` to `anon, authenticated` (e.g. `pokemon_rip_stats_snapshot_latest`).

BEGIN;

CREATE TABLE public.budget_product_ranking_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_date DATE NOT NULL,
    built_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('published')),
    ranking_method_version TEXT NOT NULL,
    allocation_method_version TEXT NOT NULL,
    comparison_scope_version TEXT NOT NULL,
    financial_rip_version TEXT NOT NULL,
    overall_rip_version TEXT NOT NULL,
    collector_appeal_version TEXT NOT NULL,
    eligible_cohort_count INTEGER NOT NULL CHECK (eligible_cohort_count > 0),
    cohort_fingerprint TEXT NOT NULL,

    -- AUTHORITY. One publication traces to exactly ONE coherent market state.
    -- Production can hold several complete cohorts at once (it held two
    -- 137-SKU cohorts during V1 validation), so the resolved price authority
    -- is persisted rather than inferred. Every row's `price_as_of` must equal
    -- this value; the RPC enforces it.
    pinned_price_as_of DATE NOT NULL,

    -- FULL MARKET publication metadata: the anchor is dynamic (next $50 above
    -- the max eligible SKU price), so its derivation is stored per publication
    -- to keep a historical anchor auditable if the increment ever changes.
    full_market_budget NUMERIC NOT NULL CHECK (full_market_budget > 0),
    max_eligible_sku_price NUMERIC NOT NULL CHECK (max_eligible_sku_price > 0),
    full_market_rounding_increment NUMERIC NOT NULL CHECK (full_market_rounding_increment > 0),
    full_market_rounding_rule_version TEXT NOT NULL,
    CHECK (full_market_budget >= max_eligible_sku_price),
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(diagnostics_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    -- One coherent publication per (market_date, method) triple. A second
    -- publish on the same date under the same method REPLACES it (see the
    -- RPC's ON CONFLICT), rather than silently coexisting as ambiguous
    -- authority.
    UNIQUE (market_date, ranking_method_version, allocation_method_version)
);

CREATE TABLE public.budget_product_ranking_rows (
    snapshot_id UUID NOT NULL REFERENCES public.budget_product_ranking_snapshots(id) ON DELETE CASCADE,
    sealed_product_id UUID NOT NULL,
    set_id UUID NOT NULL,
    product_family TEXT NOT NULL,

    -- Budget identity: target_budget + budget_type together with
    -- sealed_product_id are what make one row unique within a snapshot.
    target_budget NUMERIC NOT NULL CHECK (target_budget > 0),
    budget_type TEXT NOT NULL CHECK (budget_type IN ('standard_band', 'full_market', 'custom')),

    quantity INTEGER NOT NULL CHECK (quantity >= 1),
    actual_committed_capital NUMERIC NOT NULL CHECK (actual_committed_capital > 0),
    unused_capital NUMERIC NOT NULL CHECK (unused_capital >= 0),
    unused_capital_percent NUMERIC NOT NULL CHECK (unused_capital_percent >= 0 AND unused_capital_percent < 1),
    -- Exact complement of unused_capital_percent. Persisted because it is the
    -- diagnostic the methodology validation correlates against rank to prove
    -- the absence of budget-divisibility bias (Spearman -0.073 at freeze).
    capital_utilization NUMERIC NOT NULL CHECK (capital_utilization > 0 AND capital_utilization <= 1),
    CHECK (abs((capital_utilization + unused_capital_percent) - 1) < 0.000001),
    CHECK (abs((actual_committed_capital + unused_capital) - target_budget) < 0.01),

    -- PRIMARY rank: Overall RIP V10 (0.90 financial + 0.10 collector appeal).
    budget_rank INTEGER NOT NULL CHECK (budget_rank >= 1),
    budget_cohort_size INTEGER NOT NULL CHECK (budget_cohort_size >= budget_rank),
    -- SCORE tier (from the Overall RIP V10 score via the shared composite
    -- thresholds), NOT a rank percentile. Rank #1 does not imply tier S.
    budget_tier TEXT NOT NULL CHECK (budget_tier IN ('S', 'A', 'B', 'C', 'D', 'F')),

    -- INTERNAL AUDIT LENS, never surfaced publicly: the same cohort ordered by
    -- Financial RIP V4 alone. Dominance diagnostics are financial, and V10
    -- legitimately lets a financially dominated SKU win on collector appeal,
    -- so the clean allocation diagnostic needs appeal removed.
    financial_only_rank INTEGER NOT NULL CHECK (financial_only_rank >= 1),
    CHECK (financial_only_rank <= budget_cohort_size),

    financial_rip_v4_score NUMERIC,
    overall_rip_v10_score NUMERIC,
    collector_appeal_score NUMERIC,
    -- Canonical true-win probability for the ACTUAL multi-unit strategy
    -- distribution. Read from the V3 payload (the V4 projection carries an
    -- empty audit block), so it is populated rather than silently null.
    chance_to_recover_capital NUMERIC CHECK (chance_to_recover_capital IS NULL OR (chance_to_recover_capital >= 0 AND chance_to_recover_capital <= 1)),

    product_market_price NUMERIC NOT NULL CHECK (product_market_price > 0),
    price_as_of DATE,

    -- Full Market provenance. NULL for standard/custom budgets; populated
    -- only when budget_type = 'full_market', so the anchor's derivation is
    -- auditable per row without a join.
    full_market_anchor NUMERIC,
    max_eligible_sku_price NUMERIC,
    full_market_rounding_rule TEXT,
    full_market_rounding_increment NUMERIC,
    full_market_rounding_rule_version TEXT,

    source_calculation_run_id UUID NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    PRIMARY KEY (snapshot_id, sealed_product_id, target_budget, budget_type),
    CHECK (
        (budget_type = 'full_market' AND full_market_anchor IS NOT NULL AND max_eligible_sku_price IS NOT NULL
            AND full_market_rounding_rule IS NOT NULL AND full_market_rounding_increment IS NOT NULL
            AND full_market_rounding_rule_version IS NOT NULL)
        OR
        (budget_type <> 'full_market' AND full_market_anchor IS NULL AND max_eligible_sku_price IS NULL
            AND full_market_rounding_rule IS NULL AND full_market_rounding_increment IS NULL
            AND full_market_rounding_rule_version IS NULL)
    )
);
CREATE INDEX budget_product_ranking_rows_snapshot_idx ON public.budget_product_ranking_rows (snapshot_id);
CREATE INDEX budget_product_ranking_rows_product_idx ON public.budget_product_ranking_rows (sealed_product_id);

-- Latest, per (ranking_method_version, allocation_method_version): the
-- cheap read path once this ships to an internal/premium reader. Still
-- internal-only (see grants below) — this is precomputation for a future
-- surface, not a soft-launch of one today.
CREATE TABLE public.budget_product_ranking_latest (
    ranking_method_version TEXT NOT NULL,
    allocation_method_version TEXT NOT NULL,
    snapshot_id UUID NOT NULL REFERENCES public.budget_product_ranking_snapshots(id),
    market_date DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (ranking_method_version, allocation_method_version)
);

ALTER TABLE public.budget_product_ranking_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_product_ranking_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_product_ranking_latest ENABLE ROW LEVEL SECURITY;

-- INTERNAL ONLY: no grant to anon or authenticated on ANY object below.
REVOKE ALL ON public.budget_product_ranking_snapshots, public.budget_product_ranking_rows, public.budget_product_ranking_latest
    FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.budget_product_ranking_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.budget_product_ranking_rows TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.budget_product_ranking_latest TO service_role;

CREATE FUNCTION public.publish_budget_product_ranking_snapshot(p_snapshot JSONB, p_rows JSONB)
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
