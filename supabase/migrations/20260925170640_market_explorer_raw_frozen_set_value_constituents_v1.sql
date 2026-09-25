-- Freeze exact Set Value leaf rosters for Raw Market composition.
-- This closes the gap where current/latest card authorities can drift from the
-- exact physical basket used by a persisted Raw Set Value publication.
--
-- The Set Value application publisher already computes the exact canonical ->
-- physical variant rows while calculating each root Set Value.  It should call
-- replace_pokemon_market_set_value_constituents_v1() with that in-memory roster.
-- Raw composition then becomes a cheap generation-time union over frozen rows,
-- with exact count/value reconciliation against the persisted Raw index.

begin;

create table if not exists public.pokemon_market_set_value_constituent_publications_v1 (
  root_set_id uuid not null,
  market_date date not null,
  methodology_version text not null,
  expected_set_value numeric not null check (expected_set_value >= 0),
  expected_card_count integer not null check (expected_card_count >= 0),
  constituent_value numeric not null default 0,
  constituent_count integer not null default 0 check (constituent_count >= 0),
  roster_fingerprint text,
  source text not null,
  status text not null check (status in ('BUILDING','READY')),
  published_at timestamptz not null default clock_timestamp(),
  primary key (root_set_id,market_date,methodology_version)
);

create table if not exists public.pokemon_market_set_value_constituents_v1 (
  root_set_id uuid not null,
  market_date date not null,
  methodology_version text not null,
  canonical_card_id uuid not null,
  card_variant_id uuid not null,
  set_id uuid not null,
  market_price numeric not null check (market_price > 0),
  captured_at date,
  price_source text,
  printing_type text,
  price_selection_reason text,
  primary key (root_set_id,market_date,methodology_version,canonical_card_id),
  unique (root_set_id,market_date,methodology_version,card_variant_id),
  foreign key (root_set_id,market_date,methodology_version)
    references public.pokemon_market_set_value_constituent_publications_v1(
      root_set_id,market_date,methodology_version
    ) on delete cascade
);

create index if not exists pokemon_market_set_value_constituents_v1_date_root_idx
  on public.pokemon_market_set_value_constituents_v1(
    market_date,methodology_version,root_set_id,canonical_card_id
  )
  include (card_variant_id,set_id,market_price,captured_at,price_source,printing_type);

create index if not exists pokemon_market_set_value_constituents_v1_variant_idx
  on public.pokemon_market_set_value_constituents_v1(
    card_variant_id,market_date,methodology_version,root_set_id
  );

alter table public.pokemon_market_set_value_constituent_publications_v1 enable row level security;
alter table public.pokemon_market_set_value_constituents_v1 enable row level security;

revoke all on
  public.pokemon_market_set_value_constituent_publications_v1,
  public.pokemon_market_set_value_constituents_v1
from public,anon,authenticated;

grant select,insert,update,delete on
  public.pokemon_market_set_value_constituent_publications_v1,
  public.pokemon_market_set_value_constituents_v1
to service_role;

