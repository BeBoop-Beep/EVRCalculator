-- Regression contract for Effort 4 operational functions.
DO $test$
DECLARE
  function_signature text;
  function_signatures constant text[] := ARRAY[
    'public.claim_next_pokemon_set_onboarding_job(text,integer,uuid,boolean)',
    'public.heartbeat_pokemon_set_onboarding_job(uuid,text,integer)',
    'public.cleanup_expired_waitlist_signups()',
    'public.get_nightly_snapshot_pricing_freshness(date,integer)'
  ];
BEGIN
  FOREACH function_signature IN ARRAY function_signatures LOOP
    IF has_function_privilege('anon', function_signature, 'EXECUTE') THEN
      RAISE EXCEPTION 'anon unexpectedly has EXECUTE on %', function_signature;
    END IF;
    IF has_function_privilege('authenticated', function_signature, 'EXECUTE') THEN
      RAISE EXCEPTION 'authenticated unexpectedly has EXECUTE on %', function_signature;
    END IF;
    IF NOT has_function_privilege('service_role', function_signature, 'EXECUTE') THEN
      RAISE EXCEPTION 'service_role lacks EXECUTE on %', function_signature;
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = ANY (ARRAY[
        'claim_next_pokemon_set_onboarding_job', 'heartbeat_pokemon_set_onboarding_job',
        'cleanup_expired_waitlist_signups', 'get_nightly_snapshot_pricing_freshness'
      ])
      AND (NOT p.prosecdef OR p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog']::text[])
  ) THEN
    RAISE EXCEPTION 'operational function lost SECURITY DEFINER or safe search_path';
  END IF;
END $test$;
