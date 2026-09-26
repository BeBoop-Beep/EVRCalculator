-- Market Explorer coherent currentness: generation watermark and asset-aware leaf search.
-- Forward-only/additive. No serving pointer is changed by this migration.

begin;

alter table public.pokemon_market_explorer_surface_generations_v2
  add column if not exists comparison_as_of date;

alter table public.pokemon_market_explorer_surface_directory_v2
  add column if not exists comparison_as_of date;

create index if not exists pokemon_market_explorer_surface_directory_v2_generation_comparison_idx
  on public.pokemon_market_explorer_surface_directory_v2(generation_id,comparison_as_of,asset,scope_kind,market_key);

comment on column public.pokemon_market_explorer_surface_generations_v2.comparison_as_of is
  'One certified Explorer workspace date for the immutable V2 generation.';
comment on column public.pokemon_market_explorer_surface_directory_v2.comparison_as_of is
  'Generation comparison watermark. Drawable markets must equal the serving generation watermark.';

create or replace function public.get_pokemon_market_explorer_asset_as_of_v1(p_asset text)
returns date
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
as $function$
declare
  v_asset text := lower(btrim(coalesce(p_asset,'')));
  v_serving_date date;
  v_authority_date date;
begin
  if v_asset not in ('cards','sealed') then
    raise exception 'p_asset must be cards or sealed' using errcode='22023';
  end if;

  select g.comparison_as_of
  into v_serving_date
  from public.pokemon_market_explorer_surface_serving_v2 s
  join public.pokemon_market_explorer_surface_generations_v2 g
    on g.generation_id=s.generation_id
  where s.singleton=1
    and g.state='VALIDATED'
  limit 1;

  if v_asset='cards' then
    select max(d.market_date)
    into v_authority_date
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d;
  else
    select max(d.market_date)
    into v_authority_date
    from public.pokemon_market_explorer_sealed_daily_v1 d;
  end if;

  if v_serving_date is null then
    return v_authority_date;
  end if;

  if v_authority_date is null or v_authority_date<v_serving_date then
    return null;
  end if;

  return v_serving_date;
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_asset_as_of_v1(text)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_asset_as_of_v1(text)
to service_role;

