-- Market Explorer sealed Quick markets and generation-pinned analytical screens.
-- Publication-time only. No serving pointer is changed here.

begin;

update public.pokemon_market_explorer_sealed_quick_registry_v1
set status='REJECTED',updated_at=clock_timestamp()
where quick_key in (
  'box-market','established-sealed','new-release-sealed','premium-sealed','single-pack-market'
)
  and status='PROPOSED';

insert into public.pokemon_market_explorer_sealed_quick_registry_v1(
  quick_key,label,status,definition,research_basis,approved_at,updated_at
)
values
(
 'obtainable','Obtainable','APPROVED',
 '{"marketKey":"sealed-quick:obtainable","axis":"price","minimum":null,"maximumExclusive":100,"bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical sealed price bands","contract":"price < 100"}'::jsonb,
 clock_timestamp(),clock_timestamp()
),
(
 'intermediate','Intermediate','APPROVED',
 '{"marketKey":"sealed-quick:intermediate","axis":"price","minimumInclusive":100,"maximumExclusive":500,"bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical sealed price bands","contract":"100 <= price < 500"}'::jsonb,
 clock_timestamp(),clock_timestamp()
),
(
 'premium','Premium','APPROVED',
 '{"marketKey":"sealed-quick:premium","axis":"price","minimumInclusive":500,"maximum":null,"bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical sealed price bands","contract":"price >= 500"}'::jsonb,
 clock_timestamp(),clock_timestamp()
),
(
 'new-releases','New Releases','APPROVED',
 '{"marketKey":"sealed-quick:new-releases","axis":"releaseAge","minimumDaysInclusive":0,"maximumDaysInclusive":180,"bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical release-age bands","contract":"release age <= 180 days"}'::jsonb,
 clock_timestamp(),clock_timestamp()
),
(
 'established','Established','APPROVED',
 '{"marketKey":"sealed-quick:established","axis":"releaseAge","minimumDaysExclusive":730,"maximumDaysInclusive":1825,"bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical release-age bands","contract":"730 < release age <= 1825 days"}'::jsonb,
 clock_timestamp(),clock_timestamp()
),
(
 'global-top10','Global Top 10','APPROVED',
 '{"marketKey":"sealed-quick:global-top10","axis":"rank","topN":10,"rankBy":"marketPriceDesc","membership":"dateSpecific","bulkExcluded":true,"version":"sealed-quick-v1"}'::jsonb,
 '{"source":"canonical ranked-market semantics","contract":"filter non-bulk first, then rank each date"}'::jsonb,
 clock_timestamp(),clock_timestamp()
)
on conflict(quick_key) do update
set label=excluded.label,
    status='APPROVED',
    definition=excluded.definition,
    research_basis=excluded.research_basis,
    approved_at=coalesce(public.pokemon_market_explorer_sealed_quick_registry_v1.approved_at,excluded.approved_at),
    updated_at=clock_timestamp();

