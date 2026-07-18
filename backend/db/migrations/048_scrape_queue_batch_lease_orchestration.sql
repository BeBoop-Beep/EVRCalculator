-- Phase 2/4/5/6/7 — Crash-safe, lease-based, batch-aware orchestration RPCs for
-- the Pokémon daily scrape queue.
--
-- Functions created/replaced:
--   pokemon_scrape_ready_cohort()          — single derivation of the expected
--                                            scrape-ready cohort + deterministic
--                                            priority (Phase 7).
--   reconcile_stale_scrape_jobs()          — expire leases; requeue or terminally
--                                            fail crashed jobs (Phase 4).
--   create_daily_scrape_batch()            — explicit AZ-market-date batch
--                                            creation, reconcile-first (Phase 2/3).
--   claim_next_scrape_job()                — lease-aware, priority-ordered claim
--                                            (Phase 4/7). Backward compatible.
--   heartbeat_scrape_job()                 — extend a lease (Phase 4).
--   finalize_scrape_job()                  — one transaction finalizing queue row
--                                            + diagnostic run + batch counters
--                                            (Phase 5).
--   pokemon_scrape_missing_sets()          — cohort sets lacking a valid Near Mint
--                                            observation for a market date (Phase 6).
--   complete_scrape_batch_if_ready()       — promote a batch only when the cohort
--                                            is observation-complete (Phase 6).
--
-- Apply manually in the Supabase SQL editor.

BEGIN;

-- =============================================================================
-- 0. Expected cohort + deterministic priority (Phase 7)
-- =============================================================================
-- Priority is a single sortable integer: smaller dispatches earlier.
--   base 0    : "current/public/simulated" — set has public set-value history
--               in the last 45 market days.
--   base 1000 : "newest active" — released within the last 365 days.
--   base 2000 : remaining scrape-ready sets.
-- Within a tier, newer releases sort earlier via days-since-release.
-- This intentionally stops prioritizing the oldest releases first for the whole
-- queue, so current sets refresh early even if a late queue problem occurs.

CREATE OR REPLACE FUNCTION public.pokemon_scrape_ready_cohort()
RETURNS TABLE(set_id UUID, priority INTEGER)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH ready AS (
        SELECT
            s.id AS set_id,
            s.release_date,
            EXISTS (
                SELECT 1
                FROM public.pokemon_set_value_daily_history h
                WHERE h.set_id = s.id
                  AND h.snapshot_date >= (timezone('America/Phoenix', now())::date - 45)
            ) AS is_public
        FROM public.sets AS s
        WHERE COALESCE(s.ready_for_daily_scrape, FALSE) = TRUE
          AND COALESCE(s.has_card_details_url, FALSE) = TRUE
          AND s.card_details_url IS NOT NULL
    )
    SELECT
        r.set_id,
        (
            CASE
                WHEN r.is_public THEN 0
                WHEN r.release_date IS NOT NULL
                     AND r.release_date >= (timezone('America/Phoenix', now())::date - 365) THEN 1000
                ELSE 2000
            END
            + LEAST(
                GREATEST(
                    COALESCE((timezone('America/Phoenix', now())::date - r.release_date), 999),
                    0
                ),
                999
            )
        )::integer AS priority
    FROM ready r;
$$;

GRANT EXECUTE ON FUNCTION public.pokemon_scrape_ready_cohort() TO service_role;

-- =============================================================================
-- 1. Stale-lease reconciliation (Phase 4)
-- =============================================================================
-- Hard process termination (SIGKILL/OOM) cannot be caught in Python, so recovery
-- must be database-driven. Any running job whose lease has expired — or a legacy
-- running row with no lease that has been running too long — is reclaimed here.
-- A stale PRIOR-market-day job is always terminally failed so it can never block
-- or leak into the current batch.

