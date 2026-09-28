begin;

CREATE OR REPLACE FUNCTION public.market_explorer_sealed_is_bulk_container_v2(p_name text, p_family text)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select coalesce(p_family,'') in ('case','display','master_carton')
      or pg_catalog.lower(coalesce(p_name,'')) ~ '\m(master[[:space:]]+)?carton\M'
      or pg_catalog.lower(coalesce(p_name,'')) ~ '\mcase\M'
      or pg_catalog.lower(coalesce(p_name,'')) ~ '\mdisplay\M';
$function$
;

CREATE OR REPLACE FUNCTION public.market_explorer_sealed_parent_member_for_product_v1(p_name text, p_family text)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select not public.market_explorer_sealed_is_bulk_container_v2(p_name,p_family);
$function$
;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '60s'
AS $function$
declare
  v_rows integer;
begin
  insert into public.pokemon_market_explorer_sealed_current_metadata_v1(
    sealed_product_id,set_id,era_id,name,set_name,era_name,
    product_family,product_family_label,variant_label,
    is_case,is_display,is_bulk_container,is_multi_product_bundle,parent_membership,
    classification_version,image_small_url,image_large_url,
    latest_market_date,latest_market_price,search_text,updated_at
  )
  select
    p.id::text,p.set_id,s.era_id,p.name,s.name,e.name,
    f.family,public.market_explorer_sealed_family_label_v2(f.family),
    public.market_explorer_sealed_variant_label_v1(p.name),
    f.family='case',f.family='display',
    public.market_explorer_sealed_is_bulk_container_v2(p.name,f.family),
    f.family in ('multi_product_bundle','booster_pack_art_bundle'),
    not public.market_explorer_sealed_is_bulk_container_v2(p.name,f.family),
    'sealed-product-classification-v5-consumer-retail-taxonomy',
    p.image_small_url,p.image_large_url,
    latest.market_date,latest.market_price,
    pg_catalog.lower(pg_catalog.concat_ws(
      ' ',p.name,s.name,e.name,
      public.market_explorer_sealed_family_label_v2(f.family),
      public.market_explorer_sealed_variant_label_v1(p.name)
    )),
    clock_timestamp()
  from public.sealed_products p
  left join public.sets s on s.id=p.set_id
  left join public.eras e on e.id=s.era_id
  cross join lateral (
    select public.market_explorer_sealed_product_family_v2(p.name) as family
  ) f
  left join lateral (
    select d.market_date,d.market_price
    from public.pokemon_market_explorer_sealed_daily_v1 d
    where d.sealed_product_id=p.id::text
    order by d.market_date desc
    limit 1
  ) latest on true
  on conflict (sealed_product_id) do update
  set set_id=excluded.set_id,era_id=excluded.era_id,name=excluded.name,
      set_name=excluded.set_name,era_name=excluded.era_name,
      product_family=excluded.product_family,
      product_family_label=excluded.product_family_label,
      variant_label=excluded.variant_label,
      is_case=excluded.is_case,is_display=excluded.is_display,
      is_bulk_container=excluded.is_bulk_container,
      is_multi_product_bundle=excluded.is_multi_product_bundle,
      parent_membership=excluded.parent_membership,
      classification_version=excluded.classification_version,
      image_small_url=excluded.image_small_url,image_large_url=excluded.image_large_url,
      latest_market_date=excluded.latest_market_date,
      latest_market_price=excluded.latest_market_price,
      search_text=excluded.search_text,updated_at=excluded.updated_at;

  get diagnostics v_rows=row_count;

  delete from public.pokemon_market_explorer_sealed_current_metadata_v1 m
  where not exists (
    select 1 from public.sealed_products p where p.id::text=m.sealed_product_id
  );

  return jsonb_build_object(
    'rows',v_rows,
    'classificationVersion','sealed-product-classification-v5-consumer-retail-taxonomy',
    'consumerPolicyVersion','market-explorer-consumer-sealed-v3-nonbulk-retail',
    'pricedRows',(select count(*) from public.pokemon_market_explorer_sealed_current_metadata_v1 where latest_market_price>0),
    'consumerRows',(select count(*) from public.pokemon_market_explorer_sealed_current_metadata_v1 where parent_membership),
    'bulkRows',(select count(*) from public.pokemon_market_explorer_sealed_current_metadata_v1 where is_bulk_container)
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_explorer_sealed_daily_v1(p_from date, p_through date)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
 SET statement_timeout TO '180s'
AS $function$
declare
  v_rows integer;
begin
  if p_from is null or p_through is null or p_from>p_through then
    raise exception 'SEALED_DAILY_INVALID_RANGE';
  end if;
  if p_through-p_from > 31 then
    raise exception 'SEALED_DAILY_RANGE_TOO_LARGE_FOR_BOUNDED_V5_REFRESH';
  end if;

  with ranked as materialized (
    select
      p.id::text as sealed_product_id,
      o.captured_at::date as market_date,
      o.market_price::numeric as market_price,
      p.set_id,
      s.era_id,
      p.name,
      public.market_explorer_sealed_product_family_v2(p.name) as product_family,
      o.source,
      o.id::text as source_observation_id,
      o.captured_at,
      row_number() over (
        partition by p.id,o.captured_at::date
        order by o.captured_at desc,o.id desc
      ) as rn
    from public.sealed_product_price_observations o
    join public.sealed_products p on p.id=o.sealed_product_id
    left join public.sets s on s.id=p.set_id
    where o.captured_at >= p_from::timestamptz
      and o.captured_at < (p_through+1)::timestamptz
      and o.market_price is not null and o.market_price>0
      and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
  )
  insert into public.pokemon_market_explorer_sealed_daily_v1(
    sealed_product_id,market_date,market_price,set_id,era_id,product_family,
    parent_membership,source,source_observation_id,captured_at,classification_version,refreshed_at
  )
  select
    r.sealed_product_id,r.market_date,r.market_price,r.set_id,r.era_id,r.product_family,
    public.market_explorer_sealed_parent_member_for_product_v1(r.name,r.product_family),
    r.source,r.source_observation_id,r.captured_at,
    'sealed-product-classification-v5-consumer-retail-taxonomy',clock_timestamp()
  from ranked r
  where r.rn=1
  on conflict (sealed_product_id,market_date) do update
  set market_price=excluded.market_price,
      set_id=excluded.set_id,
      era_id=excluded.era_id,
      product_family=excluded.product_family,
      parent_membership=excluded.parent_membership,
      source=excluded.source,
      source_observation_id=excluded.source_observation_id,
      captured_at=excluded.captured_at,
      classification_version=excluded.classification_version,
      refreshed_at=excluded.refreshed_at;

  get diagnostics v_rows=row_count;
  return jsonb_build_object(
    'from',p_from,'through',p_through,'upsertedRows',v_rows,
    'classificationVersion','sealed-product-classification-v5-consumer-retail-taxonomy',
    'consumerPolicyVersion','market-explorer-consumer-sealed-v3-nonbulk-retail'
  );
end;
$function$
;

revoke all on function public.market_explorer_sealed_is_bulk_container_v2(text,text)
from public,anon,authenticated;
grant execute on function public.market_explorer_sealed_is_bulk_container_v2(text,text)
to service_role;

revoke all on function public.market_explorer_sealed_parent_member_for_product_v1(text,text)
from public,anon,authenticated;
grant execute on function public.market_explorer_sealed_parent_member_for_product_v1(text,text)
to service_role;

revoke all on function public.refresh_pokemon_market_explorer_sealed_daily_v1(date,date)
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_daily_v1(date,date)
to service_role;

revoke all on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
to service_role;

select public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();
select public.refresh_pokemon_market_explorer_sealed_type_registry_v1();

commit;
