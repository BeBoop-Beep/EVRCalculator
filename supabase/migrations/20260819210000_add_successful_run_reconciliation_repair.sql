-- Keep observation completeness and successful-run reconciliation independent.
--
-- Full-batch publication continues to use pokemon_scrape_missing_sets(), which
-- is observation-based. This additive repair RPC only reopens failed jobs that
-- lack a qualifying successful exact-date TCGPlayer Pokemon price scrape.

CREATE OR REPLACE FUNCTION public.scrape_error_code_is_retryable(p_error_code TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(btrim(p_error_code), '') NOT IN (
        'invalid_set_key_filter',
        'set_not_found',
        'missing_canonical_key',
        'invalid_scrape_config',
        'catalog_only_not_daily_eligible',
        'external_variant_identity_conflict'
    );
$$;

CREATE OR REPLACE FUNCTION public.safe_scrape_metric_numeric(p_value TEXT)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_value IS NULL OR btrim(p_value) = '' THEN
        RETURN NULL;
    END IF;
    RETURN btrim(p_value)::numeric;
EXCEPTION
    WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN NULL;
END;
$$;

-- Re-state the current observation repair in this additive migration so every
-- existing failed-job reopen is protected by the same deterministic policy.
-- Fresh missing-set insertion semantics remain unchanged.
CREATE OR REPLACE FUNCTION public.requeue_missing_scrape_jobs_for_batch(
    p_batch_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_batch public.pokemon_scrape_batches%ROWTYPE;
    v_requeued INTEGER := 0;
    v_inserted INTEGER := 0;
    v_missing INTEGER := 0;
BEGIN
    SELECT * INTO v_batch FROM public.pokemon_scrape_batches WHERE id = p_batch_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN 0;
    END IF;

    CREATE TEMP TABLE _missing_sets ON COMMIT DROP AS
    SELECT m.set_id
    FROM public.pokemon_scrape_missing_sets(v_batch.market_date) m;

    GET DIAGNOSTICS v_missing = ROW_COUNT;

    WITH reopened AS (
        UPDATE public.scrape_jobs j
        SET status = 'pending',
            completed_at = NULL,
            worker_id = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            error_message = 'requeued_by_cohort_repair',
            error_code = NULL,
            next_attempt_at = now() + make_interval(secs => LEAST(60 * power(2, GREATEST(j.attempts, 0))::integer, 1800))
        FROM _missing_sets ms
        WHERE j.batch_id = p_batch_id
          AND j.set_id = ms.set_id
          AND j.status = 'failed'
          AND j.attempts < j.max_attempts
          AND public.scrape_error_code_is_retryable(j.error_code)
          AND NOT EXISTS (
              SELECT 1 FROM public.scrape_jobs a
              WHERE a.set_id = j.set_id AND a.status IN ('pending', 'running')
          )
        RETURNING j.id
    )
    SELECT COUNT(*) INTO v_requeued FROM reopened;

    WITH inserted AS (
        INSERT INTO public.scrape_jobs (
            set_id, status, attempts, max_attempts, priority,
            batch_id, market_date, next_attempt_at, created_at
        )
        SELECT
            c.set_id, 'pending', 0, 3, c.priority,
            p_batch_id, v_batch.market_date, now(), timezone('utc', now())
        FROM public.pokemon_scrape_ready_cohort() c
        JOIN _missing_sets ms ON ms.set_id = c.set_id
        WHERE NOT EXISTS (
            SELECT 1 FROM public.scrape_jobs j
            WHERE j.batch_id = p_batch_id AND j.set_id = c.set_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM public.scrape_jobs a
            WHERE a.set_id = c.set_id AND a.status IN ('pending', 'running')
        )
        ON CONFLICT (batch_id, set_id) WHERE batch_id IS NOT NULL DO NOTHING
        RETURNING id
    )
    SELECT COUNT(*) INTO v_inserted FROM inserted;

    UPDATE public.pokemon_scrape_batches
    SET missing_set_count = v_missing,
        queued_set_count = (SELECT COUNT(*) FROM public.scrape_jobs j WHERE j.batch_id = p_batch_id),
        updated_at = timezone('utc', now())
    WHERE id = p_batch_id;

    RETURN v_requeued + v_inserted;
END;
$$;

CREATE OR REPLACE FUNCTION public.requeue_unreconciled_retryable_scrape_jobs_for_batch(
    p_batch_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_batch public.pokemon_scrape_batches%ROWTYPE;
    v_requeued INTEGER := 0;
    v_deterministic_blocked INTEGER := 0;
BEGIN
    SELECT * INTO v_batch
    FROM public.pokemon_scrape_batches
    WHERE id = p_batch_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'unreconciledRunRequeued', 0,
            'deterministicBlocked', 0
        );
    END IF;

    -- A qualifying run is deliberately stricter than observation existence.
    -- queue_job_id gives exact set/job authority, while market_date and the
    -- diagnostic family fields prevent unrelated successes from reconciling it.
    SELECT COUNT(*)::integer INTO v_deterministic_blocked
    FROM public.scrape_jobs j
    WHERE j.batch_id = p_batch_id
      AND j.market_date = v_batch.market_date
      AND j.status = 'failed'
      AND NOT public.scrape_error_code_is_retryable(j.error_code)
      AND NOT EXISTS (
          SELECT 1
          FROM public.scrape_job_runs r
          WHERE r.queue_job_id = j.id
            AND r.market_date = j.market_date
            AND r.job_name = 'pokemon_set_scrape'
            AND r.source_system = 'tcgplayer'
            AND r.job_type = 'price_scrape'
            AND r.entity_type = 'set'
            AND r.status = 'success'
            AND COALESCE(r.items_succeeded, 0) >= 1
            AND COALESCE(r.items_failed, 0) = 0
            AND public.safe_scrape_metric_numeric(
                    r.metadata ->> 'sourceCoverageRatio') = 1.0
            AND public.safe_scrape_metric_numeric(
                    r.metadata ->> 'acceptedVariantGroups') > 0
            AND public.safe_scrape_metric_numeric(
                    r.metadata ->> 'positiveNmObservationCount')
                >= public.safe_scrape_metric_numeric(
                    r.metadata ->> 'acceptedVariantGroups')
      );

    WITH reopened AS (
        UPDATE public.scrape_jobs j
        SET status = 'pending',
            completed_at = NULL,
            worker_id = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            -- Keep error_code/error_message as durable prior-attempt diagnostics.
            next_attempt_at = now() + make_interval(
                secs => LEAST(60 * power(2, GREATEST(j.attempts, 0))::integer, 1800)
            )
        WHERE j.batch_id = p_batch_id
          AND j.market_date = v_batch.market_date
          AND j.status = 'failed'
          AND j.attempts < j.max_attempts
          AND public.scrape_error_code_is_retryable(j.error_code)
          AND NOT EXISTS (
              SELECT 1
              FROM public.scrape_jobs a
              WHERE a.set_id = j.set_id
                AND a.status IN ('pending', 'running')
          )
          AND NOT EXISTS (
              SELECT 1
              FROM public.scrape_job_runs r
              WHERE r.queue_job_id = j.id
                AND r.market_date = j.market_date
                AND r.job_name = 'pokemon_set_scrape'
                AND r.source_system = 'tcgplayer'
                AND r.job_type = 'price_scrape'
                AND r.entity_type = 'set'
                AND r.status = 'success'
                AND COALESCE(r.items_succeeded, 0) >= 1
                AND COALESCE(r.items_failed, 0) = 0
                AND public.safe_scrape_metric_numeric(
                        r.metadata ->> 'sourceCoverageRatio') = 1.0
                AND public.safe_scrape_metric_numeric(
                        r.metadata ->> 'acceptedVariantGroups') > 0
                AND public.safe_scrape_metric_numeric(
                        r.metadata ->> 'positiveNmObservationCount')
                    >= public.safe_scrape_metric_numeric(
                        r.metadata ->> 'acceptedVariantGroups')
          )
        RETURNING j.id
    )
    SELECT COUNT(*)::integer INTO v_requeued FROM reopened;

    RETURN jsonb_build_object(
        'unreconciledRunRequeued', v_requeued,
        'deterministicBlocked', v_deterministic_blocked
    );
END;
$$;

REVOKE ALL ON FUNCTION public.scrape_error_code_is_retryable(TEXT)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.safe_scrape_metric_numeric(TEXT)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(BIGINT)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.requeue_unreconciled_retryable_scrape_jobs_for_batch(BIGINT)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.scrape_error_code_is_retryable(TEXT)
TO service_role;
GRANT EXECUTE ON FUNCTION public.safe_scrape_metric_numeric(TEXT)
TO service_role;
GRANT EXECUTE ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(BIGINT)
TO service_role;
GRANT EXECUTE ON FUNCTION public.requeue_unreconciled_retryable_scrape_jobs_for_batch(BIGINT)
TO service_role;