CREATE OR REPLACE FUNCTION public.reconcile_stale_scrape_jobs(
    p_now TIMESTAMPTZ DEFAULT now(),
    p_current_market_date DATE DEFAULT (timezone('America/Phoenix', now()))::date,
    p_legacy_running_grace_seconds INTEGER DEFAULT 7200
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count INTEGER := 0;
BEGIN
    WITH expired AS (
        SELECT
            j.id,
            j.attempts,
            j.max_attempts,
            (j.market_date IS NULL OR j.market_date < p_current_market_date) AS is_prior_day,
            (j.attempts < j.max_attempts) AS attempts_remain
        FROM public.scrape_jobs j
        WHERE j.status = 'running'
          AND (
              (j.lease_expires_at IS NOT NULL AND j.lease_expires_at < p_now)
              OR (
                  j.lease_expires_at IS NULL
                  AND j.started_at IS NOT NULL
                  AND j.started_at < p_now - make_interval(secs => p_legacy_running_grace_seconds)
              )
          )
        FOR UPDATE SKIP LOCKED
    ),
    reconciled AS (
        UPDATE public.scrape_jobs j
        SET
            status = CASE
                WHEN e.is_prior_day OR NOT e.attempts_remain THEN 'failed'
                ELSE 'pending'
            END,
            completed_at = CASE
                WHEN e.is_prior_day OR NOT e.attempts_remain THEN p_now
                ELSE NULL
            END,
            worker_id = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            next_attempt_at = CASE
                WHEN e.is_prior_day OR NOT e.attempts_remain THEN NULL
                -- Bounded exponential backoff prevents immediate retry loops.
                ELSE p_now + make_interval(
                    secs => LEAST(60 * power(2, GREATEST(e.attempts, 0))::integer, 1800)
                )
            END,
            error_message = CASE
                WHEN e.is_prior_day THEN 'stale_prior_day_lease_expired'
                WHEN NOT e.attempts_remain THEN 'stale_lease_expired: max attempts exhausted'
                ELSE 'stale_lease_expired: worker_terminated, requeued'
            END
        FROM expired e
        WHERE j.id = e.id
        RETURNING j.id
    ),
    -- Close any diagnostic run still open for a reconciled job so queue and
    -- diagnostic statuses cannot silently diverge.
    closed_runs AS (
        UPDATE public.scrape_job_runs r
        SET
            status = 'failed',
            aborted = TRUE,
            completed_at = COALESCE(r.completed_at, p_now),
            error_summary = COALESCE(r.error_summary, 'worker_terminated: reconciled by lease watchdog')
        FROM reconciled rec
        WHERE r.queue_job_id = rec.id
          AND r.status IN ('running', 'pending')
        RETURNING r.id
    )
    SELECT COUNT(*) INTO v_count FROM reconciled;

    RETURN v_count;
END;
$$;

GRANT EXECUTE ON FUNCTION public.reconcile_stale_scrape_jobs(TIMESTAMPTZ, DATE, INTEGER) TO service_role;

-- =============================================================================
-- 2. Explicit daily batch creation (Phase 2/3)
-- =============================================================================
-- The worker must NOT implicitly create a new daily queue because the UTC date
-- changed. This is the explicit, scheduled batch operation keyed on an
-- America/Phoenix market date. Idempotent for the same market date.

CREATE OR REPLACE FUNCTION public.create_daily_scrape_batch(
    p_market_date DATE DEFAULT (timezone('America/Phoenix', now()))::date,
    p_timezone TEXT DEFAULT 'America/Phoenix',
    p_trigger_source TEXT DEFAULT 'scheduled'
)
RETURNS public.pokemon_scrape_batches
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_batch public.pokemon_scrape_batches%ROWTYPE;
    v_expected INTEGER := 0;
BEGIN
    -- 1. Reconcile stale/crashed jobs FIRST so their active-per-set slot is
    --    freed and cannot silently exclude a set from this batch.
    PERFORM public.reconcile_stale_scrape_jobs(now(), p_market_date);

    -- 2. Derive the expected cohort dynamically (never hardcoded).
    SELECT COUNT(*) INTO v_expected FROM public.pokemon_scrape_ready_cohort();

    -- 3. Upsert the batch manifest. A batch already marked complete is returned
    --    unchanged (idempotent, non-destructive).
    SELECT * INTO v_batch
    FROM public.pokemon_scrape_batches
    WHERE market_date = p_market_date;

    IF FOUND AND v_batch.status = 'complete' THEN
        RETURN v_batch;
    END IF;

    INSERT INTO public.pokemon_scrape_batches (
        market_date, timezone, status, trigger_source,
        expected_set_count, started_at, created_at, updated_at
    )
    VALUES (
        p_market_date, p_timezone, 'running', p_trigger_source,
        v_expected, now(), timezone('utc', now()), timezone('utc', now())
    )
    ON CONFLICT (market_date) DO UPDATE SET
        status = 'running',
        trigger_source = EXCLUDED.trigger_source,
        expected_set_count = EXCLUDED.expected_set_count,
        started_at = COALESCE(public.pokemon_scrape_batches.started_at, now()),
        updated_at = timezone('utc', now())
    RETURNING * INTO v_batch;

    -- 4. Insert one pending job per cohort set that has no active job. Reconcile
    --    already cleared stale actives, so a remaining active job is a genuine
    --    in-flight job for this set and is correctly skipped.
    --    ON CONFLICT (batch_id, set_id) makes re-runs idempotent.
    INSERT INTO public.scrape_jobs (
        set_id, status, attempts, max_attempts, priority,
        batch_id, market_date, next_attempt_at, created_at
    )
    SELECT
        c.set_id,
        'pending',
        0,
        3,
        c.priority,
        v_batch.id,
        p_market_date,
        now(),
        timezone('utc', now())
    FROM public.pokemon_scrape_ready_cohort() c
    WHERE NOT EXISTS (
        SELECT 1
        FROM public.scrape_jobs j
        WHERE j.set_id = c.set_id
          AND j.status IN ('pending', 'running')
    )
    ON CONFLICT (batch_id, set_id) WHERE batch_id IS NOT NULL DO NOTHING;

    -- 5. Record queued count (jobs actually associated with this batch).
    UPDATE public.pokemon_scrape_batches b
    SET queued_set_count = (
            SELECT COUNT(*) FROM public.scrape_jobs j WHERE j.batch_id = b.id
        ),
        updated_at = timezone('utc', now())
    WHERE b.id = v_batch.id
    RETURNING * INTO v_batch;

    RETURN v_batch;
END;
$$;

GRANT EXECUTE ON FUNCTION public.create_daily_scrape_batch(DATE, TEXT, TEXT) TO service_role;

-- =============================================================================
-- 3. Lease-aware, priority-ordered claim (Phase 4/7)
-- =============================================================================
-- Backward compatible: SELECT * FROM claim_next_scrape_job() still works.

DROP FUNCTION IF EXISTS public.claim_next_scrape_job();

CREATE OR REPLACE FUNCTION public.claim_next_scrape_job(
    p_worker_id TEXT DEFAULT NULL,
    p_lease_seconds INTEGER DEFAULT 1800
)
RETURNS SETOF public.scrape_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    claimed_row public.scrape_jobs%ROWTYPE;
BEGIN
    -- Reclaim expired leases before claiming so a crashed worker's job becomes
    -- available again instead of blocking the queue.
    PERFORM public.reconcile_stale_scrape_jobs(now());

    WITH next_job AS (
        SELECT id
        FROM public.scrape_jobs
        WHERE status = 'pending'
          AND (next_attempt_at IS NULL OR next_attempt_at <= now())
        ORDER BY priority ASC, created_at ASC, id ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE public.scrape_jobs AS jobs
    SET
        status = 'running',
        started_at = now(),
        completed_at = NULL,
        attempts = jobs.attempts + 1,
        worker_id = COALESCE(p_worker_id, jobs.worker_id),
        heartbeat_at = now(),
        lease_expires_at = now() + make_interval(secs => GREATEST(p_lease_seconds, 60)),
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
-- 4. Heartbeat (Phase 4)
-- =============================================================================

CREATE OR REPLACE FUNCTION public.heartbeat_scrape_job(
    p_job_id BIGINT,
    p_worker_id TEXT DEFAULT NULL,
    p_lease_seconds INTEGER DEFAULT 1800
)
RETURNS public.scrape_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_row public.scrape_jobs%ROWTYPE;
BEGIN
    UPDATE public.scrape_jobs
    SET heartbeat_at = now(),
        lease_expires_at = now() + make_interval(secs => GREATEST(p_lease_seconds, 60)),
        worker_id = COALESCE(p_worker_id, worker_id)
    WHERE id = p_job_id AND status = 'running'
    RETURNING * INTO v_row;

    RETURN v_row;  -- NULL row when the job was no longer running
END;
$$;

GRANT EXECUTE ON FUNCTION public.heartbeat_scrape_job(BIGINT, TEXT, INTEGER) TO service_role;

-- =============================================================================
-- 5. Durable transactional finalization (Phase 5)
-- =============================================================================
-- One transaction finalizes the queue row, the diagnostic run, and the batch
-- counters together so they cannot diverge. Idempotent: re-finalizing a job that
-- is already terminal is a safe no-op.

CREATE OR REPLACE FUNCTION public.finalize_scrape_job(
    p_job_id BIGINT,
    p_diag_run_id UUID DEFAULT NULL,
    p_final_status TEXT DEFAULT 'completed',
    p_completed_at TIMESTAMPTZ DEFAULT now(),
    p_succeeded INTEGER DEFAULT 0,
    p_failed INTEGER DEFAULT 0,
    p_metrics JSONB DEFAULT '{}'::jsonb,
    p_error_summary TEXT DEFAULT NULL,
    p_report_path TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job public.scrape_jobs%ROWTYPE;
    v_batch_id BIGINT;
    v_diag_status TEXT;
    v_updated INTEGER := 0;
BEGIN
    IF p_final_status NOT IN ('completed', 'failed') THEN
        RAISE EXCEPTION 'finalize_scrape_job: invalid final status %', p_final_status;
    END IF;

    SELECT * INTO v_job FROM public.scrape_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'job_not_found', 'job_id', p_job_id);
    END IF;

    -- Idempotency: only a running job transitions to terminal here.
    IF v_job.status IN ('completed', 'failed') THEN
        RETURN jsonb_build_object(
            'ok', true, 'idempotent', true, 'job_id', p_job_id, 'status', v_job.status
        );
    END IF;

    UPDATE public.scrape_jobs
    SET status = p_final_status,
        completed_at = p_completed_at,
        lease_expires_at = NULL,
        heartbeat_at = now(),
        error_message = CASE WHEN p_final_status = 'failed'
                             THEN LEFT(COALESCE(p_error_summary, 'failed'), 2000)
                             ELSE NULL END,
        diag_run_id = COALESCE(p_diag_run_id, diag_run_id)
    WHERE id = p_job_id AND status = 'running';
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    v_batch_id := v_job.batch_id;

    -- Diagnostic run finalization (same transaction).
    IF p_diag_run_id IS NOT NULL THEN
        v_diag_status := CASE
            WHEN p_final_status = 'completed' AND p_failed = 0 THEN 'success'
            WHEN p_final_status = 'completed' THEN 'partial_failure'
            ELSE 'failed'
        END;

        UPDATE public.scrape_job_runs
        SET status = v_diag_status,
            completed_at = p_completed_at,
            items_succeeded = p_succeeded,
            items_failed = p_failed,
            error_summary = COALESCE(p_error_summary, error_summary),
            report_path = COALESCE(p_report_path, report_path),
            queue_job_id = p_job_id,
            batch_id = COALESCE(v_batch_id, batch_id),
            market_date = COALESCE(v_job.market_date, market_date),
            metadata = COALESCE(metadata, '{}'::jsonb) || COALESCE(p_metrics, '{}'::jsonb)
        WHERE id = p_diag_run_id;
    END IF;

    -- Recompute batch counters from authoritative job rows (idempotent).
    IF v_batch_id IS NOT NULL THEN
        UPDATE public.pokemon_scrape_batches b
        SET succeeded_set_count = sub.succeeded,
            failed_set_count = sub.failed,
            updated_at = timezone('utc', now())
        FROM (
            SELECT
                COUNT(*) FILTER (WHERE status = 'completed') AS succeeded,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed
            FROM public.scrape_jobs
            WHERE batch_id = v_batch_id
        ) sub
        WHERE b.id = v_batch_id;
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'idempotent', false,
        'job_id', p_job_id,
        'status', p_final_status,
        'diag_run_id', p_diag_run_id,
        'batch_id', v_batch_id,
        'queue_rows_updated', v_updated
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.finalize_scrape_job(
    BIGINT, UUID, TEXT, TIMESTAMPTZ, INTEGER, INTEGER, JSONB, TEXT, TEXT
) TO service_role;

-- =============================================================================
-- 6. Cohort completeness vs observations (Phase 6)
-- =============================================================================
-- The authority for promotion is: does every expected cohort set have a valid
-- Near Mint observation captured on the target America/Phoenix market date?

CREATE OR REPLACE FUNCTION public.pokemon_scrape_missing_sets(
    p_market_date DATE DEFAULT (timezone('America/Phoenix', now()))::date
)
RETURNS TABLE(set_id UUID, canonical_key TEXT, name TEXT)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_nm_condition_id public.conditions.id%TYPE;
BEGIN
    SELECT id INTO v_nm_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    RETURN QUERY
    SELECT s.id, s.canonical_key, s.name
    FROM public.pokemon_scrape_ready_cohort() c
    JOIN public.sets s ON s.id = c.set_id
    WHERE v_nm_condition_id IS NULL
       OR NOT EXISTS (
           SELECT 1
           FROM public.cards cd
           JOIN public.card_variants cv ON cv.card_id = cd.id
           JOIN public.card_variant_price_observations o ON o.card_variant_id = cv.id
           WHERE cd.set_id = s.id
             AND o.condition_id = v_nm_condition_id
             AND o.market_price IS NOT NULL
             AND o.market_price > 0
             AND o.captured_at IS NOT NULL
             AND timezone('America/Phoenix', o.captured_at)::date = p_market_date
       );
END;
$$;

GRANT EXECUTE ON FUNCTION public.pokemon_scrape_missing_sets(DATE) TO service_role;

CREATE OR REPLACE FUNCTION public.complete_scrape_batch_if_ready(
    p_batch_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_batch public.pokemon_scrape_batches%ROWTYPE;
    v_missing INTEGER := 0;
    v_missing_ids UUID[];
    v_active INTEGER := 0;
    v_succeeded INTEGER := 0;
    v_failed INTEGER := 0;
    v_new_status TEXT;
BEGIN
    SELECT * INTO v_batch FROM public.pokemon_scrape_batches WHERE id = p_batch_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'batch_not_found', 'batch_id', p_batch_id);
    END IF;

    SELECT COUNT(*), COALESCE(array_agg(m.set_id), ARRAY[]::uuid[])
    INTO v_missing, v_missing_ids
    FROM public.pokemon_scrape_missing_sets(v_batch.market_date) m;

    SELECT
        COUNT(*) FILTER (WHERE status IN ('pending', 'running')),
        COUNT(*) FILTER (WHERE status = 'completed'),
        COUNT(*) FILTER (WHERE status = 'failed')
    INTO v_active, v_succeeded, v_failed
    FROM public.scrape_jobs
    WHERE batch_id = p_batch_id;

    IF v_missing = 0 THEN
        v_new_status := 'complete';
    ELSE
        v_new_status := 'incomplete';
    END IF;

    UPDATE public.pokemon_scrape_batches
    SET status = v_new_status,
        succeeded_set_count = v_succeeded,
        failed_set_count = v_failed,
        missing_set_count = v_missing,
        completed_at = CASE WHEN v_new_status = 'complete' THEN COALESCE(completed_at, now()) ELSE completed_at END,
        -- promoted_at is set ONLY when the cohort is observation-complete, so a
        -- partial batch never promotes downstream snapshots.
        promoted_at = CASE WHEN v_new_status = 'complete' THEN COALESCE(promoted_at, now()) ELSE promoted_at END,
        error_summary = CASE WHEN v_new_status = 'incomplete'
                             THEN v_missing || ' set(s) missing valid Near Mint observations for market_date'
                             ELSE NULL END,
        updated_at = timezone('utc', now())
    WHERE id = p_batch_id
    RETURNING * INTO v_batch;

    RETURN jsonb_build_object(
        'ok', true,
        'batch_id', p_batch_id,
        'market_date', v_batch.market_date,
        'status', v_new_status,
        'expected_set_count', v_batch.expected_set_count,
        'missing_set_count', v_missing,
        'active_set_count', v_active,
        'succeeded_set_count', v_succeeded,
        'failed_set_count', v_failed,
        'missing_set_ids', to_jsonb(v_missing_ids),
        'promoted', (v_new_status = 'complete')
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.complete_scrape_batch_if_ready(BIGINT) TO service_role;

COMMIT;
