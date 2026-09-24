-- Unified contextual Market Explorer search and option metadata.
-- Search is asset-scoped and bounded.  It never scans historical authorities.

begin;

create index if not exists pokemon_market_explorer_sealed_meta_fts_v1
on public.pokemon_market_explorer_sealed_current_metadata_v1
using gin (pg_catalog.to_tsvector('simple'::regconfig,search_text));

create index if not exists pokemon_market_explorer_sealed_meta_trgm_v1
on public.pokemon_market_explorer_sealed_current_metadata_v1
using gin (
  public.normalize_pokemon_market_explorer_search_text_v2(search_text)
  extensions.gin_trgm_ops
);

create or replace function public.search_pokemon_market_explorer_catalog_v1(
  p_asset text,
  p_query text,
  p_limit integer default 20
)
returns table(
  asset text,
  result_kind text,
  label text,
  subtitle text,
  market_key text,
  instrument_id text,
  set_id uuid,
  era_id uuid,
  image_url text,
  availability text,
  metadata jsonb,
  relevance integer
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set work_mem = '16MB'
as $function$
declare
  v_asset text:=pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset,'')));
  v_limit integer:=least(greatest(coalesce(p_limit,20),1),50);
  v_q text;
  v_ts tsquery;
  v_generation uuid;
