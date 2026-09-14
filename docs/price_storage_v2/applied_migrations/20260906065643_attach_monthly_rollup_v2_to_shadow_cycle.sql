create or replace function public.run_price_storage_v2_shadow_cycle()
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
    v_market_date date:=timezone('America/Phoenix',now())::date;
    v_previous jsonb;
    v_current jsonb;
    v_processed jsonb;
    v_root_history jsonb;
    v_monthly_rollup jsonb;
begin
    v_previous:=public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date-1,1000);
    v_current:=public.enqueue_price_storage_v2_completed_scrape_jobs(v_market_date,1000);
    v_processed:=public.process_price_storage_v2_shadow_queue(20);

    begin
      v_root_history:=public.sync_price_storage_v2_root_history_latest();
    exception when others then
      v_root_history:=jsonb_build_object('status','error','error',left(SQLERRM,1000));
    end;

    begin
      v_monthly_rollup:=public.sync_price_storage_v2_previous_monthly_rollup();
    exception when others then
      v_monthly_rollup:=jsonb_build_object('status','error','error',left(SQLERRM,1000));
    end;

    return jsonb_build_object(
      'phoenix_market_date',v_market_date,
      'previous_date_enqueue',v_previous,
      'current_date_enqueue',v_current,
      'queue_processing',v_processed,
      'root_history_sync',v_root_history,
      'monthly_rollup_sync',v_monthly_rollup
    );
end;
$$;