BEGIN;

DO $$
DECLARE
  v_jobid bigint;
  v_def text;
  v_config text[];
BEGIN
  SELECT pg_get_functiondef(p.oid), p.proconfig
    INTO v_def, v_config
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='run_price_storage_v2_shadow_cycle'
  LIMIT 1;

  IF v_def IS NULL THEN
    RAISE EXCEPTION 'run_price_storage_v2_shadow_cycle is missing';
  END IF;
  IF position('process_price_storage_v2_shadow_queue(' in v_def) > 0
     OR position('delegated_to_application_staged_worker' in v_def) = 0 THEN
    RAISE EXCEPTION 'Refusing to reactivate cron: shadow cycle is not the bounded staged-worker coordinator';
  END IF;
  IF NOT ('statement_timeout=15s' = ANY(coalesce(v_config,ARRAY[]::text[]))) THEN
    RAISE EXCEPTION 'Refusing to reactivate cron: expected 15s statement timeout is missing';
  END IF;

  SELECT jobid INTO v_jobid
  FROM cron.job
  WHERE jobname='price-storage-v2-shadow-cycle'
  ORDER BY jobid
  LIMIT 1;

  IF v_jobid IS NULL THEN
    RAISE EXCEPTION 'price-storage-v2-shadow-cycle cron job is missing';
  END IF;

  PERFORM cron.alter_job(v_jobid, active := true);
END $$;

COMMIT;
