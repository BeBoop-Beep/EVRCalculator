-- Migration 012: Create waitlist_signups table for email interest capture.
-- This table stores landing page email signups only.
-- It does NOT create auth users or grant any access to authenticated routes.

CREATE TABLE IF NOT EXISTS public.waitlist_signups (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text        NOT NULL UNIQUE,
    source      text        NOT NULL DEFAULT 'landing_page',
    status      text        NOT NULL DEFAULT 'active',
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Index on email for fast duplicate checks.
CREATE INDEX IF NOT EXISTS idx_waitlist_signups_email ON public.waitlist_signups (email);

-- RLS: table is private; all access goes through the service-role key on the backend.
ALTER TABLE public.waitlist_signups ENABLE ROW LEVEL SECURITY;

-- No public policies: only service-role bypasses RLS.
-- Direct browser access is not permitted.

COMMENT ON TABLE public.waitlist_signups IS
    'Email interest/waitlist signups from the landing page. Not linked to auth users.';
