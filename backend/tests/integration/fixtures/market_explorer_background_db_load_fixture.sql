-- Disposable PostgreSQL 17 dependencies for the DB-load hardening migration.
-- Loaded after the main Market Explorer expansion fixture.

create table if not exists public.scrape_jobs(
  set_id uuid,
  market_date date,
  status text,
  completed_at timestamptz
);

create table if not exists public.price_storage_v2_shadow_queue(
  set_id uuid,
  market_date date,
  status text
);

create table if not exists public.price_storage_v2_monthly_rollup_backfill_sets(
  set_id uuid,
  rollup_month date,
  status text,
  attempts integer not null default 0
);

create table if not exists public.pokemon_set_value_daily_history(
  set_id uuid,
  snapshot_date date,
  value_scope text
);

create or replace function public.enqueue_price_storage_v2_completed_scrape_jobs(
  p_market_date date,
  p_limit integer default 500
)
returns jsonb language sql set search_path='' as $$
  select jsonb_build_object('market_date',p_market_date,'enqueued',0);
$$;

create or replace function public.sync_price_storage_v2_root_history_latest()
returns jsonb language sql set search_path='' as $$
  select '{"status":"noop"}'::jsonb;
$$;

create or replace function public.sync_price_storage_v2_monthly_rollup_month(
  p_month date,
  p_process_limit integer default 10,
  p_publish boolean default true
)
returns jsonb language sql set search_path='' as $$
  select jsonb_build_object(
    'status','noop','month',p_month,'limit',p_process_limit,'publish',p_publish
  );
$$;

create or replace function public.get_pokemon_market_explorer_set_history_coverage_v1(
  p_set_ids uuid[] default null
)
returns table(set_id uuid,first_snapshot_date date,latest_snapshot_date date)
language sql stable security invoker set search_path='' as $$
  select h.set_id,min(h.snapshot_date),max(h.snapshot_date)
  from public.pokemon_set_value_daily_history h
  where h.value_scope='standard'
    and (p_set_ids is null or h.set_id=any(p_set_ids))
  group by h.set_id;
$$;
