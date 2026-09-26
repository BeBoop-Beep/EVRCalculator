-- Additively persist Financial RIP V5 (Shortfall Resilience) on sealed-product results.
--
-- V5 sits BESIDE V3/V4 on the same (calculation_run_id, sealed_product_id) row.
-- No column is renamed, retyped, dropped or reinterpreted; financial_rip_v4_* keep
-- their meaning and data. All new columns are NULLABLE with no default (catalogue-
-- only change, no table rewrite). Existing rows are NOT backfilled here: V5 must
-- be built from the exact outcome artifact, never projected from a V4 payload.
--
-- Overall RIP V14 deliberately gets NO dedicated sealed-row columns: it lives in
-- the generic Overall publication ledger (pokemon_overall_rip_publication_*), as
-- V13 did. Add columns only if an authoritative read path later requires them.
--
-- No grants/RLS change: only existing table columns are added.
--
-- ROLLBACK: DROP COLUMN the five columns; nothing reads them until the V5 cutover.

BEGIN;

ALTER TABLE public.simulation_sealed_product_results
    ADD COLUMN IF NOT EXISTS financial_rip_v5_score NUMERIC
        CHECK (financial_rip_v5_score IS NULL OR financial_rip_v5_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v5_status TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v5_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS financial_rip_v5_version TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v5_payload JSONB;

COMMENT ON COLUMN public.simulation_sealed_product_results.financial_rip_v5_version IS
    'Financial RIP V5 identity, expected financial_rip_v5_shortfall_resilience_25_20_15_25_10_5. Independent of financial_rip_v4_version, which is never overwritten. The payload carries the exact Shortfall Resilience sufficient statistics.';

COMMIT;