create or replace function public.search_pokemon_market_explorer_leaves_v3(
  p_query text,
  p_asset text default 'all',
  p_limit integer default 20
)
returns table(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  current_market_price numeric,
  current_market_date date,
  card_variant_id uuid,
  canonical_card_id uuid,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  sealed_product_id uuid,
  product_family text,
  variant_label text,
  is_bulk_container boolean,
  match_kind text,
  relevance_score integer,
  name_similarity real
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set work_mem = '16MB'
as $function$
declare
  v_asset text := lower(btrim(coalesce(p_asset,'all')));
  v_limit integer := least(greatest(coalesce(p_limit,20),1),50);
  v_norm text;
  v_card_date date;
  v_sealed_date date;
begin
  if v_asset not in ('all','cards','sealed') then
    raise exception 'p_asset must be all, cards, or sealed' using errcode='22023';
  end if;

  v_norm := public.normalize_pokemon_market_explorer_search_text_v2(coalesce(p_query,''));
  if v_norm is null or length(v_norm)<2 then
    return;
  end if;

  -- Normalize common sealed search vocabulary before relevance scoring.
  v_norm := public.normalize_pokemon_market_explorer_search_text_v2(
    regexp_replace(
      regexp_replace(' '||v_norm||' ',' etb ',' elite trainer box ','g'),
      '(^| )3( |$)','\1three\2','g'
    )
  );

  if v_asset in ('all','cards') then
    v_card_date := public.get_pokemon_market_explorer_asset_as_of_v1('cards');
  end if;
  if v_asset in ('all','sealed') then
    v_sealed_date := public.get_pokemon_market_explorer_asset_as_of_v1('sealed');
  end if;

  return query
  with card_seed as materialized (
    select u.*
    from public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(
      p_query,'cards',least(50,greatest(v_limit*3,20))
    ) u
    where v_asset in ('all','cards')
      and v_card_date is not null
  ),
  card_rows as (
    select
      'cards'::text asset,
      u.instrument_id,
      m.card_name::text name,
      m.set_id,
      s.name::text set_name,
      coalesce(
        cv.image_small_url,cc.image_small_url,
        cv.image_large_url,cc.image_large_url,m.image_url
      )::text image_url,
      d.market_price current_market_price,
      d.market_date current_market_date,
      m.card_variant_id,
      m.canonical_card_id,
      m.card_number,
      m.rarity,
      m.edition,
      m.printing_type,
      m.special_type,
      null::uuid sealed_product_id,
      null::text product_family,
      null::text variant_label,
      null::boolean is_bulk_container,
      u.match_kind,
      u.relevance_score,
      u.name_similarity
    from card_seed u
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id=u.instrument_id
    join public.pokemon_market_explorer_card_daily_states_v2_shadow d
      on d.card_variant_id=m.card_variant_id
     and d.market_date=v_card_date
     and d.market_price>0
    left join public.card_variants cv on cv.id=m.card_variant_id
    left join public.pokemon_canonical_cards cc on cc.id=m.canonical_card_id
    left join public.sets s on s.id=m.set_id
  ),
  sealed_features as materialized (
    select
      m.sealed_product_id::uuid instrument_id,
      m.name,
      m.set_id,
      m.set_name,
      coalesce(m.image_small_url,m.image_large_url) image_url,
      d.market_price current_market_price,
      d.market_date current_market_date,
      m.product_family,
      m.variant_label,
      m.is_bulk_container,
      public.normalize_pokemon_market_explorer_search_text_v2(m.name) norm_name,
      public.normalize_pokemon_market_explorer_search_text_v2(m.search_text) norm_search,
      extensions.similarity(
        public.normalize_pokemon_market_explorer_search_text_v2(m.name),
        v_norm
      )::real similarity_score
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    join public.pokemon_market_explorer_sealed_daily_v1 d
      on d.sealed_product_id=m.sealed_product_id
     and d.market_date=v_sealed_date
     and d.market_price>0
    where v_asset in ('all','sealed')
      and v_sealed_date is not null
  ),
  sealed_scored as (
    select
      'sealed'::text asset,
      f.instrument_id,
      f.name,
      f.set_id,
      f.set_name,
      f.image_url,
      f.current_market_price,
      f.current_market_date,
      null::uuid card_variant_id,
      null::uuid canonical_card_id,
      null::text card_number,
      null::text rarity,
      null::text edition,
      null::text printing_type,
      null::text special_type,
      f.instrument_id sealed_product_id,
      f.product_family,
      f.variant_label,
      f.is_bulk_container,
      case
        when f.norm_name=v_norm then 'exact_name'
        when f.norm_name like v_norm||'%' then 'name_prefix'
        when position(v_norm in f.norm_name)>0 then 'contiguous_phrase'
        when not exists (
          select 1
          from unnest(regexp_split_to_array(v_norm,' +')) t(token)
          where position(t.token in f.norm_search)=0
        ) then 'all_tokens'
        else 'fuzzy_name'
      end::text match_kind,
      case
        when f.norm_name=v_norm then 100000
        when f.norm_name like v_norm||'%' then 95000
        when position(v_norm in f.norm_name)>0 then 90000
        when not exists (
          select 1
          from unnest(regexp_split_to_array(v_norm,' +')) t(token)
          where position(t.token in f.norm_search)=0
        ) then 80000
        else 50000+floor(f.similarity_score*1000)::integer
      end::integer relevance_score,
      f.similarity_score name_similarity
    from sealed_features f
    where f.norm_name=v_norm
       or f.norm_name like v_norm||'%'
       or position(v_norm in f.norm_name)>0
       or not exists (
         select 1
         from unnest(regexp_split_to_array(v_norm,' +')) t(token)
         where position(t.token in f.norm_search)=0
       )
       or f.similarity_score>=0.35
  ),
  combined as (
    select * from card_rows
    union all
    select * from sealed_scored
  )
  select c.*
  from combined c
  order by
    c.relevance_score desc,
    case when c.match_kind='fuzzy_name' then c.name_similarity else 0::real end desc,
    lower(c.name),
    lower(coalesce(c.set_name,'')),
    c.asset,
    c.instrument_id
  limit v_limit;
end;
$function$;

revoke all on function public.search_pokemon_market_explorer_leaves_v3(text,text,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_leaves_v3(text,text,integer)
to service_role;

-- Preserve the existing RPC shape for current consumers, but route currency
-- through the asset authority rather than the globally latest READY Market Date.
create or replace function public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text default 'all',
  p_limit integer default 20
)
returns table(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  product_family text,
  variant_label text,
  match_kind text,
  relevance_score integer,
  name_similarity real
)
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
as $function$
  select
    r.asset,r.instrument_id,r.name,r.set_id,r.set_name,r.image_url,
    r.card_number,r.rarity,r.edition,r.printing_type,r.special_type,
    r.product_family,r.variant_label,r.match_kind,r.relevance_score,r.name_similarity
  from public.search_pokemon_market_explorer_leaves_v3(p_query,p_asset,p_limit) r;
$function$;

revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
to service_role;

commit;
