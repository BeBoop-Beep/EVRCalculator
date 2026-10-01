begin;

-- Market Explorer rarity candidate staging: preserve the exact chain-link
-- methodology while avoiding a 2.5M-row lag() sort that exceeded the existing
-- 180s publication bound in production.
--
-- The previous implementation computed each member's immediately preceding
-- observation with window lag() over (rarity_key, card_variant_id, market_date).
-- The dates CTE already owns the previous accepted market date for each rarity.
-- Joining current membership to that exact previous date on card_variant_id is
-- mathematically equivalent for the unique daily-state identity and is aligned
-- with the temp index (rarity_key, market_date, card_variant_id).
--
-- Production-sized read-only proof before this migration:
--   2,500,688 membership rows / 30 rarities / 2,730 daily rows
--   optimized daily build: 58.2s
-- Bounded equivalence proof on Common/Rare:
--   36 / 36 linked rows matched constituent_count, basket_value,
--   common_count, common_current, and common_previous exactly.

create or replace function public.stage_pokemon_market_explorer_rarity_candidates_v2(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path=''
set statement_timeout='180s'
set work_mem='64MB'
as $function$
declare
  v_markets integer:=0;
  v_history integer:=0;
  v_rows integer:=0;
begin
  drop table if exists pg_temp._mx_rarity_members;
  create temp table _mx_rarity_members on commit drop as
  select
    r.rarity_key,
    ('rarity:'||r.rarity_key)::text as market_key,
    d.market_date,d.card_variant_id,d.set_id,d.market_price,
    m.canonical_card_id,m.card_name,m.card_number,m.rarity,
    m.edition,m.printing_type,m.special_type,m.image_url
  from public.pokemon_market_explorer_rarity_registry_v1 r
  join public.pokemon_market_explorer_card_current_metadata m
    on m.filter_rarity_key=r.rarity_key
  join public.pokemon_market_explorer_card_daily_states_v2_shadow d
    on d.card_variant_id=m.card_variant_id and d.set_id=m.set_id
  where r.eligibility_state='CUSTOM_BUILD_AVAILABLE'
    and exists (
      select 1 from public.pokemon_market_date_quality q
      where q.tcg='pokemon' and q.market_date=d.market_date
        and q.status in ('READY','LEGACY_VERIFIED')
    )
    and r.prepared_market_key is null
    and d.market_date<=p_market_date and d.market_price>0;

  create index on _mx_rarity_members(rarity_key,market_date,card_variant_id);
  analyze _mx_rarity_members;

  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,constituent_count,composition_kind,availability,
    definition_version,screen_group,screen_eligible,metadata
  )
  select
    p_generation_id,'rarity:'||r.rarity_key,'cards','rarity',r.label,r.label,
    'rarity_registry_v1',r.rarity_key,p_market_date,r.current_priced_card_count,
    'index_and_composition',
    case when r.current_priced_card_count>0 then 'available' else 'empty' end,
    r.taxonomy_version,'card',true,
    jsonb_build_object(
      'rarityKey',r.rarity_key,'eligibilityState',r.eligibility_state,
      'qualityGate','25 cards / 3 sets + current positive pricing + >=2 accepted dates',
      'newPreparedCandidate',true
    )
  from public.pokemon_market_explorer_rarity_registry_v1 r
  where r.eligibility_state='CUSTOM_BUILD_AVAILABLE' and r.prepared_market_key is null
    and exists (
      select 1 from _mx_rarity_members x
      where x.rarity_key=r.rarity_key and x.market_date=p_market_date
    )
  on conflict (generation_id,market_key) do nothing;
  get diagnostics v_markets=row_count;

  drop table if exists pg_temp._mx_rarity_daily;
  create temp table _mx_rarity_daily on commit drop as
  with dates as (
    select rarity_key,market_key,market_date,
      lag(market_date) over(partition by rarity_key order by market_date) prev_date
    from (select distinct rarity_key,market_key,market_date from _mx_rarity_members) q
  ),
  linked as (
    select
      dt.rarity_key,dt.market_key,dt.market_date,dt.prev_date,
      count(m.card_variant_id)::integer constituent_count,
      sum(m.market_price)::numeric basket_value,
      count(p.card_variant_id)::integer common_count,
      coalesce(sum(m.market_price) filter(where p.card_variant_id is not null),0)::numeric common_current,
      coalesce(sum(p.market_price),0)::numeric common_previous
    from dates dt
    join _mx_rarity_members m
      on m.rarity_key=dt.rarity_key
     and m.market_date=dt.market_date
    left join _mx_rarity_members p
      on p.rarity_key=m.rarity_key
     and p.card_variant_id=m.card_variant_id
     and p.market_date=dt.prev_date
    group by dt.rarity_key,dt.market_key,dt.market_date,dt.prev_date
  ),
  ratios as (
    select l.*,
      case when l.prev_date is not null and l.common_count>0 and l.common_previous>0
        then l.common_current/l.common_previous end link_ratio,
      case when l.prev_date is null or l.common_count=0 or l.common_previous<=0 then 1 else 0 end break_flag
    from linked l
  ),
  segments as (
    select r.*,
      sum(break_flag) over(partition by rarity_key order by market_date rows unbounded preceding)::integer segment_id
    from ratios r
  )
  select s.*,
    100.0 * exp(coalesce(
      sum(ln(s.link_ratio)) filter(where s.link_ratio is not null)
        over(partition by s.rarity_key,s.segment_id order by s.market_date rows unbounded preceding),
      0
    ))::numeric as index_value
  from segments s;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select p_generation_id,market_key,market_date,index_value,basket_value,constituent_count,segment_id
  from _mx_rarity_daily;
  get diagnostics v_history=row_count;

  insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability
  )
  select p_generation_id,d.market_key,'cards',count(*)::integer,
    case when count(*)>0 then 'available' else 'empty' end
  from _mx_rarity_members d
  join public.pokemon_market_explorer_surface_directory_v2 s
    on s.generation_id=p_generation_id and s.market_key=d.market_key
  where d.market_date=p_market_date
  group by d.market_key;

  insert into public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  select
    p_generation_id,x.market_key,
    row_number() over(partition by x.market_key order by x.market_price desc,x.card_variant_id)::integer,
    x.card_variant_id::text,'cards',x.set_id,x.market_price,x.market_date,
    jsonb_build_object(
      'asset','cards','instrumentId',x.card_variant_id,'cardVariantId',x.card_variant_id,
      'canonicalCardId',x.canonical_card_id,'setId',x.set_id,'setName',s.name,
      'name',x.card_name,'cardName',x.card_name,'cardNumber',x.card_number,
      'rarity',x.rarity,'edition',x.edition,'printingType',x.printing_type,
      'specialType',x.special_type,'marketPrice',x.market_price,'priceAsOf',x.market_date,
      'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,x.image_url),
      'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
      'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url)
    )
  from _mx_rarity_members x
  join public.pokemon_market_explorer_surface_directory_v2 sd
    on sd.generation_id=p_generation_id and sd.market_key=x.market_key
  left join public.card_variants cv on cv.id=x.card_variant_id
  left join public.pokemon_canonical_cards cc on cc.id=x.canonical_card_id
  left join public.sets s on s.id=x.set_id
  where x.market_date=p_market_date;
  get diagnostics v_rows=row_count;

  update public.pokemon_market_explorer_surface_directory_v2 d
  set constituent_count=t.total_count
  from public.pokemon_market_explorer_surface_constituent_totals_v2 t
  where d.generation_id=p_generation_id and t.generation_id=d.generation_id
    and t.market_key=d.market_key and d.scope_kind='rarity';

  return jsonb_build_object('markets',v_markets,'historyRows',v_history,'constituentRows',v_rows);
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
to service_role;

commit;