begin
  if v_asset not in ('cards','sealed','graded') then
    raise exception 'ASSET_MUST_BE_CARDS_SEALED_OR_GRADED' using errcode='22023';
  end if;

  v_q:=public.normalize_pokemon_market_explorer_search_text_v2(coalesce(p_query,''));
  if v_asset='graded' then
    return query
    select 'graded'::text,'graded_instrument'::text,'Graded Markets'::text,
      'Insufficient production authority'::text,null::text,null::text,null::uuid,null::uuid,
      null::text,'INSUFFICIENT_AUTHORITY'::text,
      jsonb_build_object(
        'status','unavailable',
        'reason','Current graded coverage is not broad enough to publish a production market.'
      ),
      1000::integer;
    return;
  end if;

  if v_q is null or pg_catalog.length(v_q)<2 then return; end if;

  select s.generation_id into v_generation
  from public.pokemon_market_explorer_surface_serving_v2 s
  where s.singleton=1;

  select pg_catalog.to_tsquery(
    'simple'::regconfig,
    pg_catalog.string_agg(t.token||':*',' & ' order by t.ord)
  )
  into v_ts
  from pg_catalog.unnest(pg_catalog.regexp_split_to_array(v_q,' +'))
       with ordinality as t(token,ord);

  if v_asset='cards' then
    return query
    with surface_markets as (
      select
        'cards'::text asset,
        case d.scope_kind
          when 'set' then 'set'
          when 'era' then 'era'
          when 'rarity' then 'rarity'
          else 'prepared_market'
        end::text result_kind,
        d.label,
        case d.scope_kind
          when 'set' then coalesce(d.market_scope,'Set market')
          when 'era' then 'Era market'
          when 'rarity' then 'Rarity market'
          when 'quick' then 'Quick market'
          else 'Prepared market'
        end::text subtitle,
        d.market_key,d.set_id,d.era_id,null::text image_url,
        d.availability,
        jsonb_build_object(
          'scopeKind',d.scope_kind,'marketScope',d.market_scope,
          'taxonomyKey',d.taxonomy_key,'definitionVersion',d.definition_version,
          'historyAvailable',d.history_available,'constituentCount',d.constituent_count
        ) metadata,
        case
          when public.normalize_pokemon_market_explorer_search_text_v2(d.label)=v_q then 1000
          when public.normalize_pokemon_market_explorer_search_text_v2(d.label) like v_q||'%' then 930
          when pg_catalog.to_tsvector('simple'::regconfig,
                 public.normalize_pokemon_market_explorer_search_text_v2(d.label)) @@ v_ts then 860
          else 700
        end::integer relevance
      from public.pokemon_market_explorer_surface_directory_v2 d
      where d.generation_id=v_generation and d.asset='cards'
        and (
          public.normalize_pokemon_market_explorer_search_text_v2(d.label) like '%'||v_q||'%'
          or pg_catalog.to_tsvector('simple'::regconfig,
               public.normalize_pokemon_market_explorer_search_text_v2(d.label)) @@ v_ts
        )
    ),
    legacy_markets as (
      select
        'cards'::text asset,
        case d.market_type
          when 'set' then 'set' when 'era' then 'era'
          when 'prepared_rarity' then 'rarity' else 'prepared_market'
        end::text result_kind,
        d.label,
        case d.market_type
          when 'set' then 'Set market' when 'era' then 'Era market'
          when 'prepared_rarity' then 'Rarity market' else 'Prepared market'
        end::text subtitle,
        d.market_key,d.set_id,d.era_id,null::text image_url,
        'available'::text availability,
        jsonb_build_object(
          'legacyPrepared',true,'marketType',d.market_type,
          'historyAvailable',d.history_available
        ) metadata,
        case
          when public.normalize_pokemon_market_explorer_search_text_v2(d.label)=v_q then 990
          when public.normalize_pokemon_market_explorer_search_text_v2(d.label) like v_q||'%' then 920
          else 800
        end::integer relevance
      from public.pokemon_market_explorer_prepared_directory_v1 d
      where v_generation is null and d.asset='cards'
        and (
          public.normalize_pokemon_market_explorer_search_text_v2(d.label) like '%'||v_q||'%'
          or pg_catalog.to_tsvector('simple'::regconfig,
               public.normalize_pokemon_market_explorer_search_text_v2(d.label)) @@ v_ts
        )
    ),
    rarity_options as (
      select
        'cards'::text asset,'rarity'::text result_kind,r.label,
        case r.eligibility_state
          when 'PREPARED' then 'Prepared rarity market'
          when 'CUSTOM_BUILD_AVAILABLE' then 'Eligible rarity market'
          else replace(pg_catalog.lower(r.eligibility_state),'_',' ')
        end::text subtitle,
        coalesce(
          (select d.market_key
           from public.pokemon_market_explorer_surface_directory_v2 d
           where d.generation_id=v_generation and d.asset='cards'
             and d.scope_kind='rarity' and d.taxonomy_key=r.rarity_key
           limit 1),
          r.prepared_market_key
        ) market_key,
        null::uuid set_id,null::uuid era_id,null::text image_url,
        r.eligibility_state::text availability,
        jsonb_build_object(
          'rarityKey',r.rarity_key,'taxonomyVersion',r.taxonomy_version,
          'currentPricedCardCount',r.current_priced_card_count,
          'representedSetCount',r.represented_set_count,
          'historyPointCount',r.history_point_count,'reason',r.reason
        ) metadata,
        case
          when public.normalize_pokemon_market_explorer_search_text_v2(r.label)=v_q then 980
          when public.normalize_pokemon_market_explorer_search_text_v2(r.label) like v_q||'%' then 900
          else 790
        end::integer relevance
      from public.pokemon_market_explorer_rarity_registry_v1 r
      where public.normalize_pokemon_market_explorer_search_text_v2(r.label) like '%'||v_q||'%'
         or public.normalize_pokemon_market_explorer_search_text_v2(r.rarity_key) like '%'||v_q||'%'
    ),
    instruments as (
      select
        'cards'::text asset,'instrument'::text result_kind,i.name::text label,
        pg_catalog.concat_ws(' · ',i.set_name,
          nullif(pg_catalog.concat_ws(' ',i.card_number,i.rarity),'')
        )::text subtitle,
        null::text market_key,i.instrument_id::text instrument_id,
        i.set_id,null::uuid era_id,i.image_url,
        'AVAILABLE'::text availability,
        jsonb_build_object(
          'cardVariantId',i.instrument_id,'cardNumber',i.card_number,
          'rarity',i.rarity,'edition',i.edition,
          'printingType',i.printing_type,'specialType',i.special_type,
          'matchKind',i.match_kind
        ) metadata,
        greatest(600,least(950,i.relevance_score))::integer relevance
      from public.search_pokemon_market_explorer_instruments_v2(p_query,'cards',least(v_limit,20)) i
    ),
    candidates as (
      select asset,result_kind,label,subtitle,market_key,null::text instrument_id,set_id,era_id,image_url,availability,metadata,relevance
      from surface_markets
      union all
      select asset,result_kind,label,subtitle,market_key,null::text instrument_id,set_id,era_id,image_url,availability,metadata,relevance
      from legacy_markets
      union all
      select asset,result_kind,label,subtitle,market_key,null::text instrument_id,set_id,era_id,image_url,availability,metadata,relevance
      from rarity_options
      union all
      select * from instruments
    )
    select c.asset,c.result_kind,c.label,c.subtitle,c.market_key,c.instrument_id,
      c.set_id,c.era_id,c.image_url,c.availability,c.metadata,c.relevance
    from candidates c
    order by c.relevance desc,c.label,c.result_kind
    limit v_limit;
    return;
  end if;

  return query
  with surface_markets as (
    select
      'sealed'::text asset,
      case d.scope_kind
        when 'set' then 'set'
        when 'era' then 'era'
        when 'type' then 'sealed_type'
        when 'quick' then 'prepared_market'
        else 'prepared_market'
      end::text result_kind,
      d.label,
      case d.scope_kind
        when 'set' then 'Sealed Set market'
        when 'era' then 'Sealed Era market'
        when 'type' then 'Sealed Type market'
        when 'quick' then 'Sealed Quick market'
        else 'Sealed market'
      end::text subtitle,
      d.market_key,d.set_id,d.era_id,
      null::text image_url,d.availability,
      jsonb_build_object(
        'scopeKind',d.scope_kind,'taxonomyKey',d.taxonomy_key,
        'definitionVersion',d.definition_version,
        'historyAvailable',d.history_available,'constituentCount',d.constituent_count
      ) metadata,
      case
        when public.normalize_pokemon_market_explorer_search_text_v2(d.label)=v_q then 1000
        when public.normalize_pokemon_market_explorer_search_text_v2(d.label) like v_q||'%' then 930
        when pg_catalog.to_tsvector('simple'::regconfig,
               public.normalize_pokemon_market_explorer_search_text_v2(d.label)) @@ v_ts then 860
        else 700
      end::integer relevance
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=v_generation and d.asset='sealed'
      and (
        public.normalize_pokemon_market_explorer_search_text_v2(d.label) like '%'||v_q||'%'
        or pg_catalog.to_tsvector('simple'::regconfig,
             public.normalize_pokemon_market_explorer_search_text_v2(d.label)) @@ v_ts
      )
  ),
  type_options as (
    select
      'sealed'::text asset,'sealed_type'::text result_kind,r.display_label label,
      case when r.bulk_container then 'Bulk/container sealed type' else 'Sealed product type' end::text subtitle,
      case
        when exists (
          select 1 from public.pokemon_market_explorer_surface_directory_v2 d
          where d.generation_id=v_generation
            and d.market_key='sealed-type:'||r.product_family
        ) then 'sealed-type:'||r.product_family
        else r.prepared_market_key
      end::text market_key,
      null::uuid set_id,null::uuid era_id,null::text image_url,
      r.eligibility_state::text availability,
      jsonb_build_object(
        'productFamily',r.product_family,'definition',r.definition,
        'currentProductCount',r.current_product_count,
        'currentPricedCount',r.current_priced_count,
        'historyPointCount',r.history_point_count,
        'representedSetCount',r.represented_set_count,
        'representedEraCount',r.represented_era_count,
        'parentMembership',r.parent_membership,
        'bulkContainer',r.bulk_container,
        'classificationVersion',r.classification_version
      ) metadata,
      case
        when public.normalize_pokemon_market_explorer_search_text_v2(r.display_label)=v_q then 970
        when public.normalize_pokemon_market_explorer_search_text_v2(r.display_label) like v_q||'%' then 890
        else 780
      end::integer relevance
    from public.pokemon_market_explorer_sealed_type_registry_v1 r
    where public.normalize_pokemon_market_explorer_search_text_v2(r.display_label) like '%'||v_q||'%'
       or public.normalize_pokemon_market_explorer_search_text_v2(r.product_family) like '%'||v_q||'%'
  ),
  instruments as (
    select
      'sealed'::text asset,'instrument'::text result_kind,m.name::text label,
      pg_catalog.concat_ws(' · ',m.set_name,m.product_family_label,
        nullif(m.variant_label,''))::text subtitle,
      null::text market_key,m.sealed_product_id::text instrument_id,
      m.set_id,m.era_id,coalesce(m.image_small_url,m.image_large_url) image_url,
      case when m.latest_market_price>0 then 'AVAILABLE' else 'NO_CURRENT_PRICE' end::text availability,
      jsonb_build_object(
        'sealedProductId',m.sealed_product_id,'productFamily',m.product_family,
        'variantLabel',m.variant_label,'latestMarketDate',m.latest_market_date,
        'latestMarketPrice',m.latest_market_price,
        'bulkContainer',m.is_bulk_container
      ) metadata,
      case
        when public.normalize_pokemon_market_explorer_search_text_v2(m.name)=v_q then 960
        when public.normalize_pokemon_market_explorer_search_text_v2(m.name) like v_q||'%' then 900
        when pg_catalog.to_tsvector('simple'::regconfig,m.search_text) @@ v_ts then 820
        else (700 + pg_catalog.floor(
          200 * extensions.similarity(
            public.normalize_pokemon_market_explorer_search_text_v2(m.search_text),v_q
          )
        ))::integer
      end relevance
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where
      pg_catalog.to_tsvector('simple'::regconfig,m.search_text) @@ v_ts
      or public.normalize_pokemon_market_explorer_search_text_v2(m.search_text) like v_q||'%'
      or (
        pg_catalog.length(v_q)>=4
        and public.normalize_pokemon_market_explorer_search_text_v2(m.search_text)
              operator(extensions.%) v_q
      )
    order by relevance desc,m.name,m.sealed_product_id
    limit least(v_limit*3,50)
  ),
  candidates as (
    select asset,result_kind,label,subtitle,market_key,null::text instrument_id,set_id,era_id,image_url,availability,metadata,relevance
    from surface_markets
    union all
    select asset,result_kind,label,subtitle,market_key,null::text instrument_id,set_id,era_id,image_url,availability,metadata,relevance
    from type_options
    union all
    select * from instruments
  )
  select c.asset,c.result_kind,c.label,c.subtitle,c.market_key,c.instrument_id,
    c.set_id,c.era_id,c.image_url,c.availability,c.metadata,c.relevance
  from candidates c
  order by c.relevance desc,c.label,c.result_kind
  limit v_limit;
