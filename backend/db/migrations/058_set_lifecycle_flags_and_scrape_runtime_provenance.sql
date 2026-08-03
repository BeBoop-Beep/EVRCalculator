-- Migration 058 — Model the scrape lifecycle explicitly, record runtime
-- provenance on each batch, and stop retrying deterministic configuration
-- failures.
--
-- Incident context (2026-08-03): the scraper VM ran a commit 19 revisions behind
-- main that predated 37 `otherEra` config files. Database metadata had already
-- been synchronized from a newer generation, so 34 database cohort rows named
-- canonical keys the deployed runtime could not resolve. Every one of those jobs
-- failed with `invalid_set_key_filter`, was retried three times, and held the
-- batch `incomplete` — which correctly (fail-closed) kept August 2 public.
--
-- Two independent defects are corrected here:
--   1. Cohort design — CATALOG_ONLY sets (promo/trainer-kit/product catalogs that
--      exist for onboarding and historical backfill) were entering the
--      publication-critical daily cohort purely because they carry a URL. They
--      must remain in the database and remain usable for manual/onboarding and
--      historical catalog backfills, but must never gate public publication.
--   2. Retry policy — a deterministic configuration/deployment mismatch is not a
--      transient fault and must not consume three identical attempts.
--
-- The `catalog_only` / `supports_opening_simulation` backfill arrays below are
-- GENERATED from the real SET_CONFIG_MAP classes by
-- `backend/scripts/generate_set_lifecycle_flag_backfill.py`, and
-- `backend/tests/unit/db/test_set_lifecycle_flag_backfill.py` fails if the
-- committed lists drift from the configs.
--
-- Apply manually in the Supabase SQL editor.

BEGIN;

-- =============================================================================
-- 1. Lifecycle columns on public.sets
-- =============================================================================
-- `ready_for_daily_scrape` is intentionally PRESERVED as the operational
-- daily-cohort flag. It becomes a derived value rather than an independent one.

ALTER TABLE public.sets
    ADD COLUMN IF NOT EXISTS catalog_only BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.sets
    ADD COLUMN IF NOT EXISTS supports_opening_simulation BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN public.sets.catalog_only IS
    'Set exists for catalog/onboarding/historical backfill only. Never enters the '
    'publication-critical daily scrape cohort and never blocks public promotion.';

COMMENT ON COLUMN public.sets.supports_opening_simulation IS
    'Set has a simulatable sealed product configuration. Authoritative "unsupported" '
    'reason for opening-simulation eligibility; avoids a second manual operator list.';

-- =============================================================================
-- 2. Backfill lifecycle flags (generated from SET_CONFIG_MAP)
-- =============================================================================

