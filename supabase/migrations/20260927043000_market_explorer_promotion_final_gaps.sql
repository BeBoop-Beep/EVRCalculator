
begin;

-- Product-specific parent eligibility: family membership alone is insufficient for
-- cartons/cases/displays whose names classify under a retail family.
create or replace function public.market_explorer_sealed_parent_member_for_product_v1(
  p_name text,
  p_family text
)
returns boolean
language sql
immutable
security invoker
set search_path = ''
as $function$
  select public.market_explorer_sealed_parent_member_v1(p_family)
     and not (
       pg_catalog.lower(coalesce(p_name,'')) ~ '\\mcase\\M'
       or pg_catalog.lower(coalesce(p_name,'')) ~ '\\mdisplay\\M'
       or pg_catalog.lower(coalesce(p_name,'')) ~ '\\m(master[[:space:]]+)?carton\\M'
     );
$function$;

revoke all on function public.market_explorer_sealed_parent_member_for_product_v1(text,text)
from public,anon,authenticated;
grant execute on function public.market_explorer_sealed_parent_member_for_product_v1(text,text)
to service_role;

-- Keep normalized daily parent membership product-aware.
create or replace function public.refresh_pokemon_market_explorer_sealed_daily_v1(
  p_from date,
  p_through date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set "TimeZone" = 'UTC'
set statement_timeout = '180s'
as $function$
declare
  v_rows integer;
begin
  if p_from is null or p_through is null or p_from>p_through then
    raise exception 'SEALED_DAILY_INVALID_RANGE';
  end if;
  if p_through-p_from > 4000 then
    raise exception 'SEALED_DAILY_RANGE_TOO_LARGE';
  end if;

  with ranked as materialized (
    select
      p.id::text as sealed_product_id,
      o.captured_at::date as market_date,
      o.market_price::numeric as market_price,
      p.set_id,
      s.era_id,
      p.name,
      public.market_explorer_sealed_product_family_v1(p.name) as product_family,
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
    'sealed-product-classification-v4-product-bulk-aware',clock_timestamp()
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
  return jsonb_build_object('from',p_from,'through',p_through,'upsertedRows',v_rows);
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_sealed_daily_v1(date,date)
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_daily_v1(date,date)
to service_role;

-- Keep current metadata in the same authority contract.
create or replace function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
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
    f.family,public.market_explorer_sealed_family_label_v1(f.family),
    public.market_explorer_sealed_variant_label_v1(p.name),
    f.family='case',f.family='display',
    (f.family in ('case','display')
      or pg_catalog.lower(p.name) ~ '\\m(master[[:space:]]+)?carton\\M'),
    f.family='multi_product_bundle',
    public.market_explorer_sealed_parent_member_for_product_v1(p.name,f.family),
    'sealed-product-classification-v4-product-bulk-aware',
    p.image_small_url,p.image_large_url,
    latest.market_date,latest.market_price,
    pg_catalog.lower(pg_catalog.concat_ws(' ',p.name,s.name,e.name,
      public.market_explorer_sealed_family_label_v1(f.family),
      public.market_explorer_sealed_variant_label_v1(p.name))),
    clock_timestamp()
  from public.sealed_products p
  left join public.sets s on s.id=p.set_id
  left join public.eras e on e.id=s.era_id
  cross join lateral (
    select public.market_explorer_sealed_product_family_v1(p.name) as family
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
    'classificationVersion','sealed-product-classification-v4-product-bulk-aware',
    'pricedRows',(select count(*) from public.pokemon_market_explorer_sealed_current_metadata_v1 where latest_market_price>0)
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
to service_role;

-- Asset-aware leaf eligibility. Cards use card-daily max date; sealed uses the
-- normalized current metadata authority. "three pack" is normalized to "3 pack".
create or replace function public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text default 'all',
  p_limit integer default 20
)
returns table(
  asset text,instrument_id uuid,name text,set_id uuid,set_name text,image_url text,
  card_number text,rarity text,edition text,printing_type text,special_type text,
  product_family text,variant_label text,match_kind text,relevance_score integer,name_similarity real
)
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set work_mem = '16MB'
as $function$
with args as materialized (
  select case
    when lower(trim(coalesce(p_asset,'all'))) in ('sealed','all')
      and lower(trim(coalesce(p_query,''))) ~ '^three[ -]+pack$'
      then '3 pack'
    else p_query
  end as effective_query
),
card_date as materialized (
  select max(d.market_date) market_date
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d
),
base as materialized (
  select u.*
  from args a
  cross join lateral public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(
    a.effective_query,p_asset,50
  ) u
),
eligible as (
  select b.*
  from base b
  where (
    b.asset='cards'
    and exists (
      select 1
      from card_date cd
      join public.pokemon_market_explorer_card_daily_states_v2_shadow d
        on d.market_date=cd.market_date
       and d.card_variant_id=b.instrument_id
       and d.market_price>0
    )
  ) or (
    b.asset='sealed'
    and exists (
      select 1
      from public.pokemon_market_explorer_sealed_current_metadata_v1 m
      where m.sealed_product_id=b.instrument_id::text
        and m.latest_market_price>0
        and m.latest_market_date is not null
    )
  )
)
select e.*
from eligible e
order by
  e.relevance_score desc,
  case when e.match_kind='fuzzy_name' then e.name_similarity else 0::real end desc,
  pg_catalog.lower(e.name),
  pg_catalog.lower(coalesce(e.set_name,'')),
  e.asset,e.instrument_id
limit least(greatest(coalesce(p_limit,20),1),50);
$function$;

revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
to service_role;

-- Explorer leaf-only compact search contract with current price/date included.
create or replace function public.search_pokemon_market_explorer_leaves_v1(
  p_asset text,
  p_query text,
  p_limit integer default 20
)
returns table(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  market_price numeric,
  market_date date,
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
  relevance_score integer
)
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set work_mem = '16MB'
as $function$
with hits as materialized (
  select *
  from public.search_pokemon_market_explorer_instruments_v2(
    p_query,p_asset,least(greatest(coalesce(p_limit,20),1),50)
  )
),
card_date as materialized (
  select max(market_date) market_date
  from public.pokemon_market_explorer_card_daily_states_v2_shadow
)
select
  h.asset,h.instrument_id,h.name,h.set_id,h.set_name,h.image_url,
  case when h.asset='cards' then cd.market_price else sm.latest_market_price end,
  case when h.asset='cards' then cdate.market_date else sm.latest_market_date end,
  case when h.asset='cards' then h.instrument_id end,
  case when h.asset='cards' then cm.canonical_card_id end,
  h.card_number,h.rarity,h.edition,h.printing_type,h.special_type,
  case when h.asset='sealed' then h.instrument_id end,
  h.product_family,h.variant_label,
  case when h.asset='sealed' then sm.is_bulk_container end,
  h.relevance_score
from hits h
cross join card_date cdate
left join public.pokemon_market_explorer_card_daily_states_v2_shadow cd
  on h.asset='cards'
 and cd.market_date=cdate.market_date
 and cd.card_variant_id=h.instrument_id
left join public.pokemon_market_explorer_card_current_metadata cm
  on h.asset='cards' and cm.card_variant_id=h.instrument_id
left join public.pokemon_market_explorer_sealed_current_metadata_v1 sm
  on h.asset='sealed' and sm.sealed_product_id=h.instrument_id::text
order by h.relevance_score desc,lower(h.name),h.instrument_id
limit least(greatest(coalesce(p_limit,20),1),50);
$function$;

revoke all on function public.search_pokemon_market_explorer_leaves_v1(text,text,integer)
from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_leaves_v1(text,text,integer)
to service_role;

commit;
