-- Migration 015: Keep waitlist cleanup pruning pending rows and clear stale active token hashes.
-- Waitlist-only change; active rows are never deleted.

CREATE OR REPLACE FUNCTION public.cleanup_expired_waitlist_signups()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    deleted_pending_count integer := 0;
    cleared_active_hash_count integer := 0;
BEGIN
    DELETE FROM public.waitlist_signups
    WHERE status = 'pending_verification'
      AND verified_at IS NULL
      AND created_at < now() - interval '24 hours';

    GET DIAGNOSTICS deleted_pending_count = ROW_COUNT;

    UPDATE public.waitlist_signups
    SET verification_token_hash = NULL
    WHERE status = 'active'
      AND verified_at IS NOT NULL
      AND verification_token_hash IS NOT NULL
      AND verification_sent_at < now() - interval '24 hours';

    GET DIAGNOSTICS cleared_active_hash_count = ROW_COUNT;

    RETURN deleted_pending_count + cleared_active_hash_count;
END;
$$;

COMMENT ON FUNCTION public.cleanup_expired_waitlist_signups() IS
    'Deletes stale pending waitlist rows older than 24h and clears stale active verification token hashes older than 24h; returns total rows affected.';
