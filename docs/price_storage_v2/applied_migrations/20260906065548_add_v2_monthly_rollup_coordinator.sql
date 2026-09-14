create table if not exists public.price_storage_v2_monthly_rollup_publication_state (
    rollup_month date primary key,
    status text not null check(status in ('pending','complete','failed')),
    expected_set_jobs integer not null default 0,
    completed_set_jobs integer not null default 0,
    failed_set_jobs integer not null default 0,
    published_rows integer not null default 0,
    published_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now()
);
alter table public.price_storage_v2_monthly_rollup_publication_state enable row level security;
revoke all on public.price_storage_v2_monthly_rollup_publication_state from public,anon,authenticated;
grant all on public.price_storage_v2_monthly_rollup_publication_state to postgres,service_role;

create or replace function public.enqueue_price_storage_v2_monthly_rollup_month(p_month date)
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
  v_month date:=date_trunc('month',p_month::timestamp)::date;
  v_rows integer:=0;
begin
  insert into public.price_storage_v2_monthly_rollup_backfill_sets(set_id,rollup_month)
  select b.set_id,v_month
  from public.price_storage_v2_backfill_sets b
  where b.status='complete'
  on conflict(set_id,rollup_month) do nothing;
  get diagnostics v_rows=row_count;
  return jsonb_build_object('rollup_month',v_month,'enqueued',v_rows);
end;
$$;
revoke all on function public.enqueue_price_storage_v2_monthly_rollup_month(date) from public,anon,authenticated;
grant execute on function public.enqueue_price_storage_v2_monthly_rollup_month(date) to postgres,service_role;

create or replace function public.sync_price_storage_v2_monthly_rollup_month(p_month date,p_process_limit integer default 10,p_publish boolean default true)
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
  v_month date:=date_trunc('month',p_month::timestamp)::date;
  v_enqueue jsonb;
  v_process jsonb;
  v_expected integer:=0;
  v_complete integer:=0;
  v_failed integer:=0;
  v_published integer:=0;
  v_mismatch bigint:=0;
  v_state public.price_storage_v2_monthly_rollup_publication_state%rowtype;
