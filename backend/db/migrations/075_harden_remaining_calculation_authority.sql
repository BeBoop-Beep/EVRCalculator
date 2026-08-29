-- Mirrored by supabase/migrations/20260830013500_harden_remaining_calculation_authority.sql.
DO $migration$
DECLARE relation_name text;
BEGIN
  FOREACH relation_name IN ARRAY ARRAY[
    'calculation_configs', 'calculation_price_snapshots',
    'manual_calculation_results', 'calculation_history_daily_latest',
    'calculation_history_trend', 'calculation_latest_by_target'
  ] LOOP
    IF to_regclass(format('public.%I', relation_name)) IS NOT NULL THEN
      EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', relation_name);
      EXECUTE format('GRANT ALL ON public.%I TO service_role', relation_name);
    END IF;
  END LOOP;
END $migration$;
