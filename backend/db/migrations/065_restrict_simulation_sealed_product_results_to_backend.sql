-- Migration 065: make `simulation_sealed_product_results` backend-private.
--
-- WHY
-- ---
-- Migration 064 created the Stage 1 product results table with a
-- `USING (true)` read policy and SELECT granted to `anon` and `authenticated`.
-- That mirrored the sealed-market SNAPSHOT tables, which are deliberately public
-- because a snapshot IS a published contract: a projected, versioned payload
-- built for consumption.
--
-- This table is not that. It is raw persistence: every scalar column plus the
-- COMPLETE Financial RIP V3 JSONB audit document, including normalization
-- records, breakpoints, clip status and the empirical tail-selection record.
-- Nothing consumes it publicly today - there is no frontend and no declared
-- Stage 1 public contract - so the blanket grant published an internal shape
-- before anyone decided it was the shape to publish. Once a raw column is
-- readable it is effectively part of the API, and every future column added to
-- this table would be published by default rather than by decision.
--
-- WHAT THIS CHANGES
-- -----------------
--   * the `USING (true)` read policy is DROPPED
--   * SELECT is REVOKED from `anon` and `authenticated`
--   * RLS stays ENABLED
--   * `service_role` keeps SELECT/INSERT/UPDATE/DELETE (it bypasses RLS and is
--     what the EVR runner and the audit script authenticate as)
--
-- NO DATA IS TOUCHED. This is a privilege change only, and it is idempotent.
--
-- WHAT THIS IS NOT
-- ----------------
-- Not a public product API. When Stage 1 product rankings are published they
-- should go through a deliberately PROJECTED surface - a view, an RPC, a
-- snapshot table or a service contract - that names the columns it publishes.
-- That surface is a separate decision and is not created here.
--
-- CORRECTION TO MIGRATION 064's REPRODUCIBILITY NOTE
-- --------------------------------------------------
-- 064's header says the composed 6-pack and 36-pack vectors are "reproducible
-- from the pack vector plus the recorded composition/model versions and the
-- deterministic seed contract". The conditional in that sentence is doing more
-- work than it looks like it is, and the honest statement is:
--
--   The Stage 1 seed makes Y reproducible GIVEN THE EXACT SOURCE X. The raw
--   million-outcome pack vector X is NOT persisted anywhere. Therefore a
--   historical product distribution CANNOT currently be reconstructed from
--   Postgres alone - only re-derived by re-running the pack simulation, which
--   is only bit-identical if every simulation input and the simulator itself
--   are unchanged.
--
-- 064 is left as applied rather than rewritten. This is expected until the
-- future outcome-artifact / custom-price stage, which is NOT implemented here.
--
-- SCOPE NOTE (deliberately NOT changed here)
-- ------------------------------------------
-- An access audit run against production with the anon key found that
-- `simulation_derived_metrics`, `calculation_runs` and
-- `simulation_value_threshold_bins` are ALSO directly anon-readable today. That
-- is a pre-existing, wider condition with existing consumers unknown to this
-- migration; changing it could break a live read path and is out of scope for a
-- Stage 1 hardening pass. It is reported rather than silently altered.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process.

BEGIN;

-- RLS stays on. Stated explicitly so re-running this file leaves the table in
-- the intended state even if something toggled it.
ALTER TABLE public.simulation_sealed_product_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS simulation_sealed_product_results_read_policy
    ON public.simulation_sealed_product_results;

REVOKE ALL ON public.simulation_sealed_product_results FROM anon;
REVOKE ALL ON public.simulation_sealed_product_results FROM authenticated;
REVOKE ALL ON public.simulation_sealed_product_results FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.simulation_sealed_product_results TO service_role;

COMMIT;
