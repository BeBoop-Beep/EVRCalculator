create or replace function public.get_pokemon_market_root_set_standard_daily_history_v2_shadow(
    p_root_set_id uuid,
    p_start_date date,
    p_end_date date
)
returns table(
    set_id uuid,
    set_name text,
    market_scope text,
    market_date date,
    set_value numeric,
    expected_card_count integer,
    priced_card_count integer,
    coverage_pct numeric,
    certified_on_date boolean,
    source text
)
language sql
stable
set search_path to ''
set "TimeZone" to 'America/Phoenix'
as $$
with root as (
    select s.id root_set_id,s.name root_set_name
    from public.sets s
    where s.id=p_root_set_id
      and s.parent_opening_set_id is null
      and coalesce(s.catalog_only,false)=false
      and exists(
        select 1 from public.pokemon_market_root_set_value_latest_v1 v
        where v.set_id=s.id and v.market_scope='standard'
      )
), members as (
    select r.root_set_id,r.root_set_name,r.root_set_id member_set_id
    from root r
    union all
    select r.root_set_id,r.root_set_name,c.id
    from root r
    join public.sets c
      on c.parent_opening_set_id=r.root_set_id
     and c.counts_toward_parent_set_value=true
), expected as (
    select m.root_set_id,count(*)::integer expected_card_count
    from members m
    join public.pokemon_canonical_cards pcc
      on pcc.set_id=m.member_set_id
     and pcc.set_value_eligible=true
    group by m.root_set_id
), dates as (
    select q.market_date
    from public.pokemon_market_date_quality q
    where q.tcg='pokemon'
      and q.status in ('READY','LEGACY_VERIFIED')
      and q.market_date between p_start_date and p_end_date
), priced as (
    select m.root_set_id,m.root_set_name,d.market_date,p.canonical_card_id,p.market_price
    from members m
    cross join dates d
    cross join lateral public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(m.member_set_id,d.market_date) p
), aggregated as (
    select p.root_set_id as set_id,
           max(p.root_set_name)::text as set_name,
           'standard'::text as market_scope,
           p.market_date,
           round(sum(p.market_price),2) as set_value,
           max(e.expected_card_count)::integer as expected_card_count,
           count(p.market_price)::integer as priced_card_count,
           round(count(p.market_price)::numeric/nullif(max(e.expected_card_count),0)::numeric*100,2) as coverage_pct,
           (max(e.expected_card_count)>0 and count(p.market_price)=max(e.expected_card_count)) as certified_on_date,
           'canonical_price_events_v2_root_standard_v1'::text as source
    from priced p
    join expected e on e.root_set_id=p.root_set_id
    group by p.root_set_id,p.market_date
)
select * from aggregated
order by market_date;
$$;
revoke all on function public.get_pokemon_market_root_set_standard_daily_history_v2_shadow(uuid,date,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_standard_daily_history_v2_shadow(uuid,date,date) to postgres,service_role;