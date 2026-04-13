-- SQL setup for single-job Pokemon scrape dispatcher
--
-- This file contains:
-- 1. Table: public.scrape_jobs
-- 2. Indexes for cron-safe queue processing
-- 3. Atomic claim function: public.claim_next_scrape_job()
-- 4. Seed insert for Pokemon scrape-ready sets
--
-- Run in Supabase SQL editor or psql.

-- =============================================================================
-- 1. Create scrape_jobs table
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.scrape_jobs (
  id BIGSERIAL PRIMARY KEY,
  set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMP WITH TIME ZONE NULL,
  completed_at TIMESTAMP WITH TIME ZONE NULL,
  error_message TEXT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  CONSTRAINT scrape_jobs_status_check CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

ALTER TABLE public.scrape_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS scrape_jobs_public_access ON public.scrape_jobs;
CREATE POLICY scrape_jobs_public_access ON public.scrape_jobs
  FOR ALL USING (true) WITH CHECK (true);

-- =============================================================================
-- 2. Indexes for deterministic single-row dispatch
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status_created_id
  ON public.scrape_jobs(status, created_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_set_id
  ON public.scrape_jobs(set_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scrape_jobs_one_active_per_set
  ON public.scrape_jobs(set_id)
  WHERE status IN ('pending', 'running');

-- =============================================================================
-- 3. Atomic claim function
-- =============================================================================

CREATE OR REPLACE FUNCTION public.claim_next_scrape_job()
RETURNS SETOF public.scrape_jobs
LANGUAGE plpgsql
AS $$
DECLARE
  claimed_row public.scrape_jobs%ROWTYPE;
BEGIN
  WITH next_job AS (
    SELECT id
    FROM public.scrape_jobs
    WHERE status = 'pending'
    ORDER BY created_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE public.scrape_jobs AS jobs
  SET
    status = 'running',
    started_at = NOW(),
    completed_at = NULL,
    attempts = jobs.attempts + 1,
    error_message = NULL
  FROM next_job
  WHERE jobs.id = next_job.id
  RETURNING jobs.* INTO claimed_row;

  IF claimed_row.id IS NULL THEN
    RETURN;
  END IF;

  RETURN NEXT claimed_row;
END;
$$;

-- =============================================================================
-- 4. Seed pending jobs for Pokemon scrape-ready sets
-- =============================================================================
-- Safe to run repeatedly. Inserts one pending job per scrape-ready Pokemon set
-- only when that set does not already have a pending/running job.

INSERT INTO public.scrape_jobs (set_id, status)
SELECT s.id, 'pending'
FROM public.sets AS s
JOIN public.tcgs AS t
  ON t.id = s.tcg_id
WHERE t.name IN ('Pokemon', 'Pokémon')
  AND COALESCE(s.ready_for_daily_scrape, FALSE) = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM public.scrape_jobs AS jobs
    WHERE jobs.set_id = s.id
      AND jobs.status IN ('pending', 'running')
  )
ORDER BY s.release_date ASC NULLS LAST, s.name ASC;

-- =============================================================================
-- 5. Verification queries
-- =============================================================================

-- Inspect queue status counts:
-- SELECT status, COUNT(*)
-- FROM public.scrape_jobs
-- GROUP BY status
-- ORDER BY status;

-- Manually test claim function:
-- SELECT * FROM public.claim_next_scrape_job();

-- Review next pending jobs:
-- SELECT id, set_id, status, attempts, created_at
-- FROM public.scrape_jobs
-- ORDER BY created_at ASC, id ASC
-- LIMIT 20;
