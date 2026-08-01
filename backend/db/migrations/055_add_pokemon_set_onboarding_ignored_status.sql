-- Adds a terminal, non-runnable 'ignored' status to pokemon_set_onboarding_jobs.
--
-- Purpose: the new-set discovery service had no first-run catalog baseline, so every
-- historical TCGplayer catalog product (Base Set, EX/XY era, promos, Trainer Kits,
-- gallery subsets, Jumbo Cards) that resolved to a stable setId absent from local
-- constants / public.sets / existing jobs was treated as a newly detected set.
-- A one-time `--baseline-current --commit` pass records those pre-existing provider
-- identities as status='ignored' so normal discovery treats them as known and only
-- reports provider identities that appear AFTER the baseline.
--
-- 'ignored' rows are never claimable by the onboarding worker.

ALTER TABLE public.pokemon_set_onboarding_jobs
    DROP CONSTRAINT IF EXISTS pokemon_set_onboarding_jobs_status_check;

ALTER TABLE public.pokemon_set_onboarding_jobs
    ADD CONSTRAINT pokemon_set_onboarding_jobs_status_check
    CHECK (status IN ('detected','ready','running','waiting','manual_review',
                      'retry','completed','failed','ignored'));

-- Keep the claim index narrow: baseline rows must never widen the runnable working set.
CREATE INDEX IF NOT EXISTS idx_pokemon_set_onboarding_source_status
    ON public.pokemon_set_onboarding_jobs (source_system, status);

-- Recreate the claim RPC with an explicit exclusion so no future eligibility change
-- (including p_force_retry and p_job_id targeting) can hand a baseline row to a worker.
CREATE OR REPLACE FUNCTION public.claim_next_pokemon_set_onboarding_job(
    p_worker_id text,
    p_lease_seconds integer DEFAULT 1800,
    p_job_id uuid DEFAULT NULL,
    p_force_retry boolean DEFAULT false
) RETURNS SETOF public.pokemon_set_onboarding_jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_job public.pokemon_set_onboarding_jobs;
BEGIN
    UPDATE public.pokemon_set_onboarding_jobs
       SET status = 'retry',
           next_attempt_at = now(),
           worker_id = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
           last_error_code = 'lease_expired',
           last_error_message = 'Worker lease expired before completion',
           updated_at = now(),
           completed_at = NULL
     WHERE status = 'running' AND lease_expires_at < now();

    UPDATE public.pokemon_set_onboarding_jobs
       SET status = 'failed', completed_at = now(), updated_at = now()
     WHERE status = 'retry' AND attempt_count >= max_attempts;

    SELECT * INTO v_job
      FROM public.pokemon_set_onboarding_jobs
     WHERE status <> 'ignored'
       AND (status IN ('detected','ready','retry') OR (p_force_retry AND status IN ('waiting','manual_review')))
       AND (p_job_id IS NULL OR id = p_job_id)
       AND (p_force_retry OR next_attempt_at <= now())
       AND (status <> 'retry' OR attempt_count < max_attempts)
     ORDER BY next_attempt_at, detected_at
     FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;

    UPDATE public.pokemon_set_onboarding_jobs
       SET status='running', worker_id=p_worker_id,
           attempt_count=attempt_count + CASE WHEN status = 'retry' THEN 1 ELSE 0 END,
           lease_expires_at=now() + make_interval(secs => greatest(60, p_lease_seconds)),
           updated_at=now()
     WHERE id=v_job.id RETURNING * INTO v_job;
    RETURN NEXT v_job;
END $$;

REVOKE ALL ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean) TO service_role;
