CREATE TABLE IF NOT EXISTS public.pokemon_set_onboarding_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tcg text NOT NULL DEFAULT 'pokemon' CHECK (tcg = 'pokemon'),
    source_system text NOT NULL,
    source_set_id text NOT NULL,
    source_set_name text NOT NULL,
    canonical_key text,
    pokemon_api_set_id text,
    era_folder text,
    status text NOT NULL DEFAULT 'detected'
        CHECK (status IN ('detected','running','waiting','manual_review',
                          'retry','completed','failed')),
    current_step text NOT NULL DEFAULT 'metadata_resolution',
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 8 CHECK (max_attempts > 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    worker_id text,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    source_branch text,
    source_pr_number integer,
    source_pr_url text,
    source_commit_sha text,
    pull_model_status text,
    latest_market_date date,
    last_error_code text,
    last_error_message text,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    detected_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (source_system, source_set_id)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_onboarding_claim
    ON public.pokemon_set_onboarding_jobs (next_attempt_at, created_at)
    WHERE status IN ('detected','retry');
CREATE INDEX IF NOT EXISTS idx_pokemon_set_onboarding_lease
    ON public.pokemon_set_onboarding_jobs (lease_expires_at)
    WHERE status = 'running';

ALTER TABLE public.pokemon_set_onboarding_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_set_onboarding_jobs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.pokemon_set_onboarding_jobs TO service_role;

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
       SET status = CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retry' END,
           next_attempt_at = CASE WHEN attempt_count >= max_attempts THEN next_attempt_at ELSE now() END,
           worker_id = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
           last_error_code = 'lease_expired',
           last_error_message = 'Worker lease expired before completion',
           updated_at = now(),
           completed_at = CASE WHEN attempt_count >= max_attempts THEN now() ELSE NULL END
     WHERE status = 'running' AND lease_expires_at < now();

    SELECT * INTO v_job
      FROM public.pokemon_set_onboarding_jobs
     WHERE (status IN ('detected','retry') OR (p_force_retry AND status IN ('waiting','manual_review','failed')))
       AND (p_job_id IS NULL OR id = p_job_id)
       AND (p_force_retry OR next_attempt_at <= now())
       AND attempt_count < max_attempts
     ORDER BY next_attempt_at, detected_at
     FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;

    UPDATE public.pokemon_set_onboarding_jobs
       SET status='running', worker_id=p_worker_id,
           attempt_count=attempt_count + CASE WHEN status IN ('detected','retry') THEN 1 ELSE 0 END,
           lease_expires_at=now() + make_interval(secs => greatest(60, p_lease_seconds)),
           updated_at=now()
     WHERE id=v_job.id RETURNING * INTO v_job;
    RETURN NEXT v_job;
END $$;

CREATE OR REPLACE FUNCTION public.heartbeat_pokemon_set_onboarding_job(
    p_job_id uuid, p_worker_id text, p_lease_seconds integer DEFAULT 1800
) RETURNS SETOF public.pokemon_set_onboarding_jobs
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE public.pokemon_set_onboarding_jobs
       SET heartbeat_at=now(),
           lease_expires_at=now() + make_interval(secs => greatest(60, p_lease_seconds)),
           updated_at=now()
     WHERE id=p_job_id AND status='running' AND worker_id=p_worker_id
     RETURNING *;
$$;

REVOKE ALL ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.heartbeat_pokemon_set_onboarding_job(uuid, text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_next_pokemon_set_onboarding_job(text, integer, uuid, boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_pokemon_set_onboarding_job(uuid, text, integer) TO service_role;