DO $backfill$
DECLARE
    -- Generated: catalog-only canonical keys (37).
    v_catalog_only_keys TEXT[] := ARRAY[
        'alternateArtPromos',
        'baseSetShadowless',
        'battleAcademy',
        'battleAcademy2022',
        'battleAcademy2024',
        'bestOfPromos',
        'blisterExclusives',
        'bwTrainerKitExcadrillAndZoroark',
        'countdownCalendarPromos',
        'deckExclusives',
        'diamondAndPearlPromos',
        'dpTrainerKitManaphyAndLucario',
        'eReaderSampleCards',
        'expedition',
        'firstPartnerCollection2026',
        'firstPartnerPack',
        'generationsRadiantCollection',
        'hgssTrainerKitGyaradosAndRaichu',
        'legendaryTreasuresRadiantCollection',
        'mcdonaldSPromos2023',
        'me30thCelebration',
        'pikachuWorldCollectionPromos',
        'professorProgramPromos',
        'smTrainerKitAlolanSandslashAndAlolanNinetales',
        'smTrainerKitLycanrocAndAlolanRaichu',
        'svScarletAndVioletPromoCards',
        'sveScarletAndVioletEnergies',
        'swshSwordAndShieldPromoCards',
        'tradingCardGameClassic',
        'trickOrTradeBOOsterBundle2023',
        'trickOrTradeBOOsterBundle2024',
        'worldChampionshipDecks',
        'wotcPromo',
        'xyTrainerKitBisharpAndWigglytuff',
        'xyTrainerKitLatiasAndLatios',
        'xyTrainerKitPikachuLibreAndSuicune',
        'xyTrainerKitSylveonAndNoivern'
    ]::text[];

    -- Generated: canonical keys that do NOT support opening simulation (37).
    v_no_simulation_keys TEXT[] := ARRAY[
        'alternateArtPromos',
        'baseSetShadowless',
        'battleAcademy',
        'battleAcademy2022',
        'battleAcademy2024',
        'bestOfPromos',
        'blisterExclusives',
        'bwTrainerKitExcadrillAndZoroark',
        'countdownCalendarPromos',
        'deckExclusives',
        'diamondAndPearlPromos',
        'dpTrainerKitManaphyAndLucario',
        'eReaderSampleCards',
        'expedition',
        'firstPartnerCollection2026',
        'firstPartnerPack',
        'generationsRadiantCollection',
        'hgssTrainerKitGyaradosAndRaichu',
        'legendaryTreasuresRadiantCollection',
        'mcdonaldSPromos2023',
        'me30thCelebration',
        'pikachuWorldCollectionPromos',
        'professorProgramPromos',
        'smTrainerKitAlolanSandslashAndAlolanNinetales',
        'smTrainerKitLycanrocAndAlolanRaichu',
        'svScarletAndVioletPromoCards',
        'sveScarletAndVioletEnergies',
        'swshSwordAndShieldPromoCards',
        'tradingCardGameClassic',
        'trickOrTradeBOOsterBundle2023',
        'trickOrTradeBOOsterBundle2024',
        'worldChampionshipDecks',
        'wotcPromo',
        'xyTrainerKitBisharpAndWigglytuff',
        'xyTrainerKitLatiasAndLatios',
        'xyTrainerKitPikachuLibreAndSuicune',
        'xyTrainerKitSylveonAndNoivern'
    ]::text[];

    v_catalog_rows INTEGER := 0;
    v_ready_rows INTEGER := 0;
    v_leaked INTEGER := 0;
BEGIN
    UPDATE public.sets
    SET catalog_only = (canonical_key = ANY(v_catalog_only_keys)),
        supports_opening_simulation = NOT (canonical_key = ANY(v_no_simulation_keys))
    WHERE canonical_key IS NOT NULL;

    SELECT COUNT(*) INTO v_catalog_rows FROM public.sets WHERE catalog_only;

    -- Recompute the operational daily-cohort flag under the corrected rule:
    --   card_details_url present AND NOT catalog_only.
    -- A sealed URL alone must NOT make a set daily-eligible: the cohort and the
    -- completeness check (`pokemon_scrape_missing_sets`) are both defined over
    -- CARD observations, so a sealed-only set could never satisfy completeness
    -- and would permanently wedge the batch.
    UPDATE public.sets
    SET ready_for_daily_scrape = (
            card_details_url IS NOT NULL
            AND length(btrim(card_details_url)) > 0
            AND NOT catalog_only
        );

    SELECT COUNT(*) INTO v_ready_rows FROM public.sets WHERE ready_for_daily_scrape;

    SELECT COUNT(*) INTO v_leaked
    FROM public.sets
    WHERE catalog_only AND ready_for_daily_scrape;

    IF v_leaked > 0 THEN
        RAISE EXCEPTION
            'Migration 058 invariant violated: % catalog-only set(s) still marked ready_for_daily_scrape',
            v_leaked;
    END IF;

    RAISE NOTICE 'Migration 058 backfill: catalog_only=%, ready_for_daily_scrape=%',
        v_catalog_rows, v_ready_rows;
END;
$backfill$;

-- Belt-and-braces: make the invariant structural, not just a one-time backfill.
ALTER TABLE public.sets
    DROP CONSTRAINT IF EXISTS sets_catalog_only_not_daily_ready;

ALTER TABLE public.sets
    ADD CONSTRAINT sets_catalog_only_not_daily_ready
    CHECK (NOT (catalog_only AND ready_for_daily_scrape));

-- =============================================================================
-- 3. Corrected daily cohort
-- =============================================================================
-- Behaviour preserved verbatim: the priority tiering is byte-for-byte unchanged.
-- The ONLY change is the eligibility predicate gaining the catalog_only guard.

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
          -- Catalog-only sets stay in the database and stay usable for manual,
          -- onboarding and historical catalog backfills. They simply must never
          -- gate public daily publication.
          AND COALESCE(s.catalog_only, FALSE) = FALSE
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

