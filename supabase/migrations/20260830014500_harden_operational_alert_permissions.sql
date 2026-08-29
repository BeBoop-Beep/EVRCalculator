-- Keep operational alert history and queue execution private to backend workers.
-- Trigger functions remain SECURITY INVOKER; no browser role needs direct access.

ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS alert_events_public_access ON public.alert_events;

REVOKE ALL ON TABLE public.alert_events FROM PUBLIC;
REVOKE ALL ON TABLE public.alert_events FROM anon;
REVOKE ALL ON TABLE public.alert_events FROM authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.alert_events TO service_role;

ALTER FUNCTION public.queue_scrape_failure_alert()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.queue_scrape_run_alert()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.queue_scrape_run_ratio_alerts()
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.queue_stuck_scrape_run_alerts()
  SET search_path = pg_catalog, public;

REVOKE EXECUTE ON FUNCTION public.queue_scrape_failure_alert()
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.queue_scrape_run_alert()
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.queue_scrape_run_ratio_alerts()
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.queue_stuck_scrape_run_alerts()
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.queue_scrape_failure_alert() TO service_role;
GRANT EXECUTE ON FUNCTION public.queue_scrape_run_alert() TO service_role;
GRANT EXECUTE ON FUNCTION public.queue_scrape_run_ratio_alerts() TO service_role;
GRANT EXECUTE ON FUNCTION public.queue_stuck_scrape_run_alerts() TO service_role;