create or replace function public.stage_pokemon_market_explorer_sealed_quicks_v1(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '120s'
set lock_timeout = '2s'
set work_mem = '32MB'
as $function$
declare
  v_markets integer;
  v_history integer;
  v_constituents integer;
begin
  if p_generation_id is null or p_market_date is null then
    raise exception 'SEALED_QUICK_ARGUMENTS_REQUIRED';
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_surface_generations_v2 g
    where g.generation_id=p_generation_id and g.market_date=p_market_date
  ) then
    raise exception 'SEALED_QUICK_GENERATION_MISMATCH';
  end if;

  delete from public.pokemon_market_explorer_surface_constituents_v2
  where generation_id=p_generation_id and market_key like 'sealed-quick:%';
  delete from public.pokemon_market_explorer_surface_constituent_totals_v2
  where generation_id=p_generation_id and market_key like 'sealed-quick:%';
  delete from public.pokemon_market_explorer_surface_history_v2
  where generation_id=p_generation_id and market_key like 'sealed-quick:%';
  delete from public.pokemon_market_explorer_surface_directory_v2
  where generation_id=p_generation_id and market_key like 'sealed-quick:%';

  drop table if exists pg_temp._mx_quick_dense;
  create temp table _mx_quick_dense on commit drop as
  with intervals as (
    select d.*,
      lead(d.market_date,1,p_market_date+1) over(
        partition by d.sealed_product_id order by d.market_date
      ) next_date
    from public.pokemon_market_explorer_sealed_daily_v1 d
    where d.market_date<=p_market_date
      and d.market_price>0
  )
  select
    i.sealed_product_id,
    g.day::date market_date,
    i.market_price,
    i.set_id,
    i.era_id,
    i.product_family,
    s.release_date
  from intervals i
  join public.pokemon_market_explorer_sealed_current_metadata_v1 m
    on m.sealed_product_id=i.sealed_product_id
   and m.is_bulk_container=false
  left join public.sets s on s.id=i.set_id
  cross join lateral generate_series(
    i.market_date,
    least(p_market_date,i.next_date-1),
    interval '1 day'
  ) g(day);

  create index on _mx_quick_dense(market_date,sealed_product_id);
  create index on _mx_quick_dense(market_date,market_price,sealed_product_id);
  analyze _mx_quick_dense;

  drop table if exists pg_temp._mx_quick_ranked;
  create temp table _mx_quick_ranked on commit drop as
  select d.*,
    row_number() over(
      partition by d.market_date
      order by d.market_price desc,d.sealed_product_id
    )::integer global_rank
  from _mx_quick_dense d;

  create index on _mx_quick_ranked(market_date,global_rank,sealed_product_id);
  analyze _mx_quick_ranked;

  drop table if exists pg_temp._mx_quick_members;
  create temp table _mx_quick_members on commit drop as
  select 'sealed-quick:obtainable'::text market_key,d.*
  from _mx_quick_dense d
  where d.market_price<100

  union all
  select 'sealed-quick:intermediate',d.*
  from _mx_quick_dense d
  where d.market_price>=100 and d.market_price<500

  union all
  select 'sealed-quick:premium',d.*
  from _mx_quick_dense d
  where d.market_price>=500

  union all
  select 'sealed-quick:new-releases',d.*
  from _mx_quick_dense d
  where d.release_date is not null
    and d.market_date>=d.release_date
    and (d.market_date-d.release_date)<=180

  union all
  select 'sealed-quick:established',d.*
  from _mx_quick_dense d
  where d.release_date is not null
    and (d.market_date-d.release_date)>730
    and (d.market_date-d.release_date)<=1825

  union all
  select
    'sealed-quick:global-top10',
    r.sealed_product_id,r.market_date,r.market_price,r.set_id,r.era_id,r.product_family,r.release_date
  from _mx_quick_ranked r
  where r.global_rank<=10;

  create index on _mx_quick_members(market_key,market_date,sealed_product_id);
  analyze _mx_quick_members;

  with definitions(market_key,label,taxonomy_key,definition) as (
    values
      ('sealed-quick:obtainable','Obtainable','obtainable',
       '{"axis":"price","priceLt":100,"bulkExcluded":true}'::jsonb),
      ('sealed-quick:intermediate','Intermediate','intermediate',
       '{"axis":"price","priceGte":100,"priceLt":500,"bulkExcluded":true}'::jsonb),
      ('sealed-quick:premium','Premium','premium',
       '{"axis":"price","priceGte":500,"bulkExcluded":true}'::jsonb),
      ('sealed-quick:new-releases','New Releases','new-releases',
       '{"axis":"releaseAge","ageDaysLte":180,"bulkExcluded":true}'::jsonb),
      ('sealed-quick:established','Established','established',
       '{"axis":"releaseAge","ageDaysGt":730,"ageDaysLte":1825,"bulkExcluded":true}'::jsonb),
      ('sealed-quick:global-top10','Global Top 10','global-top10',
       '{"axis":"rank","topN":10,"dateSpecificMembership":true,"bulkExcluded":true}'::jsonb)
  ),
  current_stats as (
    select market_key,count(*)::integer n
    from _mx_quick_members
    where market_date=p_market_date
    group by market_key
  )
  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,comparison_as_of,constituent_count,
    composition_kind,availability,unavailable_reason,definition_version,
    screen_group,screen_eligible,metadata
  )
  select
    p_generation_id,d.market_key,'sealed','quick',d.label,d.label,
    'normalized_sealed_daily_v1',d.taxonomy_key,p_market_date,p_market_date,
    coalesce(c.n,0),'index_and_composition',
    case when coalesce(c.n,0)>0 then 'available' else 'empty' end,
    case when coalesce(c.n,0)>0 then null else 'No eligible non-bulk products on comparison date' end,
    'sealed-quick-v1','sealed',true,
    jsonb_build_object(
      'quickKey',d.taxonomy_key,
      'definition',d.definition,
      'bulkContainersExcluded',true,
      'comparisonAsOf',p_market_date
    )
  from definitions d
  left join current_stats c using(market_key);

  get diagnostics v_markets=row_count;

  with daily as (
    select
      c.market_key,c.market_date,
      count(*)::integer constituent_count,
      sum(c.market_price)::numeric tracked_value,
      coalesce(sum(c.market_price) filter(where p.sealed_product_id is not null),0)::numeric current_common,
      coalesce(sum(p.market_price) filter(where p.sealed_product_id is not null),0)::numeric previous_common
    from _mx_quick_members c
    left join _mx_quick_members p
      on p.market_key=c.market_key
     and p.sealed_product_id=c.sealed_product_id
     and p.market_date=c.market_date-1
    group by c.market_key,c.market_date
  ),
  indexed as (
    select d.*,
      (
        100.0 * exp(sum(ln(
          case when d.previous_common>0 and d.current_common>0
               then d.current_common/d.previous_common
               else 1.0 end
        )) over(
          partition by d.market_key
          order by d.market_date
          rows unbounded preceding
        ))
      )::numeric index_value
    from daily d
  )
  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select
    p_generation_id,i.market_key,i.market_date,i.index_value,i.tracked_value,i.constituent_count,0
  from indexed i
  where i.market_date<=p_market_date;

  get diagnostics v_history=row_count;

  insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  )
  select
    p_generation_id,d.market_key,'sealed',d.constituent_count,
    d.availability,d.unavailable_reason
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id
    and d.market_key like 'sealed-quick:%';

  insert into public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  select
    p_generation_id,q.market_key,
    row_number() over(
      partition by q.market_key order by q.market_price desc,q.sealed_product_id
    )::integer,
    q.sealed_product_id,'sealed',q.set_id,q.market_price,q.market_date,
    jsonb_build_object(
      'asset','sealed',
      'instrumentId',q.sealed_product_id,
      'sealedProductId',q.sealed_product_id,
      'setId',m.set_id,
      'setName',m.set_name,
      'name',m.name,
      'productName',m.name,
      'variantLabel',m.variant_label,
      'productFamily',m.product_family,
      'productFamilyLabel',m.product_family_label,
      'marketPrice',q.market_price,
      'priceAsOf',q.market_date,
      'imageUrl',coalesce(m.image_small_url,m.image_large_url),
      'imageSmallUrl',m.image_small_url,
      'imageLargeUrl',m.image_large_url,
      'isBulkContainer',m.is_bulk_container
    )
  from _mx_quick_members q
  join public.pokemon_market_explorer_sealed_current_metadata_v1 m
    on m.sealed_product_id=q.sealed_product_id
  where q.market_date=p_market_date;

  get diagnostics v_constituents=row_count;

  return jsonb_build_object(
    'markets',v_markets,
    'historyRows',v_history,
    'constituentRows',v_constituents,
    'comparisonAsOf',p_market_date
  );
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_sealed_quicks_v1(uuid,date)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_sealed_quicks_v1(uuid,date)
to service_role;