-- =============================================================================
-- 4. Corrected REST-fallback enqueue path (same filter, same guard)
-- =============================================================================

CREATE OR REPLACE FUNCTION public.enqueue_missing_scrape_jobs_for_ready_sets()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_inserted INTEGER := 0;
BEGIN
    WITH inserted AS (
        INSERT INTO public.scrape_jobs (set_id, status, attempts, max_attempts, created_at)
        SELECT s.id, 'pending', 0, 3, timezone('utc', now())
        FROM public.sets AS s
        WHERE COALESCE(s.ready_for_daily_scrape, FALSE) = TRUE
          AND COALESCE(s.has_card_details_url, FALSE) = TRUE
          AND s.card_details_url IS NOT NULL
          AND COALESCE(s.catalog_only, FALSE) = FALSE
          AND NOT EXISTS (
              SELECT 1
              FROM public.scrape_jobs AS j
              WHERE j.set_id = s.id
                AND (
                    j.status IN ('pending', 'running')
                    OR (
                        j.status IN ('completed', 'failed')
                        AND timezone('America/Phoenix', j.created_at)::date
                            = timezone('America/Phoenix', now())::date
                    )
                )
          )
        RETURNING id
    )
    SELECT COUNT(*) INTO v_inserted FROM inserted;

    RETURN v_inserted;
END;
$$;

-- =============================================================================
-- 5. Runtime provenance on each batch (Part 2)
-- =============================================================================
-- Makes three questions answerable from ONE row: which code SHA created this
-- batch, which registry hash it validated, and which canonical keys were ready.

ALTER TABLE public.pokemon_scrape_batches
    ADD COLUMN IF NOT EXISTS runtime_git_sha TEXT;

ALTER TABLE public.pokemon_scrape_batches
    ADD COLUMN IF NOT EXISTS runtime_registry_hash TEXT;

ALTER TABLE public.pokemon_scrape_batches
    ADD COLUMN IF NOT EXISTS runtime_preflight_json JSONB;

COMMENT ON COLUMN public.pokemon_scrape_batches.runtime_git_sha IS
    'Git SHA of the runtime that passed preflight and created this batch.';
COMMENT ON COLUMN public.pokemon_scrape_batches.runtime_registry_hash IS
    'SHA-256 of the sorted local eligible canonical keys at batch creation.';
COMMENT ON COLUMN public.pokemon_scrape_batches.runtime_preflight_json IS
    'Full structured preflight report captured at batch creation.';

CREATE OR REPLACE FUNCTION public.record_scrape_batch_runtime_provenance(
    p_batch_id BIGINT,
    p_runtime_git_sha TEXT DEFAULT NULL,
    p_runtime_registry_hash TEXT DEFAULT NULL,
    p_runtime_preflight_json JSONB DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated INTEGER := 0;
BEGIN
    UPDATE public.pokemon_scrape_batches
    SET runtime_git_sha = COALESCE(p_runtime_git_sha, runtime_git_sha),
        runtime_registry_hash = COALESCE(p_runtime_registry_hash, runtime_registry_hash),
        runtime_preflight_json = COALESCE(p_runtime_preflight_json, runtime_preflight_json),
        updated_at = timezone('utc', now())
    WHERE id = p_batch_id;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated = 0 THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'batch_not_found', 'batch_id', p_batch_id);
    END IF;

    RETURN jsonb_build_object('ok', true, 'batch_id', p_batch_id);
END;
$$;

-- =============================================================================
-- 6. Deterministic failure codes (Part 3)
-- =============================================================================

ALTER TABLE public.scrape_jobs
    ADD COLUMN IF NOT EXISTS error_code TEXT;

COMMENT ON COLUMN public.scrape_jobs.error_code IS
    'Stable machine-readable failure code. Deterministic codes (see '
    'backend/db/services/scrape_failure_classification.py) are never requeued.';

