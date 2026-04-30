-- Migration 014: Cleanup stale pending waitlist verification rows.
-- Only touches waitlist_signups and does not affect auth/profile/portfolio/explore systems.

CREATE OR REPLACE FUNCTION public.cleanup_expired_waitlist_signups()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    deleted_count integer;
BEGIN
    DELETE FROM public.waitlist_signups
    WHERE status = 'pending_verification'
      AND verified_at IS NULL
      AND created_at < now() - interval '24 hours';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

COMMENT ON FUNCTION public.cleanup_expired_waitlist_signups() IS
    'Deletes stale waitlist rows in pending_verification older than 24h and returns deleted row count.';

DO $do$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        IF NOT EXISTS (
            SELECT 1
            FROM cron.job
            WHERE jobname = 'cleanup-expired-waitlist-signups'
        ) THEN
            PERFORM cron.schedule(
                'cleanup-expired-waitlist-signups',
                '0 * * * *',
                $$select public.cleanup_expired_waitlist_signups();$$
            );
        END IF;
    ELSE
        -- pg_cron is not enabled; invoke this function from the existing scheduler/cron runner.
        RAISE NOTICE 'pg_cron not enabled; call public.cleanup_expired_waitlist_signups() from existing scheduler.';
    END IF;
END;
$do$;
