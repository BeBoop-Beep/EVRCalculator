-- Migration 013: Add waitlist email verification support.
-- Waitlist remains isolated from auth, profiles, portfolio, and explore domains.

ALTER TABLE public.waitlist_signups
    ADD COLUMN IF NOT EXISTS verification_token_hash text,
    ADD COLUMN IF NOT EXISTS verification_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS verified_at timestamptz;

-- Keep legacy rows valid while moving new signups to verification-first flow.
UPDATE public.waitlist_signups
SET status = 'active'
WHERE status IS NULL OR btrim(status) = '';

UPDATE public.waitlist_signups
SET status = 'active'
WHERE status NOT IN (
    'pending_verification',
    'active',
    'unsubscribed',
    'invited',
    'converted'
);

ALTER TABLE public.waitlist_signups
    ALTER COLUMN status SET DEFAULT 'pending_verification';

ALTER TABLE public.waitlist_signups
    DROP CONSTRAINT IF EXISTS waitlist_signups_status_check;

ALTER TABLE public.waitlist_signups
    ADD CONSTRAINT waitlist_signups_status_check
    CHECK (status IN (
        'pending_verification',
        'active',
        'unsubscribed',
        'invited',
        'converted'
    ));

CREATE INDEX IF NOT EXISTS idx_waitlist_signups_verification_token_hash
    ON public.waitlist_signups (verification_token_hash);
