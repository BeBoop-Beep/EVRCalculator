-- Incremental rarity coverage authority for Market Explorer.
-- Avoids rescanning the full card x date history whenever the rarity registry
-- is refreshed. Backfill is deliberately bounded to <=31 calendar days/call.

begin;

create table if not exists public.pokemon_market_explorer_rarity_daily_coverage_v1 (
  market_date date not null,
  rarity_key text not null,
  priced_card_count integer not null check (priced_card_count >= 0),
  represented_set_count integer not null check (represented_set_count >= 0),
  image_count integer not null check (image_count >= 0),
  refreshed_at timestamptz not null default clock_timestamp(),
  primary key (market_date,rarity_key)
);

create index if not exists pokemon_market_explorer_rarity_daily_coverage_v1_key_date_idx
  on public.pokemon_market_explorer_rarity_daily_coverage_v1(
    rarity_key,market_date
  )
  include (priced_card_count,represented_set_count,image_count);

create index if not exists pokemon_market_explorer_card_metadata_filter_rarity_v1
  on public.pokemon_market_explorer_card_current_metadata(
    filter_rarity_key,card_variant_id,set_id
  )
  where filter_rarity_key is not null;

alter table public.pokemon_market_explorer_rarity_daily_coverage_v1 enable row level security;
revoke all on public.pokemon_market_explorer_rarity_daily_coverage_v1
from public,anon,authenticated;
grant select,insert,update,delete
on public.pokemon_market_explorer_rarity_daily_coverage_v1
to service_role;

