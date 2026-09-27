-- Bound background database maintenance after the 2026-09-24 522 incident.
--
-- Evidence captured from production logs before this migration:
--   * run_price_storage_v2_shadow_cycle() consumed ~56.9s at 2026-09-24 21:30 UTC.
--   * get_pokemon_market_explorer_set_history_coverage_v1(NULL) consumed ~16.1s.
--   * shortly afterward, REST, Supavisor session, and Supavisor transaction
--     connections all failed against the project origin.
--
-- This migration is deliberately methodology-neutral. It changes scheduling
-- work budgets and lookup paths, not price/index calculations or market identity.

begin;

-- Fast predicates used every 15 minutes by enqueue/root-history gates.
create index if not exists idx_scrape_jobs_completed_market_set_v2
  on public.scrape_jobs (market_date, set_id, completed_at desc)
  where status = 'completed'
    and set_id is not null
    and completed_at is not null;

create index if not exists idx_price_storage_v2_shadow_queue_market_status_set_v2
  on public.price_storage_v2_shadow_queue (market_date, status, set_id);

-- The monthly worker claims pending/failed jobs in rollup_month,set_id order.
create index if not exists idx_price_storage_v2_monthly_rollup_claim_v2
  on public.price_storage_v2_monthly_rollup_backfill_sets (rollup_month, set_id)
  where status in ('pending','failed') and attempts < 5;

-- A previous-month rollup is not latency-sensitive. The former coordinator
-- processed as many as 10 Sets inside each 15-minute pg_cron transaction.
-- Production observed one cycle at ~56.9 seconds. Keep progress continuous but
-- bound one invocation to one Set so a single maintenance tick cannot monopolize
-- the database for a large batch.
create or replace function public.sync_price_storage_v2_previous_monthly_rollup()
returns jsonb
language plpgsql
security invoker
set search_path = ''
set lock_timeout = '2s'
as $function$
declare
  v_month date := (
    date_trunc('month', timezone('America/Phoenix', now())) - interval '1 month'
  )::date;
begin
  return public.sync_price_storage_v2_monthly_rollup_month(v_month, 1, true);
end;
$function$;

revoke all on function public.sync_price_storage_v2_previous_monthly_rollup()
from public, anon, authenticated;
grant execute on function public.sync_price_storage_v2_previous_monthly_rollup()
to postgres, service_role;

comment on function public.sync_price_storage_v2_previous_monthly_rollup() is
'Previous-month Price Storage V2 rollup coordinator. Processes one Set per invocation so the 15-minute maintenance cycle stays bounded under database load.';

-- Keep the 15-minute cycle as an enqueue/maintenance coordinator only.
-- An advisory xact lock makes duplicate/overlapping cron invocations fail open
-- as a cheap no-op. A 15-second statement budget prevents a maintenance tick
-- from recreating the long-running workload observed immediately before the
-- database-origin outage.
create or replace function public.run_price_storage_v2_shadow_cycle()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '15s'
set lock_timeout = '2s'
as $function$
declare
  v_market_date date := timezone('America/Phoenix', now())::date;
  v_previous jsonb;
  v_current jsonb;
  v_root_history jsonb;
  v_monthly_rollup jsonb;
  v_lock_key bigint := pg_catalog.hashtextextended(
    'price-storage-v2-shadow-cycle-v2',
    0
  );
begin
  if not pg_catalog.pg_try_advisory_xact_lock(v_lock_key) then
    return jsonb_build_object(
      'status','skipped',
      'reason','already_running',
      'phoenix_market_date',v_market_date
    );
  end if;

  v_previous := public.enqueue_price_storage_v2_completed_scrape_jobs(
    v_market_date - 1, 1000
  );
  v_current := public.enqueue_price_storage_v2_completed_scrape_jobs(
    v_market_date, 1000
  );

  begin
    v_root_history := public.sync_price_storage_v2_root_history_latest();
  exception when others then
    v_root_history := jsonb_build_object(
      'status','error','error',left(sqlerrm,1000)
    );
  end;

  begin
    v_monthly_rollup := public.sync_price_storage_v2_previous_monthly_rollup();
  exception when others then
    v_monthly_rollup := jsonb_build_object(
      'status','error','error',left(sqlerrm,1000)
    );
  end;

  return jsonb_build_object(
    'status','complete',
    'phoenix_market_date',v_market_date,
    'previous_date_enqueue',v_previous,
    'current_date_enqueue',v_current,
    'queue_processing',jsonb_build_object(
      'status','delegated_to_application_staged_worker',
      'processed',0
    ),
    'root_history_sync',v_root_history,
    'monthly_rollup_sync',v_monthly_rollup,
    'maintenance_budget',jsonb_build_object(
      'monthly_sets_per_cycle',1,
      'statement_timeout_seconds',15,
      'overlap_guard','transaction_advisory_lock'
    )
  );
end;
$function$;

revoke all on function public.run_price_storage_v2_shadow_cycle()
from public, anon, authenticated;
grant execute on function public.run_price_storage_v2_shadow_cycle()
to service_role;

comment on function public.run_price_storage_v2_shadow_cycle() is
'Bounded 15-minute Price Storage V2 maintenance coordinator. Queue execution remains delegated to the application staged worker; one monthly Set is processed per tick, overlap is advisory-lock guarded, and the cycle has a 15-second statement budget.';

-- Legacy all-Set coverage remains available for callers that genuinely need
-- the complete list, but it must not occupy an interactive PostgREST worker for
-- 30 seconds. The dedicated partial (set_id,snapshot_date) index already exists.
alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])
  set statement_timeout = '5s';
alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])
  set lock_timeout = '1s';
alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])
  set jit = 'off';

-- Newer planners that only need the yes/no history preflight should not ask the
-- coverage RPC to aggregate every Set and every date. This uses the same
-- canonical standard-history semantics but stops at the first indexed match.
create or replace function public.has_pokemon_market_explorer_set_history_v1(
  p_set_ids uuid[] default null
)
returns boolean
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set lock_timeout = '500ms'
set jit = 'off'
as $function$
  select exists (
    select 1
    from public.pokemon_set_value_daily_history h
    join public.sets s on s.id = h.set_id
    where h.value_scope = 'standard'
      and coalesce(s.catalog_only, false) = false
      and (p_set_ids is null or h.set_id = any(p_set_ids))
    limit 1
  );
$function$;

revoke all on function public.has_pokemon_market_explorer_set_history_v1(uuid[])
from public, anon, authenticated;
grant execute on function public.has_pokemon_market_explorer_set_history_v1(uuid[])
to service_role;

comment on function public.has_pokemon_market_explorer_set_history_v1(uuid[]) is
'Cheap indexed existence preflight for Market Explorer card history. Use when callers only need to know whether a scope has standard Set Value history; do not enumerate the full coverage matrix for that case.';

commit;
