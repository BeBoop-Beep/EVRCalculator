-- 20260902000000: additively persist Overall RIP V12 (shadow lineage) on
-- sealed-product results.
--
-- WHY THIS EXISTS
-- ---------------
-- `compute_overall_rip_v12` (backend/desirability/weighted_rip.py) implements
-- a THIRD Overall RIP lineage - 0.86 Financial RIP V4 + 0.04 Chase
-- Accessibility V1 (transformed via chase_accessibility_overall_score, k=0.002)
-- + 0.10 Collector Appeal V5 - per
-- docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md. It exists
-- only in memory today. This migration gives it a durable, additive home on
-- the SAME row migration 073 already used for V10, following that migration's
-- own pattern exactly.
--
-- STRICTLY ADDITIVE. No column is renamed, retyped, dropped or reinterpreted:
--   * overall_rip_v10_* (canonical today) keep their meaning and their data,
--     forever, and this migration does not touch them;
--   * overall_rip_v11_* (a separate historical Core-K lineage, non-canonical)
--     is untouched - this migration adds no V11 columns and does not exist
--     because V11 already has a persistence story elsewhere or does not need
--     one; that decision is out of scope here;
--   * every new column is NULLABLE with no default, so existing rows are valid
--     unchanged and no table rewrite occurs.
--
-- overall_rip_v12_status is added (unlike V10, which has no status column)
-- because V12's own compute function returns an explicit
-- "unavailable_missing_input" status distinct from "ready", and a THIRD
-- explicit "unavailable_authority_mismatch" status the finalizer assigns when
-- Chase Accessibility belongs to a different calculation_run_id than the
-- sealed-product row being enriched. Deriving status from score-is-null alone
-- would conflate "never computed" with "computed and explicitly refused",
-- which the research closure's NULL-vs-zero discipline requires be kept
-- distinct at read time, not just in memory.
--
-- NOT CANONICAL. CANONICAL_OVERALL_RIP_VERSION continues to resolve to V10.
-- Nothing reads or writes overall_rip_v12_* except the shadow finalization
-- path added alongside this migration; no ranking, snapshot ordering or
-- public default sort consumes it.
--
-- MANUAL APPLICATION
-- -------------------
-- Follows this repository's manually-applied convention. NOT applied to
-- production by any automated process. Nothing in this migration has been
-- applied by this change.

BEGIN;

ALTER TABLE public.simulation_sealed_product_results
    ADD COLUMN IF NOT EXISTS overall_rip_v12_score NUMERIC
        CHECK (overall_rip_v12_score IS NULL OR overall_rip_v12_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS overall_rip_v12_version TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v12_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v12_status TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v12_payload JSONB;

COMMENT ON COLUMN public.simulation_sealed_product_results.overall_rip_v12_version IS
    'Overall RIP V12 identity, expected overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5 (0.86 * Financial RIP V4 + 0.04 * Chase Accessibility V1 score + 0.10 * Collector Appeal V5). Shadow lineage only; CANONICAL_OVERALL_RIP_VERSION remains V10.';
COMMENT ON COLUMN public.simulation_sealed_product_results.overall_rip_v12_status IS
    'ready | unavailable_missing_input | unavailable_authority_mismatch. A NULL overall_rip_v12_score always carries a non-ready status here; the two are never allowed to diverge by the finalizer that writes them.';

COMMIT;
