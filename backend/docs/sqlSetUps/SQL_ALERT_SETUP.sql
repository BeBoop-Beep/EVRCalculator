-- SQL Setup for Alert Events infrastructure
--
-- This file contains:
-- 1. Table: public.alert_events
-- 2. Index for efficient query of unsent alerts
-- 3. Example trigger to auto-queue alerts on scrape failures
--
-- Run this in Supabase SQL editor or via psql client

-- =============================================================================
-- 1. Create alert_events table
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.alert_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_type TEXT NOT NULL,           -- e.g., "scrape_failure", "rate_limit_pressure"
  severity TEXT NOT NULL,              -- "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"
  title TEXT NOT NULL,                 -- Short, human-readable title (max ~100 chars recommended)
  message TEXT NOT NULL,               -- Full message body (markdown OK for Slack)
  payload JSONB DEFAULT '{}',          -- Optional structured data (run_id, metrics, etc.)
  sent BOOLEAN DEFAULT FALSE,
  sent_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS if using Supabase (public can read+write, backend service uses anon key)
ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;

-- This policy allows public read/write (backend service has service role for unrestricted access)
CREATE POLICY alert_events_public_access ON public.alert_events
  FOR ALL USING (true) WITH CHECK (true);

-- =============================================================================
-- 2. Create indexing for efficient unsent alert queries
-- =============================================================================

-- Multi-column index: fetch unsent alerts ordered by creation
CREATE INDEX IF NOT EXISTS idx_alert_events_sent_created 
  ON public.alert_events(sent, created_at ASC);

-- Single index for updates by id
CREATE INDEX IF NOT EXISTS idx_alert_events_id 
  ON public.alert_events(id);

-- Index for alert_type filtering (useful for future alert subscription patterns)
CREATE INDEX IF NOT EXISTS idx_alert_events_alert_type 
  ON public.alert_events(alert_type);

-- =============================================================================
-- 3. Example: Auto-queue alerts on scrape job failure
-- =============================================================================
-- This trigger fires when a scrape_job_runs row is updated to a failed status.
-- Uncomment and adjust as needed for your alert requirements.

-- CREATE OR REPLACE FUNCTION public.queue_scrape_failure_alert()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   -- Only queue alert if status changed TO a failure/partial state
--   IF (OLD.status IS DISTINCT FROM NEW.status) 
--     AND NEW.status IN ('failed', 'partial_failure') THEN
--     
--     INSERT INTO public.alert_events (
--       alert_type,
--       severity,
--       title,
--       message,
--       payload
--     ) VALUES (
--       'scrape_run_' || NEW.status,
--       CASE WHEN NEW.status = 'failed' THEN 'CRITICAL' ELSE 'WARNING' END,
--       'Scrape ' || NEW.status || ': ' || NEW.job_name,
--       'Job ' || NEW.job_name || ' (' || NEW.source_system || ') ended with status: ' || NEW.status,
--       jsonb_build_object(
--         'run_id', NEW.id::text,
--         'job_name', NEW.job_name,
--         'source_system', NEW.source_system,
--         'job_type', NEW.job_type,
--         'entity_type', NEW.entity_type,
--         'status', NEW.status,
--         'items_attempted', NEW.items_attempted,
--         'items_failed', NEW.items_failed,
--         'items_skipped', NEW.items_skipped,
--         'http_requests_total', NEW.http_requests_total,
--         'rate_limit_events', NEW.rate_limit_events,
--         'error_summary', NEW.error_summary
--       )
--     );
--   END IF;
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;

-- -- Create the trigger
-- CREATE TRIGGER trg_scrape_runs_alert
--   AFTER UPDATE ON public.scrape_job_runs
--   FOR EACH ROW
--   EXECUTE FUNCTION public.queue_scrape_failure_alert();

-- =============================================================================
-- 4. Example: Rate-limit pressure alert
-- =============================================================================
-- Alert if a scrape run has excessive rate-limit events

-- CREATE OR REPLACE FUNCTION public.queue_rate_limit_alert()
-- RETURNS TRIGGER AS $$
-- DECLARE
--   rate_limit_threshold INT := 10;  -- Alert if >= 10 rate-limit events
-- BEGIN
--   IF NEW.rate_limit_events >= rate_limit_threshold THEN
--     INSERT INTO public.alert_events (
--       alert_type,
--       severity,
--       title,
--       message,
--       payload
--     ) VALUES (
--       'rate_limit_pressure',
--       'WARNING',
--       'Rate-limit pressure on ' || NEW.job_name,
--       'Job ' || NEW.job_name || ' experienced ' || NEW.rate_limit_events || ' rate-limit events during run',
--       jsonb_build_object(
--         'run_id', NEW.id::text,
--         'job_name', NEW.job_name,
--         'source_system', NEW.source_system,
--         'rate_limit_events', NEW.rate_limit_events
--       )
--     );
--   END IF;
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;

-- CREATE TRIGGER trg_scrape_runs_rate_limit
--   AFTER UPDATE ON public.scrape_job_runs
--   FOR EACH ROW
--   EXECUTE FUNCTION public.queue_rate_limit_alert();

-- =============================================================================
-- 5. Verify table creation
-- =============================================================================

-- Run this to confirm the table exists and has correct structure:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'alert_events' AND table_schema = 'public'
-- ORDER BY ordinal_position;

-- =============================================================================
-- 6. Test insert (to verify table works)
-- =============================================================================

-- INSERT INTO public.alert_events (
--   alert_type,
--   severity,
--   title,
--   message,
--   payload
-- ) VALUES (
--   'test_alert',
--   'INFO',
--   'Test Alert',
--   'This is a test alert from the database setup',
--   '{"test": true, "timestamp": "2026-04-12T00:00:00Z"}'::jsonb
-- );

-- -- Verify:
-- SELECT id, alert_type, severity, title, sent, created_at
-- FROM public.alert_events
-- WHERE alert_type = 'test_alert'
-- ORDER BY created_at DESC LIMIT 1;