end;
$function$;

revoke all on function public.search_pokemon_market_explorer_catalog_v1(text,text,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_catalog_v1(text,text,integer)
to service_role;

create or replace function public.get_pokemon_market_explorer_asset_options_v2(
  p_asset text
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
as $function$
declare
  v_asset text:=pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset,'')));
  v_generation uuid;
  v_result jsonb;
begin
  if v_asset not in ('cards','sealed','graded') then
    raise exception 'ASSET_MUST_BE_CARDS_SEALED_OR_GRADED';
  end if;

  select generation_id into v_generation
  from public.pokemon_market_explorer_surface_serving_v2 where singleton=1;

  if v_asset='cards' then
    select jsonb_build_object(
      'asset','cards',
      'rarityTaxonomyVersion','pokemon-card-rarity-filter-taxonomy-v1',
      'rarities',coalesce(jsonb_agg(
        jsonb_build_object(
          'key',r.rarity_key,'label',r.label,
          'preparedMarketAvailable',
            (r.prepared_market_key is not null or exists (
              select 1 from public.pokemon_market_explorer_surface_directory_v2 d
              where d.generation_id=v_generation and d.asset='cards'
                and d.scope_kind='rarity' and d.taxonomy_key=r.rarity_key
            )),
          'preparedMarketKey',coalesce(
            (select d.market_key
             from public.pokemon_market_explorer_surface_directory_v2 d
             where d.generation_id=v_generation and d.asset='cards'
               and d.scope_kind='rarity' and d.taxonomy_key=r.rarity_key
             limit 1),
            r.prepared_market_key
          ),
          'eligibilityState',r.eligibility_state,'reason',r.reason,
          'currentPricedCardCount',r.current_priced_card_count,
          'representedSetCount',r.represented_set_count,
          'historyPointCount',r.history_point_count,'imageCount',r.image_count
        ) order by r.label
      ),'[]'::jsonb)
    )
    into v_result
    from public.pokemon_market_explorer_rarity_registry_v1 r;
    return v_result;
  end if;

  if v_asset='sealed' then
    select jsonb_build_object(
      'asset','sealed',
      'classificationVersion','sealed-product-classification-v3-loose-pack-family',
      'totalSealedParentDefinition','Retail/overview families only; bulk containers are excluded',
      'types',coalesce(jsonb_agg(
        jsonb_build_object(
          'key',r.product_family,'label',r.display_label,'definition',r.definition,
          'preparedMarketAvailable',exists (
            select 1 from public.pokemon_market_explorer_surface_directory_v2 d
            where d.generation_id=v_generation
              and d.market_key='sealed-type:'||r.product_family
          ),
          'preparedMarketKey',case when exists (
            select 1 from public.pokemon_market_explorer_surface_directory_v2 d
            where d.generation_id=v_generation
              and d.market_key='sealed-type:'||r.product_family
          ) then 'sealed-type:'||r.product_family else r.prepared_market_key end,
          'eligibilityState',r.eligibility_state,
          'parentMembership',r.parent_membership,'bulkContainer',r.bulk_container,
          'currentProductCount',r.current_product_count,
          'currentPricedCount',r.current_priced_count,
          'representedSetCount',r.represented_set_count,
          'representedEraCount',r.represented_era_count,
          'historyPointCount',r.history_point_count
        ) order by r.display_label
      ),'[]'::jsonb),
      'quickMarkets',(
        select coalesce(jsonb_agg(jsonb_build_object(
          'key',q.quick_key,'label',q.label,'status',q.status,
          'definition',q.definition,'researchBasis',q.research_basis
        ) order by q.label),'[]'::jsonb)
        from public.pokemon_market_explorer_sealed_quick_registry_v1 q
      )
    )
    into v_result
    from public.pokemon_market_explorer_sealed_type_registry_v1 r;
    return v_result;
  end if;

  return jsonb_build_object(
    'asset','graded','availability','INSUFFICIENT_AUTHORITY',
    'reason','Graded production coverage is not yet broad enough to publish markets.'
  );
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_asset_options_v2(text)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_asset_options_v2(text)
to service_role;

commit;
