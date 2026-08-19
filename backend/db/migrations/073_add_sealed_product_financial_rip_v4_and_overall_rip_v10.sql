-- 073: additively persist Financial RIP V4 and Overall RIP V10 on sealed-product
-- results.
--
-- WHY THIS EXISTS
-- ---------------
-- 064 created `simulation_sealed_product_results` with version-specific
-- Financial RIP V3 columns and generic Overall RIP columns that currently carry
-- the V9 identity. V4/V10 exist only in memory, so a V4 cutover would have no
-- durable sealed-product lineage to read back or audit.
--
-- STRICTLY ADDITIVE. No column is renamed, retyped, dropped or reinterpreted:
--   * financial_rip_v3_* keep their meaning and their data, forever;
--   * overall_rip_* keep carrying whatever version wrote them (V9 today), and
--     `overall_rip_version` continues to name that version explicitly;
--   * every new column is NULLABLE with no default, so existing rows are valid
--     unchanged and no table rewrite occurs.
--
-- V3 IS NOT OVERWRITTEN BY V4. The two models coexist as separate fields on the
-- SAME authoritative row. That is deliberate: the unique key
-- (calculation_run_id, sealed_product_id) is the identity of "this SKU in this
-- run", and encoding a model version by duplicating that row would make the key
-- mean something different than it has always meant, and would silently double
-- every downstream count.
--
-- LOCKS / RISK
-- ------------
-- ADD COLUMN ... NULL with no DEFAULT and no CHECK against existing data is a
-- catalogue-only change in PostgreSQL 11+: it takes a brief ACCESS EXCLUSIVE
-- lock and does NOT rewrite the table. The CHECK constraints below are declared
-- inline with the new columns, so they apply only to the new columns and are
-- trivially satisfied by the NULLs in existing rows.
--
-- ROLLBACK
-- --------
-- DROP COLUMN on the six new columns. No existing data depends on them, and no
-- reader requires them until the canonical constants are flipped to V4/V10.

BEGIN;

ALTER TABLE public.simulation_sealed_product_results
    -- Financial RIP V4: parity with the V3 persistence contract above it.
    ADD COLUMN IF NOT EXISTS financial_rip_v4_score NUMERIC
        CHECK (financial_rip_v4_score IS NULL OR financial_rip_v4_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS financial_rip_v4_status TEXT,
    ADD COLUMN IF NOT EXISTS financial_rip_v4_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS financial_rip_v4_version TEXT,
    -- NULLABLE, unlike financial_rip_v3_payload NOT NULL: existing rows predate
    -- V4 and must stay valid. The application is what guarantees a V4 row
    -- carries its payload, and it cannot be asserted here without a backfill.
    ADD COLUMN IF NOT EXISTS financial_rip_v4_payload JSONB,

    -- Overall RIP V10: explicit, version-named columns beside the generic
    -- overall_rip_* pair, so a V10 value can never be mistaken for the V9 value
    -- already stored, and both remain readable on the same row.
    ADD COLUMN IF NOT EXISTS overall_rip_v10_score NUMERIC
        CHECK (overall_rip_v10_score IS NULL OR overall_rip_v10_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS overall_rip_v10_version TEXT,
    ADD COLUMN IF NOT EXISTS overall_rip_v10_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v10_payload JSONB;

COMMENT ON COLUMN public.simulation_sealed_product_results.financial_rip_v4_version IS
    'Financial RIP V4 identity, expected financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5. Independent of financial_rip_v3_version, which is never overwritten.';
COMMENT ON COLUMN public.simulation_sealed_product_results.overall_rip_v10_version IS
    'Overall RIP V10 identity, expected overall_rip_v10_90_financial_v4_10_collector_appeal_v5 (0.90 * Financial RIP V4 + 0.10 * Collector Appeal V5). The generic overall_rip_version continues to name whichever version wrote overall_rip_score.';

COMMIT;
