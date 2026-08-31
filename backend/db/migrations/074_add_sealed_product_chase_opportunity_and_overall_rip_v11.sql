-- 074: additively persist Chase Opportunity V1 and Overall RIP V11 on
-- sealed-product results.
--
-- WHY THIS EXISTS
-- ---------------
-- 073 added version-named Financial RIP V4 and Overall RIP V10 columns. Overall
-- RIP V11 introduces a THIRD pillar - Chase Opportunity, 100K/(K+10) over the
-- Stage V-C Core chase count - which has no durable home anywhere in the schema.
-- Without these columns a V11 score could not be reconstructed, audited, or
-- proven to have been formed from the right pillar versions.
--
-- STRICTLY ADDITIVE. No column is renamed, retyped, dropped or reinterpreted:
--   * financial_rip_v3_* and financial_rip_v4_* keep their meaning and data;
--   * overall_rip_v10_* keep meaning EXACTLY 0.90 F_V4 + 0.10 C_V5, forever. A
--     V11 score is never written into a V10-named column, and V10 is never
--     aliased to V11;
--   * the generic overall_rip_* pair continues to name whichever version wrote
--     it, and will name V11 only once the canonical constant is flipped;
--   * every new column is NULLABLE with no default, so existing rows stay valid
--     unchanged, no table rewrite occurs, and the migration can be deployed
--     safely BEFORE any backfill.
--
-- WHAT THE SCHEMA MUST BE ABLE TO PROVE
-- -------------------------------------
--   * which Chase formula produced the score  -> chase_opportunity_version
--   * which K produced it                     -> chase_opportunity_core_k
--   * whether Chase was ready at all          -> chase_opportunity_status
--   * the Core floor and cost basis behind K  -> chase_opportunity_diagnostics
--   * which Financial fed V11                 -> overall_rip_v11_financial_rip_version
--   * which Collector fed V11                 -> overall_rip_v11_collector_appeal_version
--   * which Chase fed V11                     -> overall_rip_v11_chase_opportunity_version
--   * which Overall formula wrote the score   -> overall_rip_v11_version
--
-- MISSING IS NOT ZERO
-- -------------------
-- chase_opportunity_core_k is deliberately NULLABLE and carries no DEFAULT 0.
-- A validly evaluated Core basket that admitted no card is K = 0 with status
-- 'ready'; a product whose inputs were insufficient to evaluate the basket has
-- K NULL with an 'unavailable_*' status. A DEFAULT of 0 would erase that
-- distinction at the storage layer and let unmeasured products rank as measured
-- ones. The CHECK below enforces the pairing in both directions.
--
-- LOCKS / RISK
-- ------------
-- ADD COLUMN ... NULL with no DEFAULT is a catalogue-only change in PostgreSQL
-- 11+: brief ACCESS EXCLUSIVE lock, no table rewrite. The CHECK constraints are
-- declared inline with the new columns, so they apply only to those columns and
-- are trivially satisfied by the NULLs in existing rows.
--
-- ROLLBACK
-- --------
-- DROP COLUMN on the ten new columns. No existing data depends on them, and no
-- reader requires them until CANONICAL_OVERALL_RIP_VERSION is flipped to V11.

BEGIN;

ALTER TABLE public.simulation_sealed_product_results
    -- Chase Opportunity V1, the new third pillar.
    ADD COLUMN IF NOT EXISTS chase_opportunity_score NUMERIC
        CHECK (chase_opportunity_score IS NULL
               OR chase_opportunity_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS chase_opportunity_version TEXT,
    ADD COLUMN IF NOT EXISTS chase_opportunity_status TEXT,
    -- No DEFAULT. NULL means "not evaluated"; 0 means "evaluated, none
    -- qualified". These are different facts and must stay different.
    ADD COLUMN IF NOT EXISTS chase_opportunity_core_k INTEGER
        CHECK (chase_opportunity_core_k IS NULL OR chase_opportunity_core_k >= 0),
    -- Core floor, pack-equivalent cost, product market cost, random pack count,
    -- eligible price count and the tier contract string.
    ADD COLUMN IF NOT EXISTS chase_opportunity_diagnostics JSONB,

    -- Overall RIP V11: explicit, version-named columns beside the V10 pair, so
    -- a V11 value can never be mistaken for the V10 value on the same row.
    ADD COLUMN IF NOT EXISTS overall_rip_v11_score NUMERIC
        CHECK (overall_rip_v11_score IS NULL
               OR overall_rip_v11_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS overall_rip_v11_version TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v11_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v11_payload JSONB,
    -- The three pillar identities V11 was actually formed from. Recorded on the
    -- row rather than inferred from the canonical constants, because the
    -- canonical constants move and a historical row must stay reconstructible.
    ADD COLUMN IF NOT EXISTS overall_rip_v11_collector_appeal_version TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v11_chase_opportunity_version TEXT;

-- A score and its K must arrive together, in both directions. This is the
-- storage-level expression of "missing is not zero".
ALTER TABLE public.simulation_sealed_product_results
    DROP CONSTRAINT IF EXISTS simulation_sealed_product_results_chase_score_requires_core_k;
ALTER TABLE public.simulation_sealed_product_results
    ADD CONSTRAINT simulation_sealed_product_results_chase_score_requires_core_k
    CHECK (
        (chase_opportunity_score IS NULL AND chase_opportunity_core_k IS NULL)
        OR (chase_opportunity_score IS NOT NULL AND chase_opportunity_core_k IS NOT NULL)
    ) NOT VALID;

-- A V11 score may not exist without the Chase pillar that is part of it.
ALTER TABLE public.simulation_sealed_product_results
    DROP CONSTRAINT IF EXISTS simulation_sealed_product_results_v11_requires_chase;
ALTER TABLE public.simulation_sealed_product_results
    ADD CONSTRAINT simulation_sealed_product_results_v11_requires_chase
    CHECK (
        overall_rip_v11_score IS NULL OR chase_opportunity_score IS NOT NULL
    ) NOT VALID;

-- Ranking readers admit a row only when its stored version EQUALS the canonical
-- one, so the hot predicate is (version, rankable) with the score ordered.
CREATE INDEX IF NOT EXISTS simulation_sealed_product_results_overall_rip_v11_rank_idx
    ON public.simulation_sealed_product_results (
        overall_rip_v11_version, overall_rip_v11_rankable, overall_rip_v11_score DESC
    )
    WHERE overall_rip_v11_rankable;

COMMENT ON COLUMN public.simulation_sealed_product_results.chase_opportunity_version IS
    'Chase Opportunity identity, expected chase_opportunity_v1_core_k_saturating_100_k10 (100 * K / (K + 10), Core K only, NO CLAMP). The Stage VI research scale 200K/(K+10) is never written here.';
COMMENT ON COLUMN public.simulation_sealed_product_results.chase_opportunity_core_k IS
    'Stage V-C Core chase count: cards valued at or above 3x the product''s own pack-equivalent cost (product_market_cost / random_pack_count). NULL means the basket was not evaluated; 0 means it was evaluated and admitted no card. Extended K is not part of Overall RIP.';
COMMENT ON COLUMN public.simulation_sealed_product_results.overall_rip_v11_version IS
    'Overall RIP V11 identity, expected overall_rip_v11_83_financial_v4_11_collector_appeal_v5_06_chase_opportunity_v1 (0.83 * Financial RIP V4 + 0.11 * Collector Appeal V5 + 0.06 * Chase Opportunity V1). overall_rip_v10_* continue to mean 0.90/0.10 and are never overwritten.';

COMMIT;
