create or replace function public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(
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
with near_mint as (
    select c.id
    from public.conditions c
    where lower(c.name)='near mint'
    order by c.id
    limit 1
),
root as (
    select s.id as root_set_id,s.name as root_set_name
    from public.sets s
    where s.id=p_root_set_id
      and s.parent_opening_set_id is null
      and s.catalog_only=false
),
members as (
    select r.root_set_id,r.root_set_name,r.root_set_id as member_set_id
    from root r
    union all
    select r.root_set_id,r.root_set_name,child.id
    from root r
    join public.sets child
      on child.parent_opening_set_id=r.root_set_id
     and child.counts_toward_parent_set_value=true
),
member_counts as (
    select root_set_id,count(*)::integer as expected_member_count
    from members
    group by root_set_id
),
scopes as (
    select distinct latest.set_id,latest.set_name,latest.market_scope
    from public.pokemon_market_root_set_value_latest_v1 latest
    join root r on r.root_set_id=latest.set_id
),
standard_history as (
    select r.root_set_id as set_id,
           r.root_set_name as set_name,
           'standard'::text as market_scope,
           h.snapshot_date as market_date,
           round(sum(h.set_value),2) as set_value,
           sum(h.total_card_count)::integer as expected_card_count,
           sum(h.priced_card_count)::integer as priced_card_count,
           round(sum(h.priced_card_count)::numeric/nullif(sum(h.total_card_count),0)::numeric*100,2) as coverage_pct,
           (
             count(distinct h.set_id)=max(mc.expected_member_count)
             and sum(h.total_card_count)>0
             and sum(h.priced_card_count)=sum(h.total_card_count)
           ) as certified_on_date,
           'member_standard_history_sum_v1'::text as source
    from root r
    join scopes scope on scope.set_id=r.root_set_id and scope.market_scope='standard'
    join members m on m.root_set_id=r.root_set_id
    join member_counts mc on mc.root_set_id=r.root_set_id
    join public.pokemon_set_value_daily_history h
      on h.set_id=m.member_set_id
     and h.value_scope='standard'
     and h.snapshot_date between p_start_date and p_end_date
    group by r.root_set_id,r.root_set_name,h.snapshot_date
),
eligible_cards as (
    select m.root_set_id,m.root_set_name,m.member_set_id,
           pcc.id as canonical_card_id,pcc.rarity
    from members m
    join public.pokemon_canonical_cards pcc
      on pcc.set_id=m.member_set_id
     and pcc.set_value_eligible=true
),
expected_cards as (
    select root_set_id,count(distinct canonical_card_id)::integer as expected_card_count
    from eligible_cards
    group by root_set_id
),
edition_scopes as (
    select s.set_id,s.set_name,s.market_scope,
           case s.market_scope
             when 'first_edition' then '1st-edition'
             when 'unlimited' then 'unlimited'
             when 'shadowless' then 'shadowless'
           end as edition
    from scopes s
    where s.market_scope in ('first_edition','unlimited','shadowless')
),
market_dates as (
    select q.market_date
    from public.pokemon_market_date_quality q
    where q.tcg='pokemon'
      and q.status in ('READY','LEGACY_VERIFIED')
      and q.market_date between p_start_date and p_end_date
),
edition_grid as (
    select es.set_id,es.set_name,es.market_scope,es.edition,d.market_date
    from edition_scopes es
    cross join market_dates d
),
edition_candidates as (
    select g.set_id,g.set_name,g.market_scope,g.market_date,
           ec.canonical_card_id,
           interval_row.card_variant_id,
           interval_row.market_price,
           obs.latest_observed_date as source_date,
           row_number() over (
             partition by g.set_id,g.market_scope,g.market_date,ec.canonical_card_id
             order by
               case meta.identity_basis
                 when 'explicit_legacy_identity_link' then 0
                 when 'parent_pokemon_tcg_api_id' then 1
                 when 'variant_pokemon_tcg_api_id' then 2
                 when 'normalized_name_number_fallback' then 3
                 else 9
               end,
               case when meta.special_type is null or meta.special_type='' then 0 else 1 end,
               case
                 when ec.rarity in ('Common','Uncommon') and meta.printing_type='non-holo' then 0
                 when ec.rarity in ('Common','Uncommon') and meta.printing_type='holo' then 1
                 when ec.rarity in ('Common','Uncommon') and meta.printing_type='reverse-holo' then 2
                 when meta.printing_type='holo' then 0
                 when meta.printing_type='non-holo' then 1
                 when meta.printing_type='reverse-holo' then 2
                 else 9
               end,
               obs.latest_observed_date desc nulls last,
               interval_row.card_variant_id
           ) as selection_rank
    from edition_grid g
    join eligible_cards ec on ec.root_set_id=g.set_id
    join public.pokemon_market_price_intervals_v2_shadow interval_row
      on interval_row.set_id=ec.member_set_id
     and interval_row.valid_from<=g.market_date
     and (interval_row.valid_to is null or g.market_date<interval_row.valid_to)
    join public.pokemon_market_explorer_card_current_metadata meta
      on meta.card_variant_id=interval_row.card_variant_id
     and meta.set_id=ec.member_set_id
     and meta.canonical_card_id=ec.canonical_card_id
     and meta.edition=g.edition
    cross join near_mint nm
    left join lateral (
      select max(least(r.observed_through,g.market_date)) as latest_observed_date
      from public.card_variant_price_observation_ranges_v2 r
      where r.card_variant_id=interval_row.card_variant_id
        and r.condition_id=nm.id
        and r.currency='USD'
        and r.observed_from<=g.market_date
    ) obs on true
),
edition_selected as (
    select * from edition_candidates where selection_rank=1
),
edition_history as (
    select g.set_id,g.set_name,g.market_scope,g.market_date,
           round(coalesce(sum(sel.market_price),0),2) as set_value,
           max(ec.expected_card_count)::integer as expected_card_count,
           count(distinct sel.canonical_card_id)::integer as priced_card_count,
           round(count(distinct sel.canonical_card_id)::numeric/nullif(max(ec.expected_card_count),0)::numeric*100,2) as coverage_pct,
           (
             max(ec.expected_card_count)>0
             and count(distinct sel.canonical_card_id)=max(ec.expected_card_count)
           ) as certified_on_date,
           'variant_interval_edition_exact_v2_shadow'::text as source
    from edition_grid g
    join expected_cards ec on ec.root_set_id=g.set_id
    left join edition_selected sel
      on sel.set_id=g.set_id
     and sel.market_scope=g.market_scope
     and sel.market_date=g.market_date
    group by g.set_id,g.set_name,g.market_scope,g.market_date
)
select * from standard_history
union all
select * from edition_history
order by market_date,market_scope;
$$;

revoke all on function public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(uuid,date,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_value_daily_history_v1_v2_shadow(uuid,date,date) to postgres,service_role;