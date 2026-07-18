-- Phase 3/4 — Batch/manifest authority + crash-safe lease columns for the
-- Pokémon daily scrape queue.
--
-- Root cause this addresses (July 17 incident): a stale prior-day `running`
-- scrape_jobs row satisfied the partial unique index
-- idx_scrape_jobs_one_active_per_set, so the daily enqueue's
-- `ON CONFLICT ... DO NOTHING` silently excluded that set from the next batch.
--
-- This migration is additive and backward compatible. New columns are nullable
-- or defaulted so existing rows and the current worker keep functioning while
-- the new batch/lease orchestration is rolled out.
--
-- Apply manually in the Supabase SQL editor (repo migrations are applied by
-- hand; the Supabase migration ledger is separate).

BEGIN;

-- =============================================================================
-- 1. Daily batch/manifest authority
-- =============================================================================
-- One row per (market_date). The batch is the single source of truth for
-- "was the daily cohort completed before downstream promotion?". Completion is
-- derived from the batch, not inferred from loose queue rows.

CREATE TABLE IF NOT EXISTS public.pokemon_scrape_batches (
  id BIGSERIAL PRIMARY KEY,
  market_date DATE NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'America/Phoenix',
  status TEXT NOT NULL DEFAULT 'pending',
  trigger_source TEXT NOT NULL DEFAULT 'scheduled',
  expected_set_count INTEGER NOT NULL DEFAULT 0,
  queued_set_count INTEGER NOT NULL DEFAULT 0,
  succeeded_set_count INTEGER NOT NULL DEFAULT 0,
  failed_set_count INTEGER NOT NULL DEFAULT 0,
  missing_set_count INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NULL,
  completed_at TIMESTAMPTZ NULL,
  promoted_at TIMESTAMPTZ NULL,
  error_summary TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT pokemon_scrape_batches_status_check
    CHECK (status IN ('pending', 'running', 'incomplete', 'complete', 'failed'))
);

-- One batch per market day (idempotent creation).
CREATE UNIQUE INDEX IF NOT EXISTS uq_pokemon_scrape_batches_market_date
  ON public.pokemon_scrape_batches(market_date);

ALTER TABLE public.pokemon_scrape_batches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pokemon_scrape_batches_public_access ON public.pokemon_scrape_batches;
CREATE POLICY pokemon_scrape_batches_public_access ON public.pokemon_scrape_batches
  FOR ALL USING (true) WITH CHECK (true);

-- =============================================================================
-- 2. scrape_jobs — batch association, market day, leases, retry policy
-- =============================================================================

ALTER TABLE public.scrape_jobs
  ADD COLUMN IF NOT EXISTS batch_id BIGINT NULL
    REFERENCES public.pokemon_scrape_batches(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS market_date DATE NULL,
  ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
  ADD COLUMN IF NOT EXISTS worker_id TEXT NULL,
  ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS trigger_source TEXT NULL,
  ADD COLUMN IF NOT EXISTS diag_run_id UUID NULL;

-- Idempotent uniqueness: one job per set per batch (safe re-enqueue).
-- Partial so legacy rows with NULL batch_id are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS uq_scrape_jobs_batch_set
  ON public.scrape_jobs(batch_id, set_id)
  WHERE batch_id IS NOT NULL;

-- Deterministic priority dispatch: lowest priority number first, then market
-- day, then insertion order.
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_dispatch_priority
  ON public.scrape_jobs(status, priority ASC, market_date ASC, created_at ASC, id ASC);

-- Fast lease-expiry reconciliation scan.
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_running_lease
  ON public.scrape_jobs(lease_expires_at)
  WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_market_date
  ON public.scrape_jobs(market_date);

-- =============================================================================
-- 3. Diagnostics linkage — associate scrape_job_runs with the queue job
-- =============================================================================
-- Replaces reliance on metadata set-filter matching. queue_job_id is the
-- durable association used by the transactional finalizer.

ALTER TABLE public.scrape_job_runs
  ADD COLUMN IF NOT EXISTS queue_job_id BIGINT NULL,
  ADD COLUMN IF NOT EXISTS market_date DATE NULL,
  ADD COLUMN IF NOT EXISTS batch_id BIGINT NULL;

CREATE INDEX IF NOT EXISTS idx_scrape_job_runs_queue_job_id
  ON public.scrape_job_runs(queue_job_id);

COMMIT;
