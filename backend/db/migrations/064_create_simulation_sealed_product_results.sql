-- Migration 064: Stage 1 sealed-product RIP results.
--
-- WHAT THIS ADDS
-- --------------
-- One row per (calculation_run, sealed product SKU) for the three Stage 1
-- product families - sleeved booster pack (1 pack), booster bundle (6 packs)
-- and STANDARD booster box (36 packs). Each row records the sealed product's
-- own opening distribution statistics, the real sealed market price it was
-- scored against, its Financial RIP V3 result, the inherited set-level
-- Collector Appeal and the canonical Overall RIP.
--
-- WHY A SEPARATE TABLE
-- --------------------
-- `simulation_derived_metrics` is one row per calculation run and its columns
-- carry LOOSE-PACK semantics end to end (pack cost, per-pack score, pack
-- affordability). A sealed product is a different unit of analysis with its own
-- cost and its own outcome distribution, and a set can have several SKUs in the
-- same run. Writing product numbers into pack columns would silently change what
-- every existing pack reader means; a fake calculation_run per SKU would corrupt
-- run-level history the same way from the other direction. So: a narrow child
-- table hanging off the real parent run, and no existing column touched.
--
-- STORAGE SHAPE
-- -------------
-- Scalars for ranking/auditing plus the COMPLETE Financial RIP V3 JSONB payload,
-- exactly as migration 060 does for the pack path. The scalars are a projection
-- of the document, never a second source of truth, and the nested V3 audit
-- fields are deliberately NOT exploded into columns.
--
-- DISTRIBUTIONS ARE NOT STORED
-- ----------------------------
-- The composed 6-pack and 36-pack outcome vectors exist only for the duration of
-- the run. They are reproducible from the pack vector plus the recorded
-- composition/model versions and the deterministic seed contract, so persisting
-- millions of floats per SKU would buy nothing.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process.

BEGIN;

CREATE TABLE IF NOT EXISTS public.simulation_sealed_product_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calculation_run_id UUID NOT NULL
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    sealed_product_id UUID NOT NULL
        REFERENCES public.sealed_products(id) ON DELETE CASCADE,
    set_id UUID NOT NULL
        REFERENCES public.sets(id) ON DELETE CASCADE,

    -- Identity / modeling disclosure ----------------------------------------
    product_family TEXT NOT NULL,
    product_name TEXT,
    pack_count INTEGER NOT NULL CHECK (pack_count >= 1),
    composition_version TEXT NOT NULL,
    distribution_model_version TEXT NOT NULL,
    pack_independence_assumption BOOLEAN NOT NULL DEFAULT TRUE,

    -- Market provenance: the product's OWN price, never a pack price times a
    -- pack count and never MSRP. A row cannot exist without a valid one.
    product_market_cost NUMERIC NOT NULL CHECK (product_market_cost > 0),
    price_as_of DATE,
    price_source TEXT,

    -- Composed opening distribution -----------------------------------------
    simulation_count INTEGER NOT NULL CHECK (simulation_count > 0),
    expected_value NUMERIC,
    median_value NUMERIC,
    p05_value NUMERIC,
    p95_value NUMERIC,
    p99_value NUMERIC,
    min_value NUMERIC,
    max_value NUMERIC,
    standard_deviation NUMERIC,

    -- Economic outcome -------------------------------------------------------
    chance_to_recover_cost NUMERIC
        CHECK (chance_to_recover_cost IS NULL OR chance_to_recover_cost BETWEEN 0 AND 1),
    expected_loss_when_losing NUMERIC,
    median_loss_when_losing NUMERIC,
    total_value_to_cost_ratio NUMERIC,

    -- Financial RIP V3 -------------------------------------------------------
    financial_rip_v3_score NUMERIC
        CHECK (financial_rip_v3_score IS NULL OR financial_rip_v3_score BETWEEN 0 AND 100),
    financial_rip_v3_status TEXT,
    financial_rip_v3_rankable BOOLEAN,
    financial_rip_v3_version TEXT,
    financial_rip_v3_payload JSONB NOT NULL,

    -- Collector Appeal: inherited from the set, unchanged --------------------
    collector_appeal_score NUMERIC
        CHECK (collector_appeal_score IS NULL OR collector_appeal_score BETWEEN 0 AND 100),
    collector_appeal_version TEXT,

    -- Overall RIP ------------------------------------------------------------
    overall_rip_score NUMERIC
        CHECK (overall_rip_score IS NULL OR overall_rip_score BETWEEN 0 AND 100),
    overall_rip_version TEXT,
    overall_rip_rankable BOOLEAN,
    overall_rip_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    CONSTRAINT uq_simulation_sealed_product_results_run_product
        UNIQUE (calculation_run_id, sealed_product_id)
);

CREATE INDEX IF NOT EXISTS idx_simulation_sealed_product_results_run_id
    ON public.simulation_sealed_product_results (calculation_run_id);
CREATE INDEX IF NOT EXISTS idx_simulation_sealed_product_results_set_created
    ON public.simulation_sealed_product_results (set_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulation_sealed_product_results_set_family
    ON public.simulation_sealed_product_results (set_id, product_family, created_at DESC);

DROP TRIGGER IF EXISTS trg_simulation_sealed_product_results_updated_at
    ON public.simulation_sealed_product_results;
CREATE TRIGGER trg_simulation_sealed_product_results_updated_at
BEFORE UPDATE ON public.simulation_sealed_product_results
FOR EACH ROW EXECUTE FUNCTION public.sync_pokemon_public_snapshot_updated_at();

ALTER TABLE public.simulation_sealed_product_results ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public'
        AND tablename = 'simulation_sealed_product_results'
        AND policyname = 'simulation_sealed_product_results_read_policy'
    ) THEN
        CREATE POLICY simulation_sealed_product_results_read_policy
        ON public.simulation_sealed_product_results FOR SELECT USING (true);
    END IF;
END $$;

REVOKE ALL ON public.simulation_sealed_product_results FROM anon, authenticated;
GRANT SELECT ON public.simulation_sealed_product_results TO anon, authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON public.simulation_sealed_product_results TO service_role;

COMMIT;
