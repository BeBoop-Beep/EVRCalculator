begin;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_sealed_lattice_v2(p_generation_id uuid, p_market_date date)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '240s'
 SET work_mem TO '64MB'
AS $function$
declare
  v_history integer;
  v_rows integer;
  v_markets integer;
begin
  drop table if exists pg_temp._mx_sealed_dense;
  create temp table _mx_sealed_dense on commit drop as
  with intervals as (
    select d.*,
      lead(d.market_date,1,p_market_date+1) over(
        partition by d.sealed_product_id order by d.market_date
      ) next_date
    from public.pokemon_market_explorer_sealed_daily_v1 d
    where d.market_date<=p_market_date
  )
  select
    i.sealed_product_id,g.day::date as market_date,i.market_price,
    i.set_id,i.era_id,i.product_family,i.parent_membership,
    coalesce(meta.is_bulk_container,false) as is_bulk_container
  from intervals i
  join public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    on meta.sealed_product_id=i.sealed_product_id
  cross join lateral generate_series(
    i.market_date,
    least(p_market_date,i.next_date-1,i.market_date+30),
    interval '1 day'
  ) g(day);
  create index on _mx_sealed_dense(market_date,sealed_product_id);
  create index on _mx_sealed_dense(product_family,market_date,sealed_product_id);
  create index on _mx_sealed_dense(set_id,market_date,sealed_product_id);
  create index on _mx_sealed_dense(era_id,market_date,sealed_product_id);
  analyze _mx_sealed_dense;

  drop table if exists pg_temp._mx_sealed_members;
  create temp table _mx_sealed_members on commit drop as
  select
    'sealedMarket'::text market_key,'parent'::text scope_kind,
    null::uuid scope_set_id,null::uuid scope_era_id,null::text taxonomy_key,
    d.sealed_product_id,d.market_date,d.market_price,
    d.set_id as product_set_id,d.era_id as product_era_id,
    d.product_family,d.parent_membership
  from _mx_sealed_dense d where d.parent_membership and not d.is_bulk_container
  union all
  select
    'sealed-set:'||d.set_id::text,'set',d.set_id,null::uuid,null::text,
    d.sealed_product_id,d.market_date,d.market_price,
    d.set_id,d.era_id,d.product_family,d.parent_membership
  from _mx_sealed_dense d where d.parent_membership and not d.is_bulk_container and d.set_id is not null
  union all
  select
    'sealed-era:'||d.era_id::text,'era',null::uuid,d.era_id,null::text,
    d.sealed_product_id,d.market_date,d.market_price,
    d.set_id,d.era_id,d.product_family,d.parent_membership
  from _mx_sealed_dense d where d.parent_membership and not d.is_bulk_container and d.era_id is not null
  union all
  select
    'sealed-type:'||d.product_family,'type',null::uuid,null::uuid,d.product_family,
    d.sealed_product_id,d.market_date,d.market_price,
    d.set_id,d.era_id,d.product_family,d.parent_membership
  from _mx_sealed_dense d
  union all
  select
    'sealed-type:packs','type',null::uuid,null::uuid,'packs',
    d.sealed_product_id,d.market_date,d.market_price,
    d.set_id,d.era_id,d.product_family,d.parent_membership
  from _mx_sealed_dense d
  where d.product_family in ('loose_booster_pack','sleeved_booster_pack')
    and not d.is_bulk_container;

  create index on _mx_sealed_members(market_key,market_date,sealed_product_id);
  analyze _mx_sealed_members;

  -- Directory identities are determined from current-date membership, never by
  -- scanning history in the interactive reader.
  with current_stats as (
    select market_key,scope_kind,min(scope_set_id::text)::uuid set_id,min(scope_era_id::text)::uuid era_id,max(taxonomy_key) taxonomy_key,
      count(*)::integer n
    from _mx_sealed_members
    where market_date=p_market_date
    group by market_key,scope_kind
  )
  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    set_id,era_id,taxonomy_key,source_as_of,constituent_count,
    composition_kind,availability,definition_version,screen_group,screen_eligible,metadata
  )
  select
    p_generation_id,c.market_key,'sealed',c.scope_kind,
    case
      when c.market_key='sealedMarket' then 'Total Sealed Market'
      when c.scope_kind='set' then s.name||' - Sealed'
      when c.scope_kind='era' then e.name||' - Sealed'
      when c.taxonomy_key='packs' then 'Packs'
      else coalesce(r.display_label,public.market_explorer_sealed_family_label_v1(c.taxonomy_key))
    end,
    case
      when c.scope_kind='set' then s.name
      when c.scope_kind='era' then e.name
      else null
    end,
    'normalized_sealed_daily_v1',
    c.set_id,c.era_id,c.taxonomy_key,p_market_date,c.n,
    'index_and_composition',
    case when c.n>0 then 'available' else 'empty' end,
    'sealed-surface-v3-consumer-retail-dense-point-in-time-chain',
    'sealed',
    c.scope_kind='type',
    jsonb_build_object(
      'parentMembershipRule',
        case when c.market_key='sealedMarket' or c.scope_kind in ('set','era')
          then 'consumer_retail_nonbulk_only' else 'type_specific' end,
      'bulkContainersExcludedFromTotalSealed',true,
      'classificationVersion','sealed-product-classification-v5-consumer-retail-taxonomy',
      'packsComposite',c.taxonomy_key='packs'
    )
  from current_stats c
  left join public.sets s on s.id=c.set_id
  left join public.eras e on e.id=c.era_id
  left join public.pokemon_market_explorer_sealed_type_registry_v1 r
    on r.product_family=c.taxonomy_key
  where c.market_key='sealedMarket'
     or c.scope_kind in ('set','era')
     or c.taxonomy_key='packs'
     or exists (
       select 1 from public.pokemon_market_explorer_sealed_type_registry_v1 rr
       where rr.product_family=c.taxonomy_key
         and rr.current_priced_count>0
     )
  on conflict (generation_id,market_key) do nothing;
  get diagnostics v_markets=row_count;

  drop table if exists pg_temp._mx_sealed_daily_indexed;
  create temp table _mx_sealed_daily_indexed on commit drop as
  with lagged as (
    select m.*,
      lag(m.market_price) over(
        partition by m.market_key,m.sealed_product_id order by m.market_date
      ) previous_price
    from _mx_sealed_members m
    join public.pokemon_market_explorer_surface_directory_v2 d
      on d.generation_id=p_generation_id and d.market_key=m.market_key
  ), daily as (
    select market_key,market_date,
      count(*)::integer constituent_count,
      sum(market_price)::numeric basket_value,
      coalesce(sum(market_price) filter(where previous_price is not null),0)::numeric current_common,
      coalesce(sum(previous_price) filter(where previous_price is not null),0)::numeric previous_common
    from lagged
    group by market_key,market_date
  )
  select d.*,
    100.0 * exp(sum(ln(
      case when d.previous_common>0 then d.current_common/d.previous_common else 1.0 end
    )) over(partition by d.market_key order by d.market_date rows unbounded preceding))::numeric index_value
  from daily d;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select p_generation_id,market_key,market_date,index_value,basket_value,constituent_count,0
  from _mx_sealed_daily_indexed
  where market_date<=p_market_date;
  get diagnostics v_history=row_count;

  insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability
  )
  select p_generation_id,m.market_key,'sealed',count(*)::integer,
    case when count(*)>0 then 'available' else 'empty' end
  from _mx_sealed_members m
  join public.pokemon_market_explorer_surface_directory_v2 d
    on d.generation_id=p_generation_id and d.market_key=m.market_key
  where m.market_date=p_market_date
  group by m.market_key;

  insert into public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  select
    p_generation_id,m.market_key,
    row_number() over(partition by m.market_key order by m.market_price desc,m.sealed_product_id)::integer,
    m.sealed_product_id,'sealed',m.product_set_id,m.market_price,m.market_date,
    jsonb_build_object(
      'asset','sealed','instrumentId',m.sealed_product_id,'sealedProductId',m.sealed_product_id,
      'setId',meta.set_id,'setName',meta.set_name,
      'name',meta.name,'productName',meta.name,'variantLabel',meta.variant_label,
      'productFamily',meta.product_family,'productFamilyLabel',meta.product_family_label,
      'marketPrice',m.market_price,'priceAsOf',m.market_date,
      'imageUrl',coalesce(meta.image_small_url,meta.image_large_url),
      'imageSmallUrl',meta.image_small_url,'imageLargeUrl',meta.image_large_url,
      'isBulkContainer',meta.is_bulk_container
    )
  from _mx_sealed_members m
  join public.pokemon_market_explorer_surface_directory_v2 d
    on d.generation_id=p_generation_id and d.market_key=m.market_key
  join public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    on meta.sealed_product_id=m.sealed_product_id
  where m.market_date=p_market_date;
  get diagnostics v_rows=row_count;

  update public.pokemon_market_explorer_surface_directory_v2 d
  set constituent_count=t.total_count
  from public.pokemon_market_explorer_surface_constituent_totals_v2 t
  where d.generation_id=p_generation_id and t.generation_id=d.generation_id
    and t.market_key=d.market_key and d.asset='sealed';

  -- Compatibility aliases preserve the five old prepared-format keys without
  -- duplicating history or constituent storage.
  insert into public.pokemon_market_explorer_surface_aliases_v2(generation_id,alias_key,market_key,reason)
  select p_generation_id,d.market_key,
    case d.metadata->>'segmentKey'
      when 'boosterBox' then 'sealed-type:booster_box'
      when 'eliteTrainerBox' then 'sealed-type:elite_trainer_box'
      when 'pokemonCenterEliteTrainerBox' then 'sealed-type:pokemon_center_elite_trainer_box'
      when 'boosterBundle' then 'sealed-type:booster_bundle'
      when 'packs' then 'sealed-type:packs'
    end,
    'Legacy prepared sealed-format key'
  from public.pokemon_market_explorer_prepared_directory_generations_v1 d
  where d.asset='sealed' and d.market_type='prepared_format'
    and d.generation_id=(
      select base_prepared_generation_id
      from public.pokemon_market_explorer_surface_generations_v2
      where generation_id=p_generation_id
    )
    and d.metadata->>'segmentKey' in (
      'boosterBox','eliteTrainerBox','pokemonCenterEliteTrainerBox','boosterBundle','packs'
    )
    and exists (
      select 1 from public.pokemon_market_explorer_surface_directory_v2 s
      where s.generation_id=p_generation_id and s.market_key=
        case d.metadata->>'segmentKey'
          when 'boosterBox' then 'sealed-type:booster_box'
          when 'eliteTrainerBox' then 'sealed-type:elite_trainer_box'
          when 'pokemonCenterEliteTrainerBox' then 'sealed-type:pokemon_center_elite_trainer_box'
          when 'boosterBundle' then 'sealed-type:booster_bundle'
          when 'packs' then 'sealed-type:packs'
        end
    )
  on conflict(generation_id,alias_key) do update
  set market_key=excluded.market_key,reason=excluded.reason;

  return jsonb_build_object('markets',v_markets,'historyRows',v_history,'constituentRows',v_rows);
end;
$function$
;

commit;
