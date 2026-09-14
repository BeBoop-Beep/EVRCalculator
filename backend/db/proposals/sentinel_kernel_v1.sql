-- inDex Sentinel kernel persistence proposal.
--
-- PROPOSAL ONLY. Prompt 2 does not apply this SQL to production and does not
-- create a migration file. Generate a real migration with the project's
-- Supabase CLI workflow only when production activation is explicitly approved.
--
-- Access model:
--   * server-side Sentinel/service_role only
--   * no anon/authenticated/public table access
--   * RLS enabled on every public-schema Sentinel table
--   * no privileged helper functions or RPCs

BEGIN;

CREATE TABLE public.sentinel_incidents (
    id uuid PRIMARY KEY,
    fingerprint text NOT NULL,
    check_key text NOT NULL,
    severity text NOT NULL
        CHECK (severity IN ('info','warning','error','critical')),
    status text NOT NULL
        CHECK (status IN ('open','recovering','escalated','resolved')),
    failure_code text NOT NULL,
    authority_identity text,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    resolved_at timestamptz,
    market_date date,
    batch_id bigint,
    generation_id uuid,
    deployment_sha text,
    expected_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    recovery_eligible boolean NOT NULL DEFAULT false,
    recovery_attempt_count integer NOT NULL DEFAULT 0
        CHECK (recovery_attempt_count >= 0),
    ai_triage_status text NOT NULL DEFAULT 'disabled',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX sentinel_incidents_one_active_fingerprint_uq
    ON public.sentinel_incidents (fingerprint)
    WHERE status IN ('open','recovering','escalated');

CREATE INDEX sentinel_incidents_status_last_seen_idx
    ON public.sentinel_incidents (status, last_seen_at DESC);

CREATE TABLE public.sentinel_check_state (
    check_key text PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('healthy','suspect','failing')),
    last_checked_at timestamptz,
    last_success_at timestamptz,
    first_failure_at timestamptz,
    last_failure_at timestamptz,
    consecutive_failures integer NOT NULL DEFAULT 0
        CHECK (consecutive_failures >= 0),
    current_incident_id uuid
        REFERENCES public.sentinel_incidents(id)
        ON DELETE SET NULL,
    last_observation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    observation_hash text,
    runner_build_sha text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.sentinel_recovery_attempts (
    id uuid PRIMARY KEY,
    incident_id uuid NOT NULL
        REFERENCES public.sentinel_incidents(id)
        ON DELETE CASCADE,
    runbook text NOT NULL,
    runbook_version text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    preconditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL
        CHECK (status IN ('started','succeeded','failed','blocked')),
    attempt_number integer NOT NULL CHECK (attempt_number >= 1),
    cooldown_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (incident_id, runbook, attempt_number)
);

CREATE TABLE public.sentinel_component_heartbeats (
    component text NOT NULL,
    host text NOT NULL,
    build_sha text NOT NULL,
    heartbeat_at timestamptz NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (component, host)
);

CREATE INDEX sentinel_component_heartbeats_at_idx
    ON public.sentinel_component_heartbeats (heartbeat_at DESC);

ALTER TABLE public.sentinel_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sentinel_check_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sentinel_recovery_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sentinel_component_heartbeats ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sentinel_incidents
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.sentinel_check_state
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.sentinel_recovery_attempts
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.sentinel_component_heartbeats
    FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.sentinel_incidents
    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sentinel_check_state
    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sentinel_recovery_attempts
    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sentinel_component_heartbeats
    TO service_role;

COMMENT ON TABLE public.sentinel_incidents IS
    'Internal Sentinel incident lifecycle state; service-role only.';
COMMENT ON TABLE public.sentinel_check_state IS
    'Latest Sentinel state per deterministic check; service-role only.';
COMMENT ON TABLE public.sentinel_recovery_attempts IS
    'Future bounded recovery audit trail. Prompt-2 recovery remains disabled.';
COMMENT ON TABLE public.sentinel_component_heartbeats IS
    'Latest heartbeat per Sentinel/runtime component and host; service-role only.';

COMMIT;
