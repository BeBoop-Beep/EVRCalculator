-- Transactional permission contract for the private operational alert subsystem.
BEGIN;

DO $test$
DECLARE
  role_name text;
  statement text;
  function_signature text;
  statements constant text[] := ARRAY[
    'SELECT id FROM public.alert_events LIMIT 1',
    $$INSERT INTO public.alert_events (alert_type, severity, title, message)
      VALUES ('permission_probe', 'info', 'permission probe', 'rolled back')$$,
    $$UPDATE public.alert_events SET sent = sent WHERE false$$,
    $$DELETE FROM public.alert_events WHERE false$$
  ];
  function_signatures constant text[] := ARRAY[
    'public.queue_scrape_failure_alert()',
    'public.queue_scrape_run_alert()',
    'public.queue_scrape_run_ratio_alerts()',
    'public.queue_stuck_scrape_run_alerts()'
  ];
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public' AND c.relname = 'alert_events') THEN
    RAISE EXCEPTION 'RLS is not enabled on public.alert_events';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relname = 'alert_events'
               AND p.polname = 'alert_events_public_access') THEN
    RAISE EXCEPTION 'alert_events_public_access still exists';
  END IF;

  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    EXECUTE format('SET LOCAL ROLE %I', role_name);
    FOREACH statement IN ARRAY statements LOOP
      BEGIN
        EXECUTE statement;
        RAISE EXCEPTION '% unexpectedly executed %', role_name, statement;
      EXCEPTION
        WHEN insufficient_privilege THEN NULL;
      END;
    END LOOP;
    FOREACH function_signature IN ARRAY function_signatures LOOP
      BEGIN
        EXECUTE format('SELECT %s', function_signature);
        RAISE EXCEPTION '% unexpectedly executed %', role_name, function_signature;
      EXCEPTION
        WHEN insufficient_privilege THEN NULL;
      END;
    END LOOP;
    RESET ROLE;
  END LOOP;

  FOREACH function_signature IN ARRAY function_signatures LOOP
    IF NOT has_function_privilege('service_role', function_signature, 'EXECUTE') THEN
      RAISE EXCEPTION 'service_role lacks EXECUTE on %', function_signature;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = ANY (ARRAY[
        'queue_scrape_failure_alert', 'queue_scrape_run_alert',
        'queue_scrape_run_ratio_alerts', 'queue_stuck_scrape_run_alerts'
      ])
      AND (p.prosecdef OR p.proconfig IS DISTINCT FROM
           ARRAY['search_path=pg_catalog, public']::text[])
  ) THEN
    RAISE EXCEPTION 'alert queue function lost invoker security or safe search_path';
  END IF;
END $test$;

SET LOCAL ROLE service_role;

INSERT INTO public.alert_events (alert_type, severity, dedupe_key, title, message, payload)
VALUES ('permission_probe', 'info', 'permission-probe-rollback',
        'permission probe', 'rolled back', '{"probe": true}'::jsonb);

DO $test$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.alert_events
                 WHERE dedupe_key = 'permission-probe-rollback') THEN
    RAISE EXCEPTION 'service_role alert insert/read path failed';
  END IF;
END $test$;

UPDATE public.alert_events
SET suppressed_at = now(), suppression_reason = 'transactional permission probe'
WHERE dedupe_key = 'permission-probe-rollback';

DELETE FROM public.alert_events WHERE dedupe_key = 'permission-probe-rollback';

SELECT public.queue_scrape_run_ratio_alerts();
SELECT public.queue_stuck_scrape_run_alerts();

RESET ROLE;
ROLLBACK;