create or replace function public.get_pokemon_market_explorer_surface_screen_v2(
  p_screen_key text,
  p_asset text default 'all',
  p_limit integer default 25,
  p_expected_generation_id uuid default null
)
returns table(
  rank integer,
  market_key text,
  label text,
  asset text,
  market_type text,
  metric_key text,
  metric_pct numeric,
  return_7d_pct numeric,
  comparison_as_of date,
  relative_7d_vs_era_pct numeric,
  current_drawdown_pct numeric,
  constituent_count integer,
  generation_id uuid
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
as $function$
declare
  v_screen text := lower(btrim(coalesce(p_screen_key,'')));
  v_asset text := lower(btrim(coalesce(p_asset,'all')));
  v_limit integer := least(greatest(coalesce(p_limit,25),1),25);
  v_generation uuid;
begin
  if v_screen not in (
    'top-performers','worst-performers','rarity-leaders',
    'sealed-format-leaders','momentum-leaders','largest-drawdowns'
  ) then
    raise exception 'UNKNOWN_MARKET_EXPLORER_SCREEN' using errcode='22023';
  end if;
  if v_asset not in ('all','cards','sealed') then
    raise exception 'p_asset must be all, cards, or sealed' using errcode='22023';
  end if;

  select s.generation_id into v_generation
  from public.pokemon_market_explorer_surface_serving_v2 s
  where s.singleton=1
  limit 1;

  if v_generation is null then
    raise exception 'MARKET_EXPLORER_V2_NOT_SERVING';
  end if;
  if p_expected_generation_id is not null and p_expected_generation_id<>v_generation then
    raise exception 'MARKET_EXPLORER_GENERATION_MISMATCH';
  end if;

  return query
  with candidates as (
    select
      d.market_key,d.label,d.asset,d.scope_kind,
      case
        when v_screen in ('top-performers','worst-performers') then 'return_7d'
        when v_screen in ('rarity-leaders','sealed-format-leaders','momentum-leaders') then 'return_30d'
        else 'current_drawdown'
      end metric_key,
      case
        when v_screen in ('top-performers','worst-performers') then d.return_7d_pct
        when v_screen in ('rarity-leaders','sealed-format-leaders','momentum-leaders') then d.return_30d_pct
        else d.current_drawdown_pct
      end metric_pct,
      d.return_7d_pct,d.comparison_as_of,d.current_drawdown_pct,d.constituent_count
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=v_generation
      and d.availability='available'
      and d.history_available
      and d.comparison_as_of is not null
      and (v_asset='all' or d.asset=v_asset)
      and (
        v_screen in ('top-performers','worst-performers')
        or (v_screen='rarity-leaders' and d.asset='cards' and d.scope_kind='rarity')
        or (v_screen='sealed-format-leaders' and d.asset='sealed' and d.scope_kind='type')
        or v_screen in ('momentum-leaders','largest-drawdowns')
      )
  ),
  ranked as (
    select c.*,
      row_number() over(
        order by
          case when v_screen in ('worst-performers','largest-drawdowns') then c.metric_pct end asc nulls last,
          case when v_screen not in ('worst-performers','largest-drawdowns') then c.metric_pct end desc nulls last,
          c.label,c.market_key
      )::integer r
    from candidates c
    where c.metric_pct is not null
  )
  select
    x.r,x.market_key,x.label,x.asset,x.scope_kind,x.metric_key,x.metric_pct,
    x.return_7d_pct,x.comparison_as_of,
    null::numeric relative_7d_vs_era_pct,
    x.current_drawdown_pct,x.constituent_count,v_generation
  from ranked x
  where x.r<=v_limit
  order by x.r;
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_surface_screen_v2(text,text,integer,uuid)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_surface_screen_v2(text,text,integer,uuid)
to service_role;

commit;
