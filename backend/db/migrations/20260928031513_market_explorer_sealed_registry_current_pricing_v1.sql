begin;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '60s'
AS $function$
declare
  v_rows integer;
  v_market_date date;
begin
  select max(d.market_date)
  into v_market_date
  from public.pokemon_market_explorer_sealed_daily_v1 d;

  with meta as materialized (
    select
      product_family,
      min(product_family_label) display_label,
      count(*)::integer product_count,
      count(*) filter(
        where latest_market_price>0
          and latest_market_date>=v_market_date-30
      )::integer priced_count,
      count(distinct set_id)::integer set_count,
      count(distinct era_id)::integer era_count,
      bool_or(is_bulk_container) bulk_container,
      bool_or(parent_membership) parent_membership
    from public.pokemon_market_explorer_sealed_current_metadata_v1
    group by product_family
  ), hist as materialized (
    select
      product_family,
      min(market_date) history_start,
      max(market_date) history_end,
      count(distinct market_date)::integer history_points
    from public.pokemon_market_explorer_sealed_daily_v1
    group by product_family
  )
  insert into public.pokemon_market_explorer_sealed_type_registry_v1(
    product_family,display_label,definition,classification_version,
    current_product_count,current_priced_count,
    history_start_date,history_end_date,history_point_count,
    represented_set_count,represented_era_count,
    eligibility_state,prepared_market_key,parent_membership,bulk_container,audited_at
  )
  select
    m.product_family,m.display_label,
    public.market_explorer_sealed_family_definition_v2(m.product_family),
    'sealed-product-classification-v5-consumer-retail-taxonomy',
    m.product_count,m.priced_count,
    h.history_start,h.history_end,coalesce(h.history_points,0),
    m.set_count,m.era_count,
    case
      when m.priced_count=0 then 'UNAVAILABLE'
      when coalesce(h.history_points,0)<2 then 'INSUFFICIENT_HISTORY'
      else 'PREPARED_CANDIDATE'
    end,
    case when m.priced_count>0 then 'sealed-type:'||m.product_family end,
    m.parent_membership,m.bulk_container,clock_timestamp()
  from meta m
  left join hist h using(product_family)
  on conflict(product_family) do update
  set display_label=excluded.display_label,
      definition=excluded.definition,
      classification_version=excluded.classification_version,
      current_product_count=excluded.current_product_count,
      current_priced_count=excluded.current_priced_count,
      history_start_date=excluded.history_start_date,
      history_end_date=excluded.history_end_date,
      history_point_count=excluded.history_point_count,
      represented_set_count=excluded.represented_set_count,
      represented_era_count=excluded.represented_era_count,
      eligibility_state=excluded.eligibility_state,
      prepared_market_key=excluded.prepared_market_key,
      parent_membership=excluded.parent_membership,
      bulk_container=excluded.bulk_container,
      audited_at=excluded.audited_at;

  get diagnostics v_rows=row_count;

  delete from public.pokemon_market_explorer_sealed_type_registry_v1 r
  where not exists (
    select 1
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where m.product_family=r.product_family
  );

  return jsonb_build_object(
    'marketDate',v_market_date,
    'freshnessDays',30,
    'rows',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1),
    'upserted',v_rows,
    'pricedTypes',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1 where current_priced_count>0),
    'bulkTypes',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1 where bulk_container),
    'consumerParentTypes',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1 where parent_membership)
  );
end;
$function$
;

revoke all on function public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
to service_role;

select public.refresh_pokemon_market_explorer_sealed_type_registry_v1();

commit;