begin
  if p_process_limit is null or p_process_limit<1 or p_process_limit>10 then raise exception 'p_process_limit must be between 1 and 10'; end if;

  select * into v_state from public.price_storage_v2_monthly_rollup_publication_state s where s.rollup_month=v_month;
  if found and v_state.status='complete' and p_publish then
    return jsonb_build_object('status','noop','rollup_month',v_month,'published_rows',v_state.published_rows);
  end if;

  v_enqueue:=public.enqueue_price_storage_v2_monthly_rollup_month(v_month);
  v_process:=public.process_price_storage_v2_monthly_rollup_backfill_sets(p_process_limit);

  select count(*)::integer,
         count(*) filter(where q.status='complete')::integer,
         count(*) filter(where q.status='failed')::integer
  into v_expected,v_complete,v_failed
  from public.price_storage_v2_monthly_rollup_backfill_sets q
  where q.rollup_month=v_month;

  if v_failed>0 then
    insert into public.price_storage_v2_monthly_rollup_publication_state(rollup_month,status,expected_set_jobs,completed_set_jobs,failed_set_jobs,published_rows,published_at,last_error,updated_at)
    values(v_month,'failed',v_expected,v_complete,v_failed,0,now(),format('V2 monthly rollup has %s failed set jobs',v_failed),now())
    on conflict(rollup_month) do update set status='failed',expected_set_jobs=excluded.expected_set_jobs,completed_set_jobs=excluded.completed_set_jobs,failed_set_jobs=excluded.failed_set_jobs,last_error=excluded.last_error,updated_at=excluded.updated_at;
    return jsonb_build_object('status','failed','rollup_month',v_month,'expected',v_expected,'complete',v_complete,'failed',v_failed,'processing',v_process);
  end if;

  if v_expected=0 or v_complete<>v_expected then
    insert into public.price_storage_v2_monthly_rollup_publication_state(rollup_month,status,expected_set_jobs,completed_set_jobs,failed_set_jobs,published_rows,published_at,last_error,updated_at)
    values(v_month,'pending',v_expected,v_complete,v_failed,0,null,null,now())
    on conflict(rollup_month) do update set status='pending',expected_set_jobs=excluded.expected_set_jobs,completed_set_jobs=excluded.completed_set_jobs,failed_set_jobs=excluded.failed_set_jobs,last_error=null,updated_at=excluded.updated_at;
    return jsonb_build_object('status','pending','rollup_month',v_month,'expected',v_expected,'complete',v_complete,'failed',v_failed,'enqueue',v_enqueue,'processing',v_process);
  end if;

  if not p_publish then
    return jsonb_build_object('status','ready','rollup_month',v_month,'expected',v_expected,'complete',v_complete,'failed',v_failed);
  end if;

  insert into public.card_variant_price_monthly_rollups(
    card_variant_id,condition_id,source,currency,rollup_month,
    open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,
    avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at,updated_at
  )
  select s.card_variant_id,s.condition_id,s.source,s.currency,s.rollup_month,
         s.open_market_price,s.close_market_price,s.avg_market_price,s.min_market_price,s.max_market_price,
         s.avg_high_price,s.avg_low_price,s.observation_count,s.first_captured_at,s.last_captured_at,now()
  from public.card_variant_price_monthly_rollups_v2_shadow s
  where s.rollup_month=v_month
  on conflict(card_variant_id,condition_id,source,rollup_month) do update set
    currency=excluded.currency,
    open_market_price=excluded.open_market_price,
    close_market_price=excluded.close_market_price,
    avg_market_price=excluded.avg_market_price,
    min_market_price=excluded.min_market_price,
    max_market_price=excluded.max_market_price,
    avg_high_price=excluded.avg_high_price,
    avg_low_price=excluded.avg_low_price,
    observation_count=excluded.observation_count,
    first_captured_at=excluded.first_captured_at,
    last_captured_at=excluded.last_captured_at,
    updated_at=excluded.updated_at;

  delete from public.card_variant_price_monthly_rollups p
  where p.rollup_month=v_month
    and not exists(
      select 1 from public.card_variant_price_monthly_rollups_v2_shadow s
      where s.rollup_month=v_month and s.card_variant_id=p.card_variant_id and s.condition_id=p.condition_id and s.source=p.source
    );

  select count(*)::integer into v_published from public.card_variant_price_monthly_rollups where rollup_month=v_month;

  with prod as materialized (
    select card_variant_id,condition_id,source,currency,rollup_month,open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at
    from public.card_variant_price_monthly_rollups where rollup_month=v_month
  ), shadow as materialized (
    select card_variant_id,condition_id,source,currency,rollup_month,open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at
    from public.card_variant_price_monthly_rollups_v2_shadow where rollup_month=v_month
  ), keys as (
    select card_variant_id,condition_id,source from prod union select card_variant_id,condition_id,source from shadow
  )
  select count(*) into v_mismatch
  from keys k left join prod p using(card_variant_id,condition_id,source) left join shadow s using(card_variant_id,condition_id,source)
  where p.card_variant_id is null or s.card_variant_id is null or
        p.currency is distinct from s.currency or p.open_market_price is distinct from s.open_market_price or p.close_market_price is distinct from s.close_market_price or
        p.avg_market_price is distinct from s.avg_market_price or p.min_market_price is distinct from s.min_market_price or p.max_market_price is distinct from s.max_market_price or
        p.avg_high_price is distinct from s.avg_high_price or p.avg_low_price is distinct from s.avg_low_price or p.observation_count is distinct from s.observation_count or
        p.first_captured_at is distinct from s.first_captured_at or p.last_captured_at is distinct from s.last_captured_at;

  if v_mismatch<>0 then raise exception 'V2 monthly publication parity failure month %, mismatch rows %',v_month,v_mismatch; end if;

  insert into public.price_storage_v2_monthly_rollup_publication_state(rollup_month,status,expected_set_jobs,completed_set_jobs,failed_set_jobs,published_rows,published_at,last_error,updated_at)
  values(v_month,'complete',v_expected,v_complete,v_failed,v_published,now(),null,now())
  on conflict(rollup_month) do update set status='complete',expected_set_jobs=excluded.expected_set_jobs,completed_set_jobs=excluded.completed_set_jobs,failed_set_jobs=excluded.failed_set_jobs,published_rows=excluded.published_rows,published_at=excluded.published_at,last_error=null,updated_at=excluded.updated_at;

  return jsonb_build_object('status','complete','rollup_month',v_month,'expected',v_expected,'complete_jobs',v_complete,'published_rows',v_published,'mismatches',v_mismatch);
exception when others then
  insert into public.price_storage_v2_monthly_rollup_publication_state(rollup_month,status,expected_set_jobs,completed_set_jobs,failed_set_jobs,published_rows,published_at,last_error,updated_at)
  values(v_month,'failed',v_expected,v_complete,v_failed,0,now(),left(SQLERRM,2000),now())
  on conflict(rollup_month) do update set status='failed',last_error=excluded.last_error,updated_at=excluded.updated_at;
  raise;
end;
$$;
revoke all on function public.sync_price_storage_v2_monthly_rollup_month(date,integer,boolean) from public,anon,authenticated;
grant execute on function public.sync_price_storage_v2_monthly_rollup_month(date,integer,boolean) to postgres,service_role;

create or replace function public.sync_price_storage_v2_previous_monthly_rollup()
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
  v_month date:=(date_trunc('month',timezone('America/Phoenix',now()))-interval '1 month')::date;
begin
  return public.sync_price_storage_v2_monthly_rollup_month(v_month,10,true);
end;
$$;
revoke all on function public.sync_price_storage_v2_previous_monthly_rollup() from public,anon,authenticated;
grant execute on function public.sync_price_storage_v2_previous_monthly_rollup() to postgres,service_role;