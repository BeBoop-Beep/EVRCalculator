begin;

create table if not exists public.pokemon_market_raw_edition_stable_leaf_history_v1 (
  market_date date not null,
  market_key text not null,
  root_set_id uuid not null,
  member_set_id uuid,
  market_scope text not null check (
    market_scope in ('standard','first_edition','unlimited','shadowless')
  ),
  canonical_card_id uuid not null,
  card_variant_id uuid not null,
  market_price numeric not null check (market_price>0),
  observed_date date,
  source text not null default 'TCGPlayer',
  source_observation_id uuid,
  source_observation_created_at timestamptz,
  reconstruction_method text not null check (
    reconstruction_method in ('timestamp_rewind_v1','standard_asof_v2','edition_asof_v2')
  ),
  raw_source_generation_fingerprint text not null,
  created_at timestamptz not null default clock_timestamp(),
  primary key (market_date,market_key,canonical_card_id)
);

create unique index if not exists pokemon_market_raw_edition_stable_leaf_history_v1_variant_uq
  on public.pokemon_market_raw_edition_stable_leaf_history_v1(market_date,card_variant_id);
create index if not exists pokemon_market_raw_edition_stable_leaf_history_v1_market_idx
  on public.pokemon_market_raw_edition_stable_leaf_history_v1(market_date,market_key);

alter table public.pokemon_market_raw_edition_stable_leaf_history_v1 enable row level security;
revoke all on public.pokemon_market_raw_edition_stable_leaf_history_v1
  from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_raw_edition_stable_leaf_history_v1
  to service_role;

