create or replace function public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(
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
      and exists(select 1 from public.pokemon_market_root_set_value_latest_v1 v where v.set_id=s.id and v.market_scope='standard')
), members as (
    select r.root_set_id,r.root_set_name,r.root_set_id member_set_id from root r
    union all
    select r.root_set_id,r.root_set_name,c.id
    from root r join public.sets c on c.parent_opening_set_id=r.root_set_id and c.counts_toward_parent_set_value=true
), near_mint as (
    select id from public.conditions where name='Near Mint' and abbreviation='NM' order by id limit 1
), base_cards as materialized (
    select m.root_set_id,m.root_set_name,pcc.*
    from members m join public.pokemon_canonical_cards pcc on pcc.set_id=m.member_set_id
    where pcc.set_value_eligible=true
), expected as (
    select root_set_id,count(*)::integer expected_card_count from base_cards group by root_set_id
), manual_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 identity_rank
    from base_cards pcc join public.pokemon_canonical_card_legacy_identity_links link on link.canonical_card_id=pcc.id
), parent_api_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
    from base_cards pcc join public.cards c on c.set_id=pcc.set_id and c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
    from base_cards pcc join public.card_variants mv on mv.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    join public.cards c on c.id=mv.card_id and c.set_id=pcc.set_id
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
), name_number_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,2 identity_rank
    from base_cards pcc join public.cards c on c.set_id=pcc.set_id
      and lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
      and regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') in (
        regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
        regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
      )
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
      and not exists(select 1 from variant_api_identity v where v.canonical_card_id=pcc.id)
), resolved as (
    select * from manual_identity union all select * from parent_api_identity union all select * from variant_api_identity union all select * from name_number_identity
), variants as materialized (
    select distinct r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,cv.id card_variant_id,cv.printing_type,cv.special_type
    from resolved r join public.card_variants cv on cv.card_id=r.legacy_card_id
), event_intervals as materialized (
    select e.card_variant_id,e.market_price,e.effective_date valid_from,
           lead(e.effective_date) over(partition by e.card_variant_id order by e.effective_date) valid_to
    from public.card_variant_price_events_v2 e
    join variants v on v.card_variant_id=e.card_variant_id
    cross join near_mint nm
    where e.condition_id=nm.id and e.source='TCGPlayer' and e.currency='USD'
), dates as materialized (
    select q.market_date
    from public.pokemon_market_date_quality q
    where q.tcg='pokemon' and q.status in ('READY','LEGACY_VERIFIED') and q.market_date between p_start_date and p_end_date
), candidate_daily as (
    select d.market_date,v.canonical_card_id,v.set_id,v.rarity,v.identity_rank,v.card_variant_id,v.printing_type,v.special_type,
           ei.market_price,obs.latest_observed_date,
           row_number() over(partition by d.market_date,v.canonical_card_id order by
              v.identity_rank,
              obs.latest_observed_date desc nulls last,
              case when v.special_type is null then 0 else 1 end,
              case
                when v.rarity in ('Common','Uncommon') and v.printing_type='non-holo' then 0
                when v.rarity in ('Common','Uncommon') and v.printing_type='holo' then 1
                when v.rarity in ('Common','Uncommon') and v.printing_type='reverse-holo' and v.special_type is null then 2
                when v.printing_type='holo' then 0
                when v.printing_type='non-holo' then 1
                when v.printing_type='reverse-holo' and v.special_type is null then 2
                else 9 end,
              v.card_variant_id
           ) rn
    from dates d
    join variants v on true
    join event_intervals ei on ei.card_variant_id=v.card_variant_id
      and ei.valid_from<=d.market_date
      and (ei.valid_to is null or d.market_date<ei.valid_to)
      and ei.market_price>0
    cross join near_mint nm
    left join lateral (
      select max(least(r.observed_through,d.market_date)) latest_observed_date
      from public.card_variant_price_observation_ranges_v2 r
      where r.card_variant_id=v.card_variant_id
        and r.condition_id=nm.id
        and r.source='TCGPlayer'
        and r.currency='USD'
        and r.observed_from<=d.market_date
    ) obs on true
), selected as (
    select * from candidate_daily where rn=1
), aggregated as (
    select r.root_set_id set_id,r.root_set_name set_name,'standard'::text market_scope,s.market_date,
           round(sum(s.market_price),2) set_value,
           max(e.expected_card_count)::integer expected_card_count,
           count(s.market_price)::integer priced_card_count,
           round(count(s.market_price)::numeric/nullif(max(e.expected_card_count),0)::numeric*100,2) coverage_pct,
           (max(e.expected_card_count)>0 and count(s.market_price)=max(e.expected_card_count)) certified_on_date,
           'canonical_price_events_v2_root_standard_fast_v1'::text source
    from root r join expected e on e.root_set_id=r.root_set_id join selected s on true
    group by r.root_set_id,r.root_set_name,s.market_date
)
select * from aggregated order by market_date;
$$;
revoke all on function public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(uuid,date,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(uuid,date,date) to postgres,service_role;