create table if not exists public.pokemon_market_root_set_value_daily_history_v2_shadow (
    set_id uuid not null references public.sets(id) on delete cascade,
    market_scope text not null,
    market_date date not null,
    set_value numeric,
    expected_card_count integer not null default 0,
    priced_card_count integer not null default 0,
    coverage_pct numeric,
    certified_on_date boolean not null default false,
    source text not null,
    updated_at timestamptz not null default now(),
    primary key(set_id,market_scope,market_date)
);
alter table public.pokemon_market_root_set_value_daily_history_v2_shadow enable row level security;
revoke all on public.pokemon_market_root_set_value_daily_history_v2_shadow from public,anon,authenticated;
grant all on public.pokemon_market_root_set_value_daily_history_v2_shadow to postgres,service_role;
create index if not exists idx_root_set_value_daily_history_v2_date on public.pokemon_market_root_set_value_daily_history_v2_shadow(market_date,set_id,market_scope);

create table if not exists public.price_storage_v2_root_history_backfill_sets (
    set_id uuid primary key references public.sets(id) on delete cascade,
    status text not null default 'pending' check(status in ('pending','processing','complete','failed')),
    attempts integer not null default 0,
    row_count bigint,
    started_at timestamptz,
    completed_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now()
);
alter table public.price_storage_v2_root_history_backfill_sets enable row level security;
revoke all on public.price_storage_v2_root_history_backfill_sets from public,anon,authenticated;
grant all on public.price_storage_v2_root_history_backfill_sets to postgres,service_role;

insert into public.price_storage_v2_root_history_backfill_sets(set_id)
select distinct v.set_id from public.pokemon_market_root_set_value_latest_v1 v
on conflict(set_id) do nothing;

create or replace function public.process_price_storage_v2_root_history_backfill_sets(p_limit integer default 5)
returns jsonb
language plpgsql
set search_path to ''
as $$
declare
    v_job record;
    v_first date;
    v_last date;
    v_rows bigint;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
begin
    if p_limit is null or p_limit<1 or p_limit>10 then raise exception 'p_limit must be between 1 and 10'; end if;
    select min(market_date),max(market_date) into v_first,v_last
    from public.pokemon_market_date_quality
    where tcg='pokemon' and status in ('READY','LEGACY_VERIFIED');
    if v_first is null or v_last is null then raise exception 'No approved Pokemon market dates'; end if;

    for v_job in
      select q.set_id from public.price_storage_v2_root_history_backfill_sets q
      where q.status in ('pending','failed') and q.attempts<5
      order by q.set_id for update skip locked limit p_limit
    loop
      v_processed:=v_processed+1;
      update public.price_storage_v2_root_history_backfill_sets
      set status='processing',attempts=attempts+1,started_at=now(),completed_at=null,last_error=null,updated_at=now()
      where set_id=v_job.set_id;
      begin
        delete from public.pokemon_market_root_set_value_daily_history_v2_shadow where set_id=v_job.set_id;

        if exists(select 1 from public.pokemon_market_root_set_value_latest_v1 where set_id=v_job.set_id and market_scope='standard') then
          insert into public.pokemon_market_root_set_value_daily_history_v2_shadow(
            set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,coverage_pct,certified_on_date,source,updated_at
          )
          select h.set_id,h.market_scope,h.market_date,h.set_value,h.expected_card_count,h.priced_card_count,h.coverage_pct,h.certified_on_date,h.source,now()
          from public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(v_job.set_id,v_first,v_last) h;
        else
          insert into public.pokemon_market_root_set_value_daily_history_v2_shadow(
            set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,coverage_pct,certified_on_date,source,updated_at
          )
          select h.set_id,h.market_scope,h.market_date,h.set_value,h.expected_card_count,h.priced_card_count,h.coverage_pct,h.certified_on_date,h.source,now()
          from public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(v_job.set_id,v_first,v_last) h
          where h.market_scope<>'standard';
        end if;

        insert into public.pokemon_market_root_set_value_daily_history_v2_shadow(
          set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,coverage_pct,certified_on_date,source,updated_at
        )
        select v.set_id,v.market_scope,v_last,v.set_value,v.expected_card_count,v.priced_card_count,v.coverage_pct,v.publishable_100pct,
               'root_latest_v2_snapshot'::text,now()
        from public.pokemon_market_root_set_value_latest_v1 v
        where v.set_id=v_job.set_id
        on conflict(set_id,market_scope,market_date) do update set
          set_value=excluded.set_value,expected_card_count=excluded.expected_card_count,priced_card_count=excluded.priced_card_count,
          coverage_pct=excluded.coverage_pct,certified_on_date=excluded.certified_on_date,source=excluded.source,updated_at=excluded.updated_at;

        select count(*) into v_rows from public.pokemon_market_root_set_value_daily_history_v2_shadow where set_id=v_job.set_id;
        update public.price_storage_v2_root_history_backfill_sets set status='complete',row_count=v_rows,completed_at=now(),last_error=null,updated_at=now() where set_id=v_job.set_id;
        v_completed:=v_completed+1;
      exception when others then
        update public.price_storage_v2_root_history_backfill_sets set status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now() where set_id=v_job.set_id;
        v_failed:=v_failed+1;
      end;
    end loop;
    return jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed,'first_date',v_first,'last_date',v_last);
end;
$$;
revoke all on function public.process_price_storage_v2_root_history_backfill_sets(integer) from public,anon,authenticated;
grant execute on function public.process_price_storage_v2_root_history_backfill_sets(integer) to postgres,service_role;