create or replace function public.refresh_pokemon_market_explorer_rarity_daily_coverage_v1(
  p_from date,
  p_through date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '15s'
set lock_timeout = '2s'
set jit = 'off'
as $function$
declare
  v_rows integer;
  v_dates integer;
begin
  if p_from is null or p_through is null or p_from>p_through then
    raise exception 'RARITY_COVERAGE_INVALID_RANGE';
  end if;
  if p_through-p_from>30 then
    raise exception 'RARITY_COVERAGE_RANGE_TOO_LARGE';
  end if;

  delete from public.pokemon_market_explorer_rarity_daily_coverage_v1
  where market_date between p_from and p_through;

  insert into public.pokemon_market_explorer_rarity_daily_coverage_v1(
    market_date,rarity_key,priced_card_count,represented_set_count,image_count,refreshed_at
  )
  select
    d.market_date,
    m.filter_rarity_key,
    count(*)::integer,
    count(distinct m.set_id)::integer,
    count(*) filter (
      where coalesce(
        cv.image_small_url,cc.image_small_url,
        cv.image_large_url,cc.image_large_url,m.image_url
      ) is not null
    )::integer,
    clock_timestamp()
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d
  join public.pokemon_market_explorer_card_current_metadata m
    on m.card_variant_id=d.card_variant_id
  join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=d.market_date
   and q.status in ('READY','LEGACY_VERIFIED')
  left join public.card_variants cv on cv.id=m.card_variant_id
  left join public.pokemon_canonical_cards cc on cc.id=m.canonical_card_id
  where d.market_date between p_from and p_through
    and d.market_price>0
    and m.filter_rarity_key is not null
  group by d.market_date,m.filter_rarity_key;

  get diagnostics v_rows=row_count;

  select count(distinct market_date)::integer
  into v_dates
  from public.pokemon_market_explorer_rarity_daily_coverage_v1
  where market_date between p_from and p_through;

  return jsonb_build_object(
    'from',p_from,'through',p_through,
    'summaryRows',v_rows,'acceptedDatesMaterialized',v_dates
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_rarity_daily_coverage_v1(date,date)
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_rarity_daily_coverage_v1(date,date)
to service_role;

create or replace function public.refresh_pokemon_market_explorer_rarity_registry_v1(
  p_market_date date default null
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '10s'
set lock_timeout = '2s'
set jit = 'off'
as $function$
declare
  v_market_date date;
  v_rows integer;
begin
  select coalesce(p_market_date,max(c.market_date))
  into v_market_date
  from public.pokemon_market_explorer_rarity_daily_coverage_v1 c;

  if v_market_date is null then
    raise exception 'RARITY_AUDIT_NO_MATERIALIZED_MARKET_DATE';
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    where c.market_date=v_market_date
  ) then
    raise exception 'RARITY_AUDIT_MARKET_DATE_NOT_MATERIALIZED';
  end if;

  with current_stats as materialized (
    select
      c.rarity_key,
      c.priced_card_count as card_count,
      c.represented_set_count as set_count,
      c.image_count
    from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    where c.market_date=v_market_date
  ),
  history_stats as materialized (
    select
      c.rarity_key,
      min(c.market_date) as history_start,
      max(c.market_date) as history_end,
      count(distinct c.market_date)::integer as history_points
    from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    where c.market_date<=v_market_date
    group by c.rarity_key
  ),
  prepared as (
    select
      coalesce(
        nullif(d.metadata->>'rarityKey',''),
        nullif(d.metadata->>'segmentKey',''),
        nullif(d.metadata->>'segmentId',''),
        nullif(d.metadata->>'filterRarityKey','')
      ) as rarity_key,
      min(d.market_key) as market_key
    from public.pokemon_market_explorer_prepared_directory_v1 d
    where d.asset='cards'
      and d.market_type='prepared_rarity'
    group by coalesce(
      nullif(d.metadata->>'rarityKey',''),
      nullif(d.metadata->>'segmentKey',''),
      nullif(d.metadata->>'segmentId',''),
      nullif(d.metadata->>'filterRarityKey','')
    )
  )
  update public.pokemon_market_explorer_rarity_registry_v1 r
  set
    current_market_date=v_market_date,
    current_priced_card_count=coalesce(c.card_count,0),
    represented_set_count=coalesce(c.set_count,0),
    image_count=coalesce(c.image_count,0),
    history_start_date=h.history_start,
    history_end_date=h.history_end,
    history_point_count=coalesce(h.history_points,0),
    prepared_market_key=p.market_key,
    eligibility_state=case
      when p.market_key is not null then 'PREPARED'
      when coalesce(c.card_count,0)<25 or coalesce(c.set_count,0)<3
        then 'INSUFFICIENT_COHORT'
      when coalesce(h.history_points,0)<2 or h.history_end is distinct from v_market_date
        then 'INSUFFICIENT_HISTORY'
      when coalesce(c.card_count,0)>0
        then 'CUSTOM_BUILD_AVAILABLE'
      else 'UNAVAILABLE'
    end,
    reason=case
      when p.market_key is not null then 'Maintained prepared market is published'
      when coalesce(c.card_count,0)<25 or coalesce(c.set_count,0)<3
        then format(
          'Below 25-card / 3-set cross-market gate (%s cards, %s sets)',
          coalesce(c.card_count,0),coalesce(c.set_count,0)
        )
      when coalesce(h.history_points,0)<2
        then 'Fewer than two materialized accepted history dates'
      when h.history_end is distinct from v_market_date
        then 'Materialized history does not reach the audited market date'
      when coalesce(c.card_count,0)>0
        then 'Cohort is eligible for a prepared candidate; candidate publication is separate'
      else 'No current positively priced constituents'
    end,
    audited_at=clock_timestamp()
  from current_stats c
  full join history_stats h using (rarity_key)
  full join prepared p using (rarity_key)
  where r.rarity_key=coalesce(c.rarity_key,h.rarity_key,p.rarity_key);

  get diagnostics v_rows=row_count;

  update public.pokemon_market_explorer_rarity_registry_v1 r
  set current_market_date=v_market_date,
      current_priced_card_count=0,
      represented_set_count=0,
      image_count=0,
      history_start_date=null,
      history_end_date=null,
      history_point_count=0,
      prepared_market_key=null,
      eligibility_state='UNAVAILABLE',
      reason='No current positively priced constituents',
      audited_at=clock_timestamp()
  where r.prepared_market_key is null
    and not exists (
      select 1
      from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
      where c.market_date=v_market_date
        and c.rarity_key=r.rarity_key
    );

  return jsonb_build_object(
    'marketDate',v_market_date,
    'taxonomyVersion','pokemon-card-rarity-filter-taxonomy-v1',
    'registryRows',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1),
    'updated',v_rows,
    'prepared',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1 where eligibility_state='PREPARED'),
    'preparedCandidates',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1 where eligibility_state='CUSTOM_BUILD_AVAILABLE')
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_rarity_registry_v1(date)
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_rarity_registry_v1(date)
to service_role;

commit;
