-- Phase 7 — Lock down the scrape batch/orchestration surface created by
-- migrations 047-049.
--
-- Live permission audit found that the batch authority was reachable by the
-- public API roles:
--
--   * `anon` and `authenticated` held DELETE, INSERT, REFERENCES, SELECT,
--     TRIGGER, TRUNCATE, UPDATE on public.pokemon_scrape_batches.
--   * `anon` and `authenticated` held USAGE on
--     public.pokemon_scrape_batches_id_seq.
--   * `anon` and `authenticated` could EXECUTE all nine orchestration
--     functions, seven of which are SECURITY DEFINER and therefore run with
--     the privileges of their owner (postgres, which has BYPASSRLS).
--
-- That combination let an unauthenticated caller drive the daily scrape
-- lifecycle and, critically, forge the publication gate: pokemon_scrape_batches
-- is the sole authority the gate consults, so an anon UPDATE setting
-- status='complete' / promoted_at / missing_set_count=0 would open publication
-- for an incomplete cohort. The permissive RLS policy
-- `pokemon_scrape_batches_public_access` (USING true WITH CHECK true) provided
-- no protection at all.
--
-- Only the scraper/publisher service identity needs any of this surface.
--
-- Safe to drop the policy: `service_role` has rolbypassrls = true, and every
-- SECURITY DEFINER function is owned by `postgres` (also BYPASSRLS), so neither
-- the scheduled worker nor the RPCs depend on a policy being present. After
-- this migration the table is protected twice over for anon/authenticated:
-- no grants, and RLS enabled with no policy.
--
-- Scoped deliberately: privileges are revoked function-by-function using exact
-- signatures. No blanket "REVOKE ... ON ALL FUNCTIONS IN SCHEMA public" is used,
-- because that would strip execution from unrelated application RPCs.
--
-- Apply manually in the Supabase SQL editor (repo migrations are applied by
-- hand; the Supabase migration ledger is separate).

BEGIN;

-- =============================================================================
-- 1. Remove the permissive policy
-- =============================================================================

DROP POLICY IF EXISTS pokemon_scrape_batches_public_access
  ON public.pokemon_scrape_batches;

-- RLS stays ENABLED. With no policy, non-BYPASSRLS roles are denied outright.
ALTER TABLE public.pokemon_scrape_batches ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- 2. Table privileges
-- =============================================================================

REVOKE ALL ON TABLE public.pokemon_scrape_batches FROM PUBLIC;
REVOKE ALL ON TABLE public.pokemon_scrape_batches FROM anon;
REVOKE ALL ON TABLE public.pokemon_scrape_batches FROM authenticated;

-- service_role is reset too, because migration 047 left it holding the full
-- default set including TRUNCATE. TRUNCATE on the batch authority is the one
-- privilege worth removing outright: this table is the sole input to the
-- publication gate, so a compromised service key must not be able to erase it.
-- REFERENCES and TRIGGER are likewise unnecessary. Revoke+grant run inside this
-- migration's transaction, so service_role is never momentarily unprivileged.
REVOKE ALL ON TABLE public.pokemon_scrape_batches FROM service_role;

-- Only what the batch scripts actually perform against the table directly
-- (create/complete/repair read and update rows).
GRANT SELECT, INSERT, UPDATE, DELETE
  ON TABLE public.pokemon_scrape_batches TO service_role;

-- =============================================================================
-- 3. Sequence privileges
-- =============================================================================

REVOKE ALL ON SEQUENCE public.pokemon_scrape_batches_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.pokemon_scrape_batches_id_seq FROM anon;
REVOKE ALL ON SEQUENCE public.pokemon_scrape_batches_id_seq FROM authenticated;

GRANT USAGE, SELECT ON SEQUENCE public.pokemon_scrape_batches_id_seq TO service_role;

-- =============================================================================
-- 4. Function execution — exact signatures only
-- =============================================================================
-- REVOKE FROM PUBLIC is the one that matters: EXECUTE is granted to PUBLIC by
-- default at CREATE FUNCTION time, which is how anon/authenticated acquired it.
-- The explicit anon/authenticated revokes remove any direct grant as well.

REVOKE ALL ON FUNCTION public.pokemon_scrape_ready_cohort()
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reconcile_stale_scrape_jobs(timestamptz, date, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_daily_scrape_batch(date, text, text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_next_scrape_job(text, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.heartbeat_scrape_job(bigint, text, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finalize_scrape_job(
    bigint, uuid, text, timestamptz, integer, integer, jsonb, text, text
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.pokemon_scrape_missing_sets(date)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_scrape_batch_if_ready(bigint)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(bigint)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.pokemon_scrape_ready_cohort()
  TO service_role;
GRANT EXECUTE ON FUNCTION public.reconcile_stale_scrape_jobs(timestamptz, date, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.create_daily_scrape_batch(date, text, text)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_next_scrape_job(text, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_scrape_job(bigint, text, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.finalize_scrape_job(
    bigint, uuid, text, timestamptz, integer, integer, jsonb, text, text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.pokemon_scrape_missing_sets(date)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_scrape_batch_if_ready(bigint)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(bigint)
  TO service_role;

COMMIT;
