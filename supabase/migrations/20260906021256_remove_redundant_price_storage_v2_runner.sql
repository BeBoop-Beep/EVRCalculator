BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'price-storage-v2-shadow-promoted-batch') THEN
        PERFORM cron.unschedule('price-storage-v2-shadow-promoted-batch');
    END IF;
END $$;

DROP FUNCTION IF EXISTS public.process_latest_promoted_price_storage_v2_shadow();
DROP FUNCTION IF EXISTS public.process_price_storage_v2_market_date(date);
DROP TABLE IF EXISTS public.price_storage_v2_shadow_runs;

COMMIT;