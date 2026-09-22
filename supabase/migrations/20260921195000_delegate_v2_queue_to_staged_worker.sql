BEGIN;

CREATE OR REPLACE FUNCTION public.run_price_storage_v2_shadow_cycle()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_market_date date:=timezone('America/Phoenix',now())::date;
    v_previous jsonb;
    v_current jsonb;
    v_root_history jsonb;
    v_monthly_rollup jsonb;
BEGIN
    /*
     * Queue execution is intentionally NOT performed here.
     *
     * The original pg_cron cycle called process_price_storage_v2_shadow_queue(20),
     * which runs all four expensive per-set projection stages inside one database
     * transaction. The post-scrape publication path now owns queue execution via
     * the application-level staged worker, where each stage has its own bounded
     * transaction/retry boundary. Running both workers concurrently causes the
     * monolithic cron transaction to hold queue-row locks while the staged worker
     * tries to claim/update the same cohort, amplifying statement/read timeouts
     * and consuming retry budgets.
     *
     * Keep the 15-minute job only for idempotent enqueue coverage plus the
     * independent root-history/monthly maintenance attached to this cycle.
     */
    v_previous:=public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date-1,1000);
    v_current:=public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date,1000);

    BEGIN
      v_root_history:=public.sync_price_storage_v2_root_history_latest();
    EXCEPTION WHEN OTHERS THEN
      v_root_history:=jsonb_build_object('status','error','error',left(SQLERRM,1000));
    END;

    BEGIN
      v_monthly_rollup:=public.sync_price_storage_v2_previous_monthly_rollup();
    EXCEPTION WHEN OTHERS THEN
      v_monthly_rollup:=jsonb_build_object('status','error','error',left(SQLERRM,1000));
    END;

    RETURN jsonb_build_object(
      'phoenix_market_date',v_market_date,
      'previous_date_enqueue',v_previous,
      'current_date_enqueue',v_current,
      'queue_processing',jsonb_build_object(
          'status','delegated_to_application_staged_worker',
          'processed',0
      ),
      'root_history_sync',v_root_history,
      'monthly_rollup_sync',v_monthly_rollup
    );
END;
$function$;

COMMENT ON FUNCTION public.run_price_storage_v2_shadow_cycle() IS
'15-minute Price Storage V2 maintenance cycle. Enqueues completed scrape dates and maintains root/monthly projections; queue execution is delegated to the application staged worker to avoid monolithic pg_cron lock/timeout contention.';

COMMIT;