create or replace function public.replace_pokemon_market_set_value_constituents_v1(
  p_root_set_id uuid,
  p_market_date date,
  p_methodology_version text,
  p_expected_set_value numeric,
  p_expected_card_count integer,
  p_source text,
  p_items jsonb
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '10s'
set lock_timeout = '2s'
as $function$
declare
  v_count integer;
  v_value numeric;
  v_fingerprint text;
  v_lock_key bigint;
begin
  if p_root_set_id is null
     or p_market_date is null
     or nullif(pg_catalog.btrim(coalesce(p_methodology_version,'')),'') is null
     or p_expected_set_value is null
     or p_expected_set_value < 0
     or p_expected_card_count is null
     or p_expected_card_count < 0
     or nullif(pg_catalog.btrim(coalesce(p_source,'')),'') is null
     or p_items is null
     or jsonb_typeof(p_items) <> 'array'
  then
    raise exception 'SET_VALUE_CONSTITUENT_PUBLICATION_ARGUMENTS_INVALID';
  end if;

  if jsonb_array_length(p_items) <> p_expected_card_count then
    raise exception 'SET_VALUE_CONSTITUENT_COUNT_MISMATCH';
  end if;

  if p_expected_card_count > 2000 then
    raise exception 'SET_VALUE_CONSTITUENT_COUNT_TOO_LARGE';
  end if;

  v_lock_key := pg_catalog.hashtextextended(
    p_root_set_id::text || ':' || p_market_date::text || ':' || p_methodology_version,
    0
  );
  perform pg_catalog.pg_advisory_xact_lock(v_lock_key);

  delete from public.pokemon_market_set_value_constituent_publications_v1
  where root_set_id=p_root_set_id
    and market_date=p_market_date
    and methodology_version=p_methodology_version;

  insert into public.pokemon_market_set_value_constituent_publications_v1(
    root_set_id,market_date,methodology_version,
    expected_set_value,expected_card_count,source,status
  ) values (
    p_root_set_id,p_market_date,p_methodology_version,
    p_expected_set_value,p_expected_card_count,p_source,'BUILDING'
  );

  insert into public.pokemon_market_set_value_constituents_v1(
    root_set_id,market_date,methodology_version,
    canonical_card_id,card_variant_id,set_id,market_price,captured_at,
    price_source,printing_type,price_selection_reason
  )
  select
    p_root_set_id,p_market_date,p_methodology_version,
    (x->>'canonicalCardId')::uuid,
    (x->>'cardVariantId')::uuid,
    (x->>'setId')::uuid,
    (x->>'marketPrice')::numeric,
    nullif(x->>'capturedAt','')::date,
    nullif(x->>'source',''),
    nullif(x->>'printingType',''),
    nullif(x->>'priceSelectionReason','')
  from jsonb_array_elements(p_items) x
  where x ? 'canonicalCardId'
    and x ? 'cardVariantId'
    and x ? 'setId'
    and x ? 'marketPrice'
    and (x->>'marketPrice')::numeric > 0;

  get diagnostics v_count=row_count;

  if v_count <> p_expected_card_count then
    raise exception 'SET_VALUE_CONSTITUENT_VALID_ROW_COUNT_MISMATCH';
  end if;

  if exists (
    select 1
    from public.pokemon_market_set_value_constituents_v1 c
    where c.root_set_id=p_root_set_id
      and c.market_date=p_market_date
      and c.methodology_version=p_methodology_version
      and c.set_id<>p_root_set_id
      and not exists (
        select 1
        from public.sets s
        where s.id=c.set_id
          and s.parent_opening_set_id=p_root_set_id
          and coalesce(s.counts_toward_parent_set_value,false)
          and not coalesce(s.catalog_only,false)
      )
  ) then
    raise exception 'SET_VALUE_CONSTITUENT_MEMBER_SET_OUTSIDE_ROOT';
  end if;

  select
    count(*)::integer,
    coalesce(sum(round(c.market_price,2)),0),
    md5(string_agg(
      c.canonical_card_id::text || ':' ||
      c.card_variant_id::text || ':' ||
      round(c.market_price,2)::text,
      '|' order by c.canonical_card_id
    ))
  into v_count,v_value,v_fingerprint
  from public.pokemon_market_set_value_constituents_v1 c
  where c.root_set_id=p_root_set_id
    and c.market_date=p_market_date
    and c.methodology_version=p_methodology_version;

  if v_count<>p_expected_card_count then
    raise exception 'SET_VALUE_CONSTITUENT_FINAL_COUNT_MISMATCH';
  end if;

  if round(v_value,2)<>round(p_expected_set_value,2) then
    raise exception 'SET_VALUE_CONSTITUENT_VALUE_MISMATCH';
  end if;

  update public.pokemon_market_set_value_constituent_publications_v1
  set constituent_count=v_count,
      constituent_value=v_value,
      roster_fingerprint=v_fingerprint,
      status='READY',
      published_at=clock_timestamp()
  where root_set_id=p_root_set_id
    and market_date=p_market_date
    and methodology_version=p_methodology_version;

  return jsonb_build_object(
    'rootSetId',p_root_set_id,
    'marketDate',p_market_date,
    'methodologyVersion',p_methodology_version,
    'status','READY',
    'constituentCount',v_count,
    'constituentValue',v_value,
    'rosterFingerprint',v_fingerprint
  );
end;
$function$;

revoke all on function public.replace_pokemon_market_set_value_constituents_v1(
  uuid,date,text,numeric,integer,text,jsonb
) from public,anon,authenticated;
grant execute on function public.replace_pokemon_market_set_value_constituents_v1(
  uuid,date,text,numeric,integer,text,jsonb
) to service_role;

alter table public.pokemon_market_explorer_raw_composition_v1
  add column if not exists source_date date,
  add column if not exists price_source text,
  add column if not exists price_selection_reason text;

create or replace function public.stage_pokemon_market_explorer_raw_composition_v1(
  p_generation_id uuid,
  p_market_date date,
  p_methodology_version text
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '30s'
set lock_timeout = '2s'
as $function$
declare
  v_raw public.pokemon_market_index_daily_history%rowtype;
  v_value numeric;
  v_count integer;
  v_expected_roots integer;
  v_ready_roots integer;
  v_status text;
  v_reason text;
begin
  if p_generation_id is null or p_market_date is null
     or nullif(p_methodology_version,'') is null
  then
    raise exception 'RAW_COMPOSITION_ARGUMENTS_REQUIRED';
  end if;

  select * into v_raw
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon'
    and h.index_key='raw'
    and h.market_date=p_market_date
    and h.methodology_version=p_methodology_version
  order by h.updated_at desc
  limit 1;

  if not found then
    raise exception 'RAW_INDEX_ROW_NOT_FOUND';
  end if;

  delete from public.pokemon_market_explorer_raw_composition_runs_v1
  where generation_id=p_generation_id;

  insert into public.pokemon_market_explorer_raw_composition_runs_v1(
    generation_id,market_date,methodology_version,expected_basket_value,
    raw_index_set_count,raw_index_card_count,status
  ) values (
    p_generation_id,p_market_date,p_methodology_version,v_raw.basket_value,
    v_raw.set_count,v_raw.card_count,'STAGING'
  );

  with roots as materialized (
    select
      coalesce(x->>'setId',x->>'set_id')::uuid as root_set_id,
      (x->>'setValue')::numeric as expected_set_value,
      coalesce(x->>'includedCardCount',x->>'cardCount')::integer as expected_card_count
    from jsonb_array_elements(v_raw.constituents_json) x
    where coalesce(x->>'setId',x->>'set_id') is not null
  ), audit as (
    select
      count(*)::integer as expected_roots,
      count(p.root_set_id) filter (
        where p.status='READY'
          and round(p.expected_set_value,2)=round(r.expected_set_value,2)
          and p.expected_card_count=r.expected_card_count
          and round(p.constituent_value,2)=round(r.expected_set_value,2)
          and p.constituent_count=r.expected_card_count
      )::integer as ready_roots
    from roots r
    left join public.pokemon_market_set_value_constituent_publications_v1 p
      on p.root_set_id=r.root_set_id
     and p.market_date=p_market_date
     and p.methodology_version=p_methodology_version
  )
  select expected_roots,ready_roots
  into v_expected_roots,v_ready_roots
  from audit;

  if v_expected_roots<>v_raw.set_count or v_ready_roots<>v_expected_roots then
    v_status:='FAILED_RECONCILIATION';
    v_reason:=format(
      'Frozen Set Value leaf publications incomplete or mismatched: ready %s / expected %s; Raw set count %s',
      coalesce(v_ready_roots,0),coalesce(v_expected_roots,0),v_raw.set_count
    );

    update public.pokemon_market_explorer_raw_composition_runs_v1
    set status=v_status,reason=v_reason,staged_at=clock_timestamp()
    where generation_id=p_generation_id;

    return jsonb_build_object(
      'generationId',p_generation_id,
      'marketDate',p_market_date,
      'methodologyVersion',p_methodology_version,
      'status',v_status,
      'reason',v_reason,
      'readySetValueLeafPublications',coalesce(v_ready_roots,0),
      'expectedSetValueLeafPublications',coalesce(v_expected_roots,0),
      'rawIndexSetCount',v_raw.set_count,
      'rawIndexCardCount',v_raw.card_count
    );
  end if;

  with roots as materialized (
    select coalesce(x->>'setId',x->>'set_id')::uuid as root_set_id
    from jsonb_array_elements(v_raw.constituents_json) x
    where coalesce(x->>'setId',x->>'set_id') is not null
  ), leaves as materialized (
    select
      c.card_variant_id,c.canonical_card_id,c.set_id,c.root_set_id,
      cc.name as card_name,
      coalesce(cc.number,cc.printed_number) as card_number,
      cc.rarity,
      m.edition,
      coalesce(c.printing_type,m.printing_type) as printing_type,
      m.special_type,
      c.market_price,p_market_date as price_as_of,c.captured_at as source_date,
      c.price_source,c.price_selection_reason,
      cv.image_small_url as variant_small,
      cv.image_large_url as variant_large,
      cc.image_small_url as canonical_small,
      cc.image_large_url as canonical_large,
      m.image_url as metadata_image,
      'standard'::text as market_scope
    from roots r
    join public.pokemon_market_set_value_constituents_v1 c
      on c.root_set_id=r.root_set_id
     and c.market_date=p_market_date
     and c.methodology_version=p_methodology_version
    join public.pokemon_canonical_cards cc on cc.id=c.canonical_card_id
    left join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id=c.card_variant_id
    left join public.card_variants cv on cv.id=c.card_variant_id
  ), ranked as (
    select l.*,
      row_number() over(order by l.market_price desc,l.card_variant_id)::integer as rank
    from leaves l
  )
  insert into public.pokemon_market_explorer_raw_composition_v1(
    generation_id,rank,card_variant_id,canonical_card_id,set_id,root_set_id,market_scope,
    card_name,card_number,rarity,edition,printing_type,special_type,
    market_price,price_as_of,image_url,image_small_url,image_large_url,
    source_date,price_source,price_selection_reason
  )
  select
    p_generation_id,r.rank,r.card_variant_id,r.canonical_card_id,r.set_id,r.root_set_id,
    r.market_scope,r.card_name,r.card_number,r.rarity,r.edition,r.printing_type,r.special_type,
    r.market_price,r.price_as_of,
    coalesce(r.variant_small,r.canonical_small,r.variant_large,r.canonical_large,r.metadata_image),
    coalesce(r.variant_small,r.canonical_small),
    coalesce(r.variant_large,r.canonical_large),
    r.source_date,r.price_source,r.price_selection_reason
  from ranked r;

  select coalesce(sum(round(market_price,2)),0),count(*)::integer
  into v_value,v_count
  from public.pokemon_market_explorer_raw_composition_v1
  where generation_id=p_generation_id;

  if round(v_value,2)=round(v_raw.basket_value,2)
     and v_count=v_raw.card_count
  then
    v_status:='READY';
    v_reason:=null;
  else
    v_status:='FAILED_RECONCILIATION';
    v_reason:=format(
      'Raw frozen composition did not reconcile: value %s vs %s; leaf count %s vs raw card count %s',
      round(v_value,2),round(v_raw.basket_value,2),v_count,v_raw.card_count
    );
  end if;

  update public.pokemon_market_explorer_raw_composition_runs_v1
  set composition_basket_value=v_value,
      composition_leaf_count=v_count,
      status=v_status,
      reason=v_reason,
      staged_at=clock_timestamp()
  where generation_id=p_generation_id;

  return jsonb_build_object(
    'generationId',p_generation_id,
    'marketDate',p_market_date,
    'methodologyVersion',p_methodology_version,
    'status',v_status,
    'reason',v_reason,
    'rawIndexSetCount',v_raw.set_count,
    'rawIndexCardCount',v_raw.card_count,
    'compositionLeafCount',v_count,
    'expectedBasketValue',v_raw.basket_value,
    'compositionBasketValue',v_value,
    'readySetValueLeafPublications',v_ready_roots
  );
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_raw_composition_v1(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_raw_composition_v1(uuid,date,text)
to service_role;

commit;
