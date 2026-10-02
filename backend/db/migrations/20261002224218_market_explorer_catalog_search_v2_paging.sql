-- Bounded, catalog-first contextual search pages for Market Explorer.
-- Set-context pages are ranked by the current DB price authority; ordinary
-- name searches retain the canonical instrument search relevance order.

begin;

create or replace function public.search_pokemon_market_explorer_catalog_v2(
  p_asset text,
  p_query text,
  p_limit integer default 12,
  p_after integer default 0
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
set work_mem = '16MB'
as $function$
declare
  v_asset text := pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset,'')));
  v_query text := public.normalize_pokemon_market_explorer_search_text_v2(coalesce(p_query,''));
  v_limit integer := least(greatest(coalesce(p_limit,12),1),25);
  v_after integer := least(greatest(coalesce(p_after,0),0),5000);
  v_generation uuid;
  v_set_id uuid;
  v_market jsonb := '[]'::jsonb;
  v_items jsonb := '[]'::jsonb;
  v_count integer := 0;
begin
  if v_asset not in ('cards','sealed','graded') then
    raise exception 'ASSET_MUST_BE_CARDS_SEALED_OR_GRADED' using errcode='22023';
  end if;
  if pg_catalog.length(v_query)<2 then
    raise exception 'QUERY_TOO_SHORT' using errcode='22023';
  end if;
  if v_asset='graded' then
    return jsonb_build_object('results','[]'::jsonb,'nextCursor',null,'context','name');
  end if;

  select s.generation_id into v_generation
  from public.pokemon_market_explorer_surface_serving_v2 s where s.singleton=1;

  -- The best matching current Set market establishes context.  This is based
  -- on enumerable catalog identity, never a client label special case.
  select d.set_id,
         jsonb_build_array(jsonb_build_object(
           'asset',d.asset,'result_kind','set','label',d.label,
           'subtitle',case when d.asset='sealed' then 'Sealed Set market' else 'Set market' end,
           'market_key',d.market_key,'instrument_id',null,'set_id',d.set_id,
           'era_id',d.era_id,'image_url',null,'availability',d.availability,
           'metadata',jsonb_build_object('scopeKind',d.scope_kind,'marketScope',d.market_scope,
             'constituentCount',d.constituent_count,'generationId',d.generation_id),
           'relevance',case
             when public.normalize_pokemon_market_explorer_search_text_v2(d.label)=v_query then 1000
             when public.normalize_pokemon_market_explorer_search_text_v2(d.label) like v_query||'%' then 930
             else 860 end
         ))
    into v_set_id,v_market
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=v_generation and d.asset=v_asset and d.scope_kind='set'
    and public.normalize_pokemon_market_explorer_search_text_v2(d.label) like '%'||v_query||'%'
  order by
    (public.normalize_pokemon_market_explorer_search_text_v2(d.label)=v_query) desc,
    (public.normalize_pokemon_market_explorer_search_text_v2(d.label) like v_query||'%') desc,
    d.label,d.market_key
  limit 1;

  if v_set_id is not null and v_asset='cards' then
    with latest_market_date as materialized (
      select max(d.market_date) market_date
      from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    ), page as materialized (
      select m.card_variant_id,m.card_name,m.card_number,m.rarity,m.edition,
             m.printing_type,m.special_type,m.image_url,s.name set_name,d.market_price
      from latest_market_date md
      join public.pokemon_market_explorer_card_daily_states_v2_shadow d on d.market_date=md.market_date
      join public.pokemon_market_explorer_card_current_metadata m on m.card_variant_id=d.card_variant_id
      left join public.sets s on s.id=m.set_id
      where m.set_id=v_set_id and d.market_price>0
      order by d.market_price desc,m.card_variant_id
      offset v_after limit v_limit+1
    )
    select coalesce(jsonb_agg(jsonb_build_object(
             'asset','cards','result_kind','instrument','label',p.card_name,
             'subtitle',pg_catalog.concat_ws(' · ',p.set_name,nullif(pg_catalog.concat_ws(' ',p.card_number,p.rarity),'')),
             'market_key',null,'instrument_id',p.card_variant_id,'set_id',v_set_id,'era_id',null,
             'image_url',p.image_url,'availability','AVAILABLE','relevance',700,
             'metadata',jsonb_build_object('cardVariantId',p.card_variant_id,'cardNumber',p.card_number,
               'rarity',p.rarity,'edition',p.edition,'printingType',p.printing_type,
               'specialType',p.special_type,'marketPrice',p.market_price,'setName',p.set_name)
           ) order by p.market_price desc,p.card_variant_id) filter (where p.rn<=v_limit),'[]'::jsonb),
           count(*)
      into v_items,v_count
    from (select page.*,row_number() over() rn from page) p;
  elsif v_set_id is not null and v_asset='sealed' then
    with page as materialized (
      select m.*
      from public.pokemon_market_explorer_sealed_current_metadata_v1 m
      where m.set_id=v_set_id and m.latest_market_price>0
      order by m.latest_market_price desc,m.sealed_product_id
      offset v_after limit v_limit+1
    )
    select coalesce(jsonb_agg(jsonb_build_object(
             'asset','sealed','result_kind','instrument','label',p.name,
             'subtitle',pg_catalog.concat_ws(' · ',p.set_name,p.product_family_label,nullif(p.variant_label,'')),
             'market_key',null,'instrument_id',p.sealed_product_id,'set_id',p.set_id,'era_id',p.era_id,
             'image_url',coalesce(p.image_small_url,p.image_large_url),'availability','AVAILABLE','relevance',700,
             'metadata',jsonb_build_object('sealedProductId',p.sealed_product_id,'productFamily',p.product_family,
               'variantLabel',p.variant_label,'marketPrice',p.latest_market_price,'setName',p.set_name)
           ) order by p.latest_market_price desc,p.sealed_product_id) filter (where p.rn<=v_limit),'[]'::jsonb),
           count(*)
      into v_items,v_count
    from (select page.*,row_number() over() rn from page) p;
  else
    -- Name search keeps the reviewed canonical relevance contract.  Fetch one
    -- extra row for a bounded continuation signal; never re-rank in React.
    with sliced as materialized (
      select i.*
      from public.search_pokemon_market_explorer_instruments_v2(
        p_query,v_asset,least(v_after+v_limit+1,50)
      ) i offset v_after
    ), page as materialized (
      select sliced.*,row_number() over() rn from sliced
    )
    select coalesce(jsonb_agg(jsonb_build_object(
             'asset',p.asset,'result_kind','instrument','label',p.name,
             'subtitle',pg_catalog.concat_ws(' · ',p.set_name,nullif(pg_catalog.concat_ws(' ',p.card_number,p.rarity),'')),
             'market_key',null,'instrument_id',p.instrument_id,'set_id',p.set_id,'era_id',null,
             'image_url',p.image_url,'availability','AVAILABLE','relevance',p.relevance_score,
             'metadata',jsonb_build_object('cardNumber',p.card_number,'rarity',p.rarity,'edition',p.edition,
               'printingType',p.printing_type,'specialType',p.special_type,'productFamily',p.product_family,
               'variantLabel',p.variant_label,'matchKind',p.match_kind,'setName',p.set_name)
           ) order by p.rn) filter (where p.rn<=v_limit),'[]'::jsonb),count(*)
      into v_items,v_count from page p where p.rn<=v_limit+1;
  end if;

  return jsonb_build_object(
    'results',(case when v_after=0 then coalesce(v_market,'[]'::jsonb) else '[]'::jsonb end)||coalesce(v_items,'[]'::jsonb),
    'nextCursor',case when v_count>v_limit then (v_after+v_limit)::text else null end,
    'context',case when v_set_id is null then 'name' else 'set' end,
    'generationId',v_generation
  );
end;
$function$;

revoke all on function public.search_pokemon_market_explorer_catalog_v2(text,text,integer,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_catalog_v2(text,text,integer,integer)
to service_role;

commit;