create or replace function public.refresh_pokemon_market_raw_edition_stable_leaves_v1(
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path=''
set statement_timeout='900s'
set work_mem='96MB'
as $function$
declare
  v_raw public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
  v_nm uuid;
  v_existing_count integer;
  v_existing_value numeric;
  v_existing_fp_ok boolean;
  v_unresolved integer;
  v_bad_markets integer;
  v_duplicate_variants integer;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_rewind_roots integer;
  v_asof_roots integer;
  v_scoped_markets integer;
begin
  if p_market_date is null then
    raise exception 'RAW_LEAF_MARKET_DATE_REQUIRED';
  end if;

  select * into v_raw
  from public.pokemon_market_raw_edition_stable_daily_history_v1 h
  where h.market_date=p_market_date;

  if not found then
    raise exception 'RAW_LEAF_PARENT_NOT_FOUND: %',p_market_date;
  end if;

  select
    count(*)::integer,
    coalesce(sum(l.market_price),0)::numeric,
    coalesce(bool_and(l.raw_source_generation_fingerprint=v_raw.source_generation_fingerprint),false)
  into v_existing_count,v_existing_value,v_existing_fp_ok
  from public.pokemon_market_raw_edition_stable_leaf_history_v1 l
  where l.market_date=p_market_date;

  if v_existing_count=v_raw.card_count
     and round(v_existing_value,2)=round(v_raw.basket_value,2)
     and v_existing_fp_ok then
    return jsonb_build_object(
      'status','noop',
      'marketDate',p_market_date,
      'leafCount',v_existing_count,
      'leafValue',round(v_existing_value,2),
      'rawSourceGenerationFingerprint',v_raw.source_generation_fingerprint
    );
  end if;

  select c.id into v_nm
  from public.conditions c
  where c.name='Near Mint' and c.abbreviation='NM'
  order by c.id
  limit 1;

  if v_nm is null then
    raise exception 'RAW_LEAF_NEAR_MINT_CONDITION_MISSING';
  end if;

  drop table if exists pg_temp._raw_leaf_expected;
  create temp table _raw_leaf_expected on commit drop as
  select
    x->>'marketKey' as market_key,
    (x->>'setId')::uuid as root_set_id,
    x->>'marketScope' as market_scope,
    (x->>'setValue')::numeric as expected_value,
    (x->>'includedCardCount')::integer as expected_count,
    nullif(x->>'sourceUpdatedAt','')::timestamptz as source_updated_at
  from jsonb_array_elements(v_raw.constituents_json) x;

  create unique index on _raw_leaf_expected(market_key);
  create index on _raw_leaf_expected(root_set_id,market_scope);
  analyze _raw_leaf_expected;

  if exists (
    select 1 from _raw_leaf_expected
    where market_scope='standard' and source_updated_at is null
  ) then
    raise exception 'RAW_LEAF_STANDARD_SOURCE_TIMESTAMP_MISSING';
  end if;

  drop table if exists pg_temp._raw_leaf_rewind;
  create temp table _raw_leaf_rewind on commit drop as
  select
    e.market_key,e.root_set_id,q.member_set_id,e.market_scope,
    q.canonical_card_id,q.card_variant_id,
    o.market_price,o.captured_at as observed_date,
    'TCGPlayer'::text as source,
    o.id as source_observation_id,
    o.created_at as source_observation_created_at,
    'timestamp_rewind_v1'::text as reconstruction_method
  from _raw_leaf_expected e
  cross join lateral public.get_pokemon_market_root_set_card_prices_latest_v1(e.root_set_id) q
  left join lateral (
    select o.id,o.market_price,o.captured_at,o.created_at
    from public.card_variant_price_observations o
    where o.card_variant_id=q.card_variant_id
      and o.condition_id=v_nm
      and o.source='TCGPlayer'
      and o.currency='USD'
      and o.market_price>0
      and o.created_at<=e.source_updated_at
      and o.captured_at<=p_market_date
    order by o.captured_at desc,o.created_at desc,o.id desc
    limit 1
  ) o on true
  where e.market_scope='standard'
    and q.market_scope='standard'
    and q.card_variant_id is not null
    and o.market_price is not null;

  create index on _raw_leaf_rewind(root_set_id,canonical_card_id);
  analyze _raw_leaf_rewind;

  drop table if exists pg_temp._raw_leaf_asof;
  create temp table _raw_leaf_asof on commit drop as
  select
    e.market_key,e.root_set_id,x.member_set_id,e.market_scope,
    x.canonical_card_id,x.card_variant_id,
    x.market_price,x.observed_date,
    'TCGPlayer'::text as source,
    null::uuid as source_observation_id,
    null::timestamptz as source_observation_created_at,
    'standard_asof_v2'::text as reconstruction_method
  from _raw_leaf_expected e
  cross join lateral public.get_pokemon_market_root_standard_card_prices_as_of_v2(
    e.root_set_id,p_market_date
  ) x
  where e.market_scope='standard'
    and x.card_variant_id is not null
    and x.market_price is not null
    and x.market_price>0;

  create index on _raw_leaf_asof(root_set_id,canonical_card_id);
  analyze _raw_leaf_asof;

  drop table if exists pg_temp._raw_leaf_choice;
  create temp table _raw_leaf_choice on commit drop as
  with rewind_rollup as (
    select root_set_id,count(*)::integer n,round(sum(market_price),2) value
    from _raw_leaf_rewind group by root_set_id
  ), asof_rollup as (
    select root_set_id,count(*)::integer n,round(sum(market_price),2) value
    from _raw_leaf_asof group by root_set_id
  )
  select
    e.market_key,e.root_set_id,e.expected_count,e.expected_value,
    case
      when rw.n=e.expected_count and rw.value=round(e.expected_value,2)
        then 'timestamp_rewind_v1'
      when av.n=e.expected_count and av.value=round(e.expected_value,2)
        then 'standard_asof_v2'
      else null
    end reconstruction_method
  from _raw_leaf_expected e
  left join rewind_rollup rw using(root_set_id)
  left join asof_rollup av using(root_set_id)
  where e.market_scope='standard';

  select count(*)::integer into v_unresolved
  from _raw_leaf_choice where reconstruction_method is null;
  if v_unresolved<>0 then
    raise exception 'RAW_LEAF_STANDARD_RECONSTRUCTION_UNRESOLVED: %',v_unresolved;
  end if;

  select count(*) filter(where reconstruction_method='timestamp_rewind_v1')::integer,
         count(*) filter(where reconstruction_method='standard_asof_v2')::integer
  into v_rewind_roots,v_asof_roots
  from _raw_leaf_choice;

  drop table if exists pg_temp._raw_leaf_selected;
  create temp table _raw_leaf_selected (
    market_key text,
    root_set_id uuid,
    member_set_id uuid,
    market_scope text,
    canonical_card_id uuid,
    card_variant_id uuid,
    market_price numeric,
    observed_date date,
    source text,
    source_observation_id uuid,
    source_observation_created_at timestamptz,
    reconstruction_method text
  ) on commit drop;

  insert into _raw_leaf_selected
  select r.*
  from _raw_leaf_rewind r
  join _raw_leaf_choice c using(root_set_id)
  where c.reconstruction_method='timestamp_rewind_v1';

  insert into _raw_leaf_selected
  select a.*
  from _raw_leaf_asof a
  join _raw_leaf_choice c using(root_set_id)
  where c.reconstruction_method='standard_asof_v2';

  insert into _raw_leaf_selected
  select
    e.market_key,e.root_set_id,x.member_set_id,e.market_scope,
    x.canonical_card_id,x.card_variant_id,
    x.market_price,x.observed_date,
    'TCGPlayer'::text,
    null::uuid,null::timestamptz,
    'edition_asof_v2'::text
  from _raw_leaf_expected e
  cross join lateral public.get_pokemon_edition_history_card_prices_as_of_v2(
    e.root_set_id,p_market_date,false
  ) x
  where e.market_scope in ('first_edition','unlimited','shadowless')
    and x.market_scope=e.market_scope
    and x.card_variant_id is not null
    and x.market_price is not null
    and x.market_price>0;

  select count(*)::integer into v_scoped_markets
  from _raw_leaf_expected
  where market_scope in ('first_edition','unlimited','shadowless');

  create index on _raw_leaf_selected(market_key,canonical_card_id);
  analyze _raw_leaf_selected;

  with rollup as (
    select market_key,count(*)::integer n,round(sum(market_price),2) value
    from _raw_leaf_selected
    group by market_key
  )
  select count(*)::integer into v_bad_markets
  from _raw_leaf_expected e
  left join rollup r using(market_key)
  where r.market_key is null
     or r.n<>e.expected_count
     or r.value<>round(e.expected_value,2);

  if v_bad_markets<>0 then
    raise exception 'RAW_LEAF_MARKET_RECONCILIATION_FAILED: %',v_bad_markets;
  end if;

  select count(*)::integer into v_duplicate_variants
  from (
    select card_variant_id
    from _raw_leaf_selected
    group by card_variant_id
    having count(*)>1
  ) d;
  if v_duplicate_variants<>0 then
    raise exception 'RAW_LEAF_DUPLICATE_VARIANTS: %',v_duplicate_variants;
  end if;

  select count(*)::integer,coalesce(sum(market_price),0)::numeric
  into v_leaf_count,v_leaf_value
  from _raw_leaf_selected;

  if v_leaf_count<>v_raw.card_count then
    raise exception 'RAW_LEAF_TOTAL_COUNT_MISMATCH: leaves % expected %',
      v_leaf_count,v_raw.card_count;
  end if;
  if round(v_leaf_value,2)<>round(v_raw.basket_value,2) then
    raise exception 'RAW_LEAF_TOTAL_VALUE_MISMATCH: leaves % expected %',
      round(v_leaf_value,2),round(v_raw.basket_value,2);
  end if;

  delete from public.pokemon_market_raw_edition_stable_leaf_history_v1
  where market_date=p_market_date;

  insert into public.pokemon_market_raw_edition_stable_leaf_history_v1(
    market_date,market_key,root_set_id,member_set_id,market_scope,
    canonical_card_id,card_variant_id,market_price,observed_date,source,
    source_observation_id,source_observation_created_at,reconstruction_method,
    raw_source_generation_fingerprint
  )
  select
    p_market_date,l.market_key,l.root_set_id,l.member_set_id,l.market_scope,
    l.canonical_card_id,l.card_variant_id,l.market_price,l.observed_date,l.source,
    l.source_observation_id,l.source_observation_created_at,l.reconstruction_method,
    v_raw.source_generation_fingerprint
  from _raw_leaf_selected l;

  return jsonb_build_object(
    'status','complete',
    'marketDate',p_market_date,
    'leafCount',v_leaf_count,
    'leafValue',round(v_leaf_value,2),
    'marketCount',(select count(*) from _raw_leaf_expected),
    'standardTimestampRewindRoots',v_rewind_roots,
    'standardAsofRoots',v_asof_roots,
    'scopedMarkets',v_scoped_markets,
    'rawSourceGenerationFingerprint',v_raw.source_generation_fingerprint
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_raw_edition_stable_leaves_v1(date)
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_raw_edition_stable_leaves_v1(date)
to service_role;

create or replace function public.stage_pokemon_market_explorer_raw_surface_v2(
  p_generation_id uuid,
  p_market_date date,
  p_methodology_version text
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path=''
set statement_timeout='120s'
as $function$
declare
  v_current public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
  v_hist integer;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_duplicate_count integer;
  v_fp_ok boolean;
begin
  select * into v_current
  from public.pokemon_market_raw_edition_stable_daily_history_v1
  where market_date=p_market_date;

  if not found then
    raise exception 'RAW_EDITION_STABLE_CURRENT_DATE_MISSING';
  end if;
  if coalesce(v_current.methodology_version,'')<>'edition_stable_market_identity_chain_v1' then
    raise exception 'RAW_EDITION_STABLE_METHODOLOGY_UNEXPECTED: %',
      coalesce(v_current.methodology_version,'null');
  end if;

  select count(*)::integer,coalesce(sum(l.market_price),0)::numeric,
         coalesce(bool_and(l.raw_source_generation_fingerprint=v_current.source_generation_fingerprint),false)
  into v_leaf_count,v_leaf_value,v_fp_ok
  from public.pokemon_market_raw_edition_stable_leaf_history_v1 l
  where l.market_date=p_market_date;

  if v_leaf_count<>v_current.card_count or not v_fp_ok then
    raise exception 'RAW_EDITION_STABLE_LEAF_SIDECAR_MISSING_OR_STALE: leaves % expected %',
      v_leaf_count,v_current.card_count;
  end if;
  if round(v_leaf_value,2)<>round(v_current.basket_value,2) then
    raise exception 'RAW_EDITION_STABLE_LEAF_VALUE_MISMATCH: leaves % expected %',
      round(v_leaf_value,2),round(v_current.basket_value,2);
  end if;

  select count(*)::integer into v_duplicate_count
  from (
    select card_variant_id
    from public.pokemon_market_raw_edition_stable_leaf_history_v1
    where market_date=p_market_date
    group by card_variant_id having count(*)>1
  ) d;
  if v_duplicate_count<>0 then
    raise exception 'RAW_EDITION_STABLE_DUPLICATE_INSTRUMENTS: %',v_duplicate_count;
  end if;

  delete from public.pokemon_market_explorer_surface_constituents_v2
   where generation_id=p_generation_id and market_key='raw';
  delete from public.pokemon_market_explorer_surface_constituent_totals_v2
   where generation_id=p_generation_id and market_key='raw';
  delete from public.pokemon_market_explorer_surface_history_v2
   where generation_id=p_generation_id and market_key='raw';
  delete from public.pokemon_market_explorer_surface_directory_v2
   where generation_id=p_generation_id and market_key='raw';

  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    source_as_of,current_tracked_value,current_index_value,
    history_available,history_start_date,history_end_date,history_point_count,
    constituent_count,composition_kind,availability,unavailable_reason,
    definition_version,screen_group,screen_eligible,metadata
  )
  select
    p_generation_id,'raw','cards','parent','Raw Card Market','Raw Card Market',
    'pokemon_market_raw_edition_stable_daily_history_v1',
    p_market_date,
    v_current.basket_value,v_current.normalized_index_value,
    true,min(h.market_date),max(h.market_date),count(*)::integer,
    v_leaf_count,'index_and_composition','available',null,
    v_current.methodology_version,'card',false,
    jsonb_build_object(
      'editionStable',true,
      'indexConstituentKind','set_market_identity',
      'compositionConstituentKind','card_variant',
      'indexMethod','market-identity-chain-linked-common-cohort',
      'vintageScopesSeparate',true,
      'legacyGenericVintageExcluded',true,
      'rawIndexMarketCount',v_current.market_count,
      'rawIndexRootCount',v_current.root_count,
      'rawIndexCardCount',v_current.card_count,
      'compositionLeafCount',v_leaf_count,
      'leafAuthority','pokemon_market_raw_edition_stable_leaf_history_v1',
      'legacyFrozenMethodologyVersion',p_methodology_version,
      'authorityRefreshInsideStage',false
    )
  from public.pokemon_market_raw_edition_stable_daily_history_v1 h
  where h.market_date<=p_market_date;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select
    p_generation_id,'raw',h.market_date,h.normalized_index_value,h.basket_value,h.card_count,0
  from public.pokemon_market_raw_edition_stable_daily_history_v1 h
  where h.market_date<=p_market_date
  order by h.market_date;
  get diagnostics v_hist=row_count;

  insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  ) values (
    p_generation_id,'raw','cards',v_leaf_count,'available',null
  );

  insert into public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  select
    p_generation_id,'raw',
    row_number() over(order by l.market_price desc,l.card_variant_id)::integer,
    l.card_variant_id::text,
    'cards',
    case when l.market_scope='standard' then coalesce(l.member_set_id,l.root_set_id) else l.root_set_id end,
    l.market_price,
    p_market_date,
    jsonb_build_object(
      'asset','cards',
      'instrumentId',l.card_variant_id,
      'cardVariantId',l.card_variant_id,
      'canonicalCardId',l.canonical_card_id,
      'setId',case when l.market_scope='standard' then coalesce(l.member_set_id,l.root_set_id) else l.root_set_id end,
      'rootSetId',l.root_set_id,
      'memberSetId',l.member_set_id,
      'marketScope',l.market_scope,
      'name',cc.name,
      'cardName',cc.name,
      'cardNumber',coalesce(cc.number,cc.printed_number),
      'rarity',cc.rarity,
      'edition',case
        when l.market_scope='first_edition' then '1st-edition'
        when l.market_scope in ('unlimited','shadowless') then l.market_scope
        else m.edition
      end,
      'setName',coalesce(member.name,root.name),
      'printingType',coalesce(cv.printing_type,m.printing_type),
      'specialType',coalesce(cv.special_type,m.special_type),
      'marketPrice',l.market_price,
      'priceAsOf',p_market_date,
      'asOf',p_market_date,
      'sourceDate',l.observed_date,
      'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url),
      'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
      'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url),
      'sourceMarketKey',l.market_key,
      'identitySource',l.reconstruction_method,
      'parentMarketKey','raw'
    )
  from public.pokemon_market_raw_edition_stable_leaf_history_v1 l
  join public.pokemon_canonical_cards cc on cc.id=l.canonical_card_id
  left join public.card_variants cv on cv.id=l.card_variant_id
  left join public.pokemon_market_explorer_card_current_metadata m
    on m.card_variant_id=l.card_variant_id
  left join public.sets root on root.id=l.root_set_id
  left join public.sets member on member.id=l.member_set_id
  where l.market_date=p_market_date;

  return jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'historyRows',v_hist,
    'compositionLeafCount',v_leaf_count,
    'compositionValue',round(v_leaf_value,2),
    'editionStable',true,
    'leafAuthority','pokemon_market_raw_edition_stable_leaf_history_v1',
    'authorityRefreshInsideStage',false
  );
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
to service_role;

commit;