-- The canonical non-retryable set. Kept in SQL so cohort repair can enforce the
-- policy even if a worker on an older runtime finalizes without a code.
CREATE OR REPLACE FUNCTION public.scrape_error_code_is_retryable(p_error_code TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
SET search_path = public
AS $$
    SELECT COALESCE(p_error_code, '') NOT IN (
        'invalid_set_key_filter',
        'set_not_found',
        'missing_canonical_key',
        'invalid_scrape_config',
        'catalog_only_not_daily_eligible'
    );
$$;

-- finalize_scrape_job gains `p_error_code`. The previous 9-argument signature is
-- dropped so PostgREST named-parameter dispatch stays unambiguous.
DROP FUNCTION IF EXISTS public.finalize_scrape_job(
    BIGINT, UUID, TEXT, TIMESTAMPTZ, INTEGER, INTEGER, JSONB, TEXT, TEXT
);

CREATE OR REPLACE FUNCTION public.finalize_scrape_job(
    p_job_id BIGINT,
    p_diag_run_id UUID DEFAULT NULL,
    p_final_status TEXT DEFAULT 'completed',
    p_completed_at TIMESTAMPTZ DEFAULT now(),
    p_succeeded INTEGER DEFAULT 0,
    p_failed INTEGER DEFAULT 0,
    p_metrics JSONB DEFAULT '{}'::jsonb,
    p_error_summary TEXT DEFAULT NULL,
    p_report_path TEXT DEFAULT NULL,
    p_error_code TEXT DEFAULT NULL
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
    v_retryable BOOLEAN;
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

    v_retryable := public.scrape_error_code_is_retryable(p_error_code);

    UPDATE public.scrape_jobs
    SET status = p_final_status,
        completed_at = p_completed_at,
        lease_expires_at = NULL,
        heartbeat_at = now(),
        error_message = CASE WHEN p_final_status = 'failed'
                             THEN LEFT(COALESCE(p_error_summary, 'failed'), 2000)
                             ELSE NULL END,
        error_code = CASE WHEN p_final_status = 'failed' THEN p_error_code ELSE NULL END,
        -- A deterministic failure must not consume three identical attempts:
        -- burn the remaining budget so no repair path can reopen it.
        attempts = CASE
            WHEN p_final_status = 'failed' AND NOT v_retryable
            THEN GREATEST(v_job.attempts, v_job.max_attempts)
            ELSE v_job.attempts
        END,
        diag_run_id = COALESCE(p_diag_run_id, diag_run_id)
    WHERE id = p_job_id AND status = 'running';
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    v_batch_id := v_job.batch_id;

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
            metadata = COALESCE(metadata, '{}'::jsonb)
                       || COALESCE(p_metrics, '{}'::jsonb)
                       || CASE WHEN p_error_code IS NULL THEN '{}'::jsonb
                               ELSE jsonb_build_object('error_code', p_error_code) END
        WHERE id = p_diag_run_id;
    END IF;

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
        'error_code', p_error_code,
        'retryable', v_retryable,
        'queue_rows_updated', v_updated
    );
END;
$$;

-- =============================================================================
-- 7. Cohort repair refuses to reopen deterministic failures (Part 3)
-- =============================================================================

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
          -- A deterministic configuration/deployment failure is not fixed by
          -- trying again; reopening it only burns attempts and hides the defect.
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

-- =============================================================================
-- 8. Re-assert migration 051 privilege rules for every touched function
-- =============================================================================
-- Every function replaced above keeps SECURITY DEFINER + fixed search_path, and
-- must remain service_role-only. `CREATE OR REPLACE` preserves existing ACLs, but
-- the newly created functions (and the re-created finalize_scrape_job) need the
-- rules applied explicitly. No RLS policy is added and no unrelated function is
-- granted anything here.

REVOKE ALL ON FUNCTION public.pokemon_scrape_ready_cohort()
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.enqueue_missing_scrape_jobs_for_ready_sets()
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(bigint)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_scrape_batch_runtime_provenance(bigint, text, text, jsonb)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.scrape_error_code_is_retryable(text)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finalize_scrape_job(
    bigint, uuid, text, timestamptz, integer, integer, jsonb, text, text, text
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.pokemon_scrape_ready_cohort()
    TO service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_missing_scrape_jobs_for_ready_sets()
    TO service_role;
GRANT EXECUTE ON FUNCTION public.requeue_missing_scrape_jobs_for_batch(bigint)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.record_scrape_batch_runtime_provenance(bigint, text, text, jsonb)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.scrape_error_code_is_retryable(text)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.finalize_scrape_job(
    bigint, uuid, text, timestamptz, integer, integer, jsonb, text, text, text
) TO service_role;

COMMIT;
