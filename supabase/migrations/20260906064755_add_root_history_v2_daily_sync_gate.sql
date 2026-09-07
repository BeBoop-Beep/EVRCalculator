create table if not exists public.price_storage_v2_root_history_sync_state (
    market_date date primary key,
    status text not null check(status in ('complete','skipped','failed')),
    source_completed_set_count integer not null default 0,
    source_latest_completed_at timestamptz,
    shadow_completed_set_count integer not null default 0,
    synced_row_count integer not null default 0,
    completed_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now()
);
alter table public.price_storage_v2_root_history_sync_state enable row level security;
revoke all on public.price_storage_v2_root_history_sync_state from public,anon,authenticated;
grant all on public.price_storage_v2_root_history_sync_state to postgres,service_role;

create or replace function public.sync_price_storage_v2_root_history_latest()
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
    v_date date;
    v_source_count integer:=0;
    v_source_latest timestamptz;
    v_shadow_count integer:=0;
    v_missing_shadow integer:=0;
    v_existing public.price_storage_v2_root_history_sync_state%rowtype;
    v_rows integer:=0;
begin
    select max(q.market_date) into v_date
    from public.pokemon_market_date_quality q
    where q.tcg='pokemon' and q.status in ('READY','LEGACY_VERIFIED');
    if v_date is null then
      return jsonb_build_object('status','skipped','reason','no_approved_market_date');
    end if;

    select count(distinct j.set_id)::integer,max(j.completed_at)
    into v_source_count,v_source_latest
    from public.scrape_jobs j
    where j.market_date=v_date and j.status='completed';

    select count(distinct q.set_id)::integer
    into v_shadow_count
    from public.price_storage_v2_shadow_queue q
    join public.scrape_jobs j on j.set_id=q.set_id and j.market_date=q.market_date and j.status='completed'
    where q.market_date=v_date and q.status='complete';

    select count(*)::integer
    into v_missing_shadow
    from public.scrape_jobs j
    where j.market_date=v_date and j.status='completed'
      and not exists (
        select 1 from public.price_storage_v2_shadow_queue q
        where q.set_id=j.set_id and q.market_date=j.market_date and q.status='complete'
      );

    if v_source_count=0 or v_missing_shadow>0 or v_shadow_count<>v_source_count then
      insert into public.price_storage_v2_root_history_sync_state(
        market_date,status,source_completed_set_count,source_latest_completed_at,shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at
      ) values(
        v_date,'skipped',v_source_count,v_source_latest,v_shadow_count,0,now(),
        format('waiting_for_v2_shadow: source_completed=%s shadow_completed=%s missing=%s',v_source_count,v_shadow_count,v_missing_shadow),now()
      )
      on conflict(market_date) do update set
        status=excluded.status,source_completed_set_count=excluded.source_completed_set_count,
        source_latest_completed_at=excluded.source_latest_completed_at,shadow_completed_set_count=excluded.shadow_completed_set_count,
        synced_row_count=excluded.synced_row_count,completed_at=excluded.completed_at,last_error=excluded.last_error,updated_at=excluded.updated_at;
      return jsonb_build_object('status','skipped','market_date',v_date,'source_completed',v_source_count,'shadow_completed',v_shadow_count,'missing_shadow',v_missing_shadow);
    end if;

    select * into v_existing
    from public.price_storage_v2_root_history_sync_state s
    where s.market_date=v_date;

    if found and v_existing.status='complete'
       and v_existing.source_completed_set_count=v_source_count
       and v_existing.shadow_completed_set_count=v_shadow_count
       and v_existing.source_latest_completed_at is not distinct from v_source_latest then
      return jsonb_build_object('status','noop','market_date',v_date,'synced_rows',v_existing.synced_row_count);
    end if;

    delete from public.pokemon_market_root_set_value_daily_history_v2_shadow h where h.market_date=v_date;

    insert into public.pokemon_market_root_set_value_daily_history_v2_shadow(
      set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,coverage_pct,certified_on_date,source,updated_at
    )
    select v.set_id,v.market_scope,v_date,v.set_value,v.expected_card_count,v.priced_card_count,v.coverage_pct,
           v.publishable_100pct,'root_latest_v2_snapshot'::text,now()
    from public.pokemon_market_root_set_value_latest_v1 v;
    get diagnostics v_rows=row_count;

    insert into public.price_storage_v2_root_history_sync_state(
      market_date,status,source_completed_set_count,source_latest_completed_at,shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at
    ) values(v_date,'complete',v_source_count,v_source_latest,v_shadow_count,v_rows,now(),null,now())
    on conflict(market_date) do update set
      status=excluded.status,source_completed_set_count=excluded.source_completed_set_count,
      source_latest_completed_at=excluded.source_latest_completed_at,shadow_completed_set_count=excluded.shadow_completed_set_count,
      synced_row_count=excluded.synced_row_count,completed_at=excluded.completed_at,last_error=null,updated_at=excluded.updated_at;

    return jsonb_build_object('status','complete','market_date',v_date,'source_completed',v_source_count,'shadow_completed',v_shadow_count,'synced_rows',v_rows);
exception when others then
    if v_date is not null then
      insert into public.price_storage_v2_root_history_sync_state(market_date,status,source_completed_set_count,source_latest_completed_at,shadow_completed_set_count,synced_row_count,completed_at,last_error,updated_at)
      values(v_date,'failed',v_source_count,v_source_latest,v_shadow_count,0,now(),left(SQLERRM,2000),now())
      on conflict(market_date) do update set status='failed',last_error=excluded.last_error,completed_at=excluded.completed_at,updated_at=excluded.updated_at;
    end if;
    raise;
end;
$$;
revoke all on function public.sync_price_storage_v2_root_history_latest() from public,anon,authenticated;
grant execute on function public.sync_price_storage_v2_root_history_latest() to postgres,service_role;