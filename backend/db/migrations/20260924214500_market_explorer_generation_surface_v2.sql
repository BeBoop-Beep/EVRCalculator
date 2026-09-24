-- Market Explorer v2 shadow serving surface.
-- Additive/generation-pinned.  This migration creates no public serving promotion.
-- Existing prepared Set/Era/Quick/Rarity math is copied as-is; new Raw
-- composition and normalized sealed/rarity markets are staged beside it.

begin;

create table if not exists public.pokemon_market_explorer_surface_generations_v2 (
  generation_id uuid primary key default gen_random_uuid(),
  base_prepared_generation_id uuid not null,
  market_date date not null,
  raw_methodology_version text not null,
  state text not null
    check (state in ('BUILDING','BUILT','VALIDATED','REJECTED','RETIRED')),
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default clock_timestamp(),
  built_at timestamptz,
  validated_at timestamptz
);

create table if not exists public.pokemon_market_explorer_surface_serving_v2 (
  singleton smallint primary key default 1 check (singleton=1),
  generation_id uuid references public.pokemon_market_explorer_surface_generations_v2(generation_id),
  previous_generation_id uuid references public.pokemon_market_explorer_surface_generations_v2(generation_id),
  promoted_at timestamptz
);

create table if not exists public.pokemon_market_explorer_surface_directory_v2 (
  generation_id uuid not null references public.pokemon_market_explorer_surface_generations_v2(generation_id) on delete cascade,
  market_key text not null check (market_key<>''),
  asset text not null check (asset in ('cards','sealed')),
  scope_kind text not null check (scope_kind in ('parent','set','era','rarity','quick','type')),
  label text not null,
  base_label text,
  source_kind text not null,
  set_id uuid,
  era_id uuid,
  market_scope text,
  taxonomy_key text,
  source_as_of date,
  current_tracked_value numeric,
  current_index_value numeric,
  history_available boolean not null default false,
  history_start_date date,
  history_end_date date,
  history_point_count integer not null default 0 check (history_point_count>=0),
  constituent_count integer not null default 0 check (constituent_count>=0),
  composition_kind text not null default 'index'
    check (composition_kind in ('index','composition','index_and_composition','none')),
  availability text not null default 'available'
    check (availability in ('available','empty','unavailable')),
  unavailable_reason text,
  definition_version text not null,
  return_7d_pct numeric,
  return_30d_pct numeric,
  return_90d_pct numeric,
  return_1y_pct numeric,
  current_drawdown_pct numeric,
  max_drawdown_pct numeric,
  screen_group text,
  screen_eligible boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default clock_timestamp(),
  primary key (generation_id,market_key)
);
create index if not exists pokemon_market_explorer_surface_dir_v2_asset_scope_idx
  on public.pokemon_market_explorer_surface_directory_v2(generation_id,asset,scope_kind,label,market_key);
create index if not exists pokemon_market_explorer_surface_dir_v2_set_idx
  on public.pokemon_market_explorer_surface_directory_v2(generation_id,set_id,market_key)
  where set_id is not null;
create index if not exists pokemon_market_explorer_surface_dir_v2_era_idx
  on public.pokemon_market_explorer_surface_directory_v2(generation_id,era_id,market_key)
  where era_id is not null;

create table if not exists public.pokemon_market_explorer_surface_history_v2 (
  generation_id uuid not null,
  market_key text not null,
  market_date date not null,
  index_value numeric not null check (index_value>0),
  tracked_value numeric,
  constituent_count integer,
  chain_segment_id integer not null default 0,
  primary key (generation_id,market_key,market_date),
  foreign key (generation_id,market_key)
    references public.pokemon_market_explorer_surface_directory_v2(generation_id,market_key)
    on delete cascade
);
create index if not exists pokemon_market_explorer_surface_hist_v2_read_idx
  on public.pokemon_market_explorer_surface_history_v2(generation_id,market_key,market_date)
  include(index_value,tracked_value,constituent_count,chain_segment_id);

create table if not exists public.pokemon_market_explorer_surface_constituent_totals_v2 (
  generation_id uuid not null,
  market_key text not null,
  asset text not null check (asset in ('cards','sealed')),
  total_count integer not null check (total_count>=0),
  availability text not null check (availability in ('available','empty','unavailable')),
  availability_reason text,
  staged_at timestamptz not null default clock_timestamp(),
  primary key (generation_id,market_key),
  foreign key (generation_id,market_key)
    references public.pokemon_market_explorer_surface_directory_v2(generation_id,market_key)
    on delete cascade
);

create table if not exists public.pokemon_market_explorer_surface_constituents_v2 (
  generation_id uuid not null,
  market_key text not null,
  rank integer not null check(rank>=1),
  instrument_id text not null check(instrument_id<>''),
  asset text not null check(asset in ('cards','sealed')),
  set_id uuid,
  market_price numeric,
  price_as_of date,
  item jsonb not null,
  primary key (generation_id,market_key,rank),
  unique (generation_id,market_key,instrument_id),
  foreign key (generation_id,market_key)
    references public.pokemon_market_explorer_surface_constituent_totals_v2(generation_id,market_key)
    on delete cascade
);
create index if not exists pokemon_market_explorer_surface_constituents_v2_instrument_idx
  on public.pokemon_market_explorer_surface_constituents_v2(instrument_id,generation_id,market_key);
create index if not exists pokemon_market_explorer_surface_constituents_v2_set_idx
  on public.pokemon_market_explorer_surface_constituents_v2(generation_id,market_key,set_id,rank)
  where set_id is not null;

create table if not exists public.pokemon_market_explorer_surface_aliases_v2 (
  generation_id uuid not null references public.pokemon_market_explorer_surface_generations_v2(generation_id) on delete cascade,
  alias_key text not null,
  market_key text not null,
  reason text not null,
  primary key(generation_id,alias_key),
  foreign key(generation_id,market_key)
    references public.pokemon_market_explorer_surface_directory_v2(generation_id,market_key)
    on delete cascade
);

alter table public.pokemon_market_explorer_surface_generations_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_serving_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_directory_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_history_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_constituent_totals_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_constituents_v2 enable row level security;
alter table public.pokemon_market_explorer_surface_aliases_v2 enable row level security;

revoke all on
  public.pokemon_market_explorer_surface_generations_v2,
  public.pokemon_market_explorer_surface_serving_v2,
  public.pokemon_market_explorer_surface_directory_v2,
  public.pokemon_market_explorer_surface_history_v2,
  public.pokemon_market_explorer_surface_constituent_totals_v2,
  public.pokemon_market_explorer_surface_constituents_v2,
  public.pokemon_market_explorer_surface_aliases_v2
from public,anon,authenticated;
grant select,insert,update,delete on
  public.pokemon_market_explorer_surface_generations_v2,
  public.pokemon_market_explorer_surface_serving_v2,
  public.pokemon_market_explorer_surface_directory_v2,
  public.pokemon_market_explorer_surface_history_v2,
  public.pokemon_market_explorer_surface_constituent_totals_v2,
  public.pokemon_market_explorer_surface_constituents_v2,
  public.pokemon_market_explorer_surface_aliases_v2
to service_role;

-- ---------------------------------------------------------------------------
-- Copy the current proven prepared surface into a candidate generation.
-- The compact v1 constituent tables are operational authorities in production
-- but were introduced outside older clean-schema trees, so their copy is
-- intentionally dynamic and optional at compile time.
-- ---------------------------------------------------------------------------

create or replace function public.seed_pokemon_market_explorer_surface_from_prepared_v1(
  p_generation_id uuid,
  p_base_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '90s'
as $function$
declare
  v_dir integer;
  v_hist integer;
  v_const integer := 0;
begin
  if exists (
    select 1 from public.pokemon_market_explorer_prepared_directory_v1
    where generation_id<>p_base_generation_id
  ) or not exists (
    select 1 from public.pokemon_market_explorer_prepared_directory_v1
    where generation_id=p_base_generation_id
  ) then
    raise exception 'BASE_PREPARED_GENERATION_MISMATCH';
  end if;

  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    set_id,era_id,market_scope,taxonomy_key,source_as_of,
    current_tracked_value,current_index_value,history_available,
    history_start_date,history_end_date,history_point_count,
    constituent_count,composition_kind,availability,definition_version,
    return_7d_pct,return_30d_pct,return_90d_pct,return_1y_pct,
    current_drawdown_pct,max_drawdown_pct,screen_group,screen_eligible,
    metadata,generated_at
  )
  select
    p_generation_id,d.market_key,d.asset,
    case d.market_type
      when 'set' then 'set'
      when 'era' then 'era'
      when 'curated' then 'quick'
      when 'prepared_rarity' then 'rarity'
      else 'type'
    end,
    d.label,
    coalesce(nullif(d.metadata->>'baseSetName',''),d.label),
    d.source_kind,d.set_id,d.era_id,
    nullif(d.metadata->>'marketScope',''),
    coalesce(nullif(d.metadata->>'rarityKey',''),nullif(d.metadata->>'segmentKey','')),
    d.source_as_of,
    d.comparison_value,d.comparison_index_value,d.history_available,
    d.history_start_date,d.history_end_date,d.history_point_count,
    0,
    case when d.asset='cards' then 'index_and_composition' else 'index' end,
    'available',
    coalesce(nullif(d.metadata->>'definitionVersion',''),d.prepared_series_key),
    d.return_7d_pct,d.return_30d_pct,d.return_90d_pct,d.return_1y_pct,
    d.current_drawdown_pct,d.max_drawdown_pct,d.screen_group,d.screen_eligible,
    d.metadata || jsonb_build_object(
      'basePreparedGenerationId',p_base_generation_id,
      'legacyMarketType',d.market_type,
      'copiedWithoutMathChange',true
    ),
    clock_timestamp()
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.generation_id=p_base_generation_id
    and not (d.asset='sealed' and d.market_type='prepared_format');
  get diagnostics v_dir=row_count;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select p_generation_id,h.market_key,h.market_date,h.index_value,h.tracked_value,null,h.chain_segment_id
  from public.pokemon_market_explorer_prepared_history_v1 h
  join public.pokemon_market_explorer_surface_directory_v2 d
    on d.generation_id=p_generation_id and d.market_key=h.market_key
  where h.generation_id=p_base_generation_id;
  get diagnostics v_hist=row_count;

  if pg_catalog.to_regclass('public.pokemon_market_explorer_prepared_constituent_totals_v1') is not null
     and pg_catalog.to_regclass('public.pokemon_market_explorer_prepared_constituents_v1') is not null then

    execute $copy_totals$
      insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
        generation_id,market_key,asset,total_count,availability,availability_reason
      )
      select $1,t.market_key,t.asset,t.total_count,t.availability,t.availability_reason
      from public.pokemon_market_explorer_prepared_constituent_totals_v1 t
      join public.pokemon_market_explorer_surface_directory_v2 d
        on d.generation_id=$1 and d.market_key=t.market_key
      where t.generation_id=$2
      on conflict (generation_id,market_key) do nothing
    $copy_totals$ using p_generation_id,p_base_generation_id;

    execute $copy_rows$
      insert into public.pokemon_market_explorer_surface_constituents_v2(
        generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
      )
      select
        $1,p.market_key,p.rank,p.instrument_id,p.asset,
        coalesce(cm.set_id,nullif(p.item->>'setId','')::uuid),
        p.market_price,p.price_as_of,
        case when p.asset='cards' then
          p.item || jsonb_build_object(
            'rank',p.rank,
            'asset','cards',
            'instrumentId',p.instrument_id,
            'cardVariantId',cm.card_variant_id,
            'canonicalCardId',cm.canonical_card_id,
            'setId',cm.set_id,
            'setName',s.name,
            'name',cm.card_name,
            'cardName',cm.card_name,
            'cardNumber',cm.card_number,
            'rarity',cm.rarity,
            'edition',cm.edition,
            'printingType',cm.printing_type,
            'specialType',cm.special_type,
            'marketPrice',p.market_price,
            'priceAsOf',p.price_as_of,
            'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,cm.image_url),
            'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
            'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url)
          )
        else p.item end
      from public.pokemon_market_explorer_prepared_constituents_v1 p
      join public.pokemon_market_explorer_surface_directory_v2 d
        on d.generation_id=$1 and d.market_key=p.market_key
      left join public.pokemon_market_explorer_card_current_metadata cm
        on p.asset='cards' and p.instrument_id=cm.card_variant_id::text
      left join public.card_variants cv on cv.id=cm.card_variant_id
      left join public.pokemon_canonical_cards cc on cc.id=cm.canonical_card_id
      left join public.sets s on s.id=cm.set_id
      where p.generation_id=$2
    $copy_rows$ using p_generation_id,p_base_generation_id;
    get diagnostics v_const=row_count;

    update public.pokemon_market_explorer_surface_directory_v2 d
    set constituent_count=t.total_count,
        availability=t.availability,
        unavailable_reason=t.availability_reason
    from public.pokemon_market_explorer_surface_constituent_totals_v2 t
    where d.generation_id=p_generation_id
      and t.generation_id=d.generation_id and t.market_key=d.market_key;
  end if;

  return jsonb_build_object(
    'directoryRows',v_dir,'historyRows',v_hist,'constituentRows',v_const
  );
end;
$function$;

revoke all on function public.seed_pokemon_market_explorer_surface_from_prepared_v1(uuid,uuid)
from public,anon,authenticated;
grant execute on function public.seed_pokemon_market_explorer_surface_from_prepared_v1(uuid,uuid)
to service_role;

-- ---------------------------------------------------------------------------
-- Raw parent: copy the persisted Set-level Raw index unchanged, attach the
-- separately reconciled card-leaf display composition.
-- ---------------------------------------------------------------------------

create or replace function public.stage_pokemon_market_explorer_raw_surface_v2(
  p_generation_id uuid,
  p_market_date date,
  p_methodology_version text
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '120s'
as $function$
declare
  v_stage jsonb;
  v_run public.pokemon_market_explorer_raw_composition_runs_v1%rowtype;
  v_hist integer;
begin
  v_stage:=public.stage_pokemon_market_explorer_raw_composition_v1(
    p_generation_id,p_market_date,p_methodology_version
  );
  select * into v_run
  from public.pokemon_market_explorer_raw_composition_runs_v1
  where generation_id=p_generation_id;

  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    source_as_of,current_tracked_value,current_index_value,
    history_available,history_start_date,history_end_date,history_point_count,
    constituent_count,composition_kind,availability,unavailable_reason,
    definition_version,screen_group,screen_eligible,metadata
  )
  select
    p_generation_id,'raw','cards','parent','Raw Card Market','Raw Card Market',
    'pokemon_market_index_daily_history',
    p_market_date,
    current_row.basket_value,current_row.normalized_index_value,
    true,
    min(h.market_date),max(h.market_date),count(*)::integer,
    v_run.composition_leaf_count,'index_and_composition',
    case when v_run.status='READY' then 'available' else 'unavailable' end,
    v_run.reason,
    p_methodology_version,'card',false,
    jsonb_build_object(
      'indexConstituentKind','set_value',
      'compositionConstituentKind','card_variant',
      'indexMethod','set-level-chain-linked-common-cohort',
      'compositionIsDisplayRosterNotIndexMethod',true,
      'rawIndexSetCount',v_run.raw_index_set_count,
      'rawIndexCardCount',v_run.raw_index_card_count,
      'compositionLeafCount',v_run.composition_leaf_count
    )
  from public.pokemon_market_index_daily_history h
  cross join lateral (
    select x.*
    from public.pokemon_market_index_daily_history x
    where x.tcg='pokemon' and x.index_key='raw'
      and x.market_date=p_market_date and x.methodology_version=p_methodology_version
    order by x.updated_at desc limit 1
  ) current_row
  join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=h.market_date
   and q.status in ('READY','LEGACY_VERIFIED')
  where h.tcg='pokemon' and h.index_key='raw'
    and h.methodology_version=p_methodology_version and h.market_date<=p_market_date
  group by current_row.basket_value,current_row.normalized_index_value;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select p_generation_id,'raw',h.market_date,h.normalized_index_value,h.basket_value,h.card_count,0
  from public.pokemon_market_index_daily_history h
  join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=h.market_date
   and q.status in ('READY','LEGACY_VERIFIED')
  where h.tcg='pokemon' and h.index_key='raw'
    and h.methodology_version=p_methodology_version
    and h.market_date<=p_market_date
  order by h.market_date;
  get diagnostics v_hist=row_count;

  insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  ) values (
    p_generation_id,'raw','cards',v_run.composition_leaf_count,
    case when v_run.status='READY' and v_run.composition_leaf_count>0 then 'available'
         when v_run.status='READY' then 'empty' else 'unavailable' end,
    v_run.reason
  );

  insert into public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  select
    p_generation_id,'raw',r.rank,r.card_variant_id::text,'cards',r.set_id,r.market_price,r.price_as_of,
    jsonb_build_object(
      'rank',r.rank,'asset','cards',
      'instrumentId',r.card_variant_id,
      'cardVariantId',r.card_variant_id,
      'canonicalCardId',r.canonical_card_id,
      'setId',r.set_id,'rootSetId',r.root_set_id,'marketScope',r.market_scope,
      'name',r.card_name,'cardName',r.card_name,'cardNumber',r.card_number,
      'rarity',r.rarity,'edition',r.edition,'printingType',r.printing_type,
      'specialType',r.special_type,'marketPrice',r.market_price,
      'priceAsOf',r.price_as_of,'imageUrl',r.image_url,
      'imageSmallUrl',r.image_small_url,'imageLargeUrl',r.image_large_url
    )
  from public.pokemon_market_explorer_raw_composition_v1 r
  where r.generation_id=p_generation_id and v_run.status='READY';

  return v_stage || jsonb_build_object('historyRows',v_hist);
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
to service_role;

-- ---------------------------------------------------------------------------
-- Newly eligible rarity markets.  The nine legacy prepared rarity markets are
-- copied without math changes; only registry rows not already prepared enter
-- this candidate lane.
-- ---------------------------------------------------------------------------

create or replace function public.stage_pokemon_market_explorer_rarity_candidates_v2(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '180s'
set work_mem = '64MB'
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
    on public.market_explorer_filter_rarity_key(m.rarity)=r.rarity_key
  join public.pokemon_market_explorer_card_daily_states_v2_shadow d
    on d.card_variant_id=m.card_variant_id and d.set_id=m.set_id
  join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=d.market_date
   and q.status in ('READY','LEGACY_VERIFIED')
  where r.eligibility_state='CUSTOM_BUILD_AVAILABLE'
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
  ), linked as (
    select
      dt.rarity_key,dt.market_key,dt.market_date,dt.prev_date,
      count(cur.card_variant_id)::integer constituent_count,
      sum(cur.market_price)::numeric basket_value,
      count(prev.card_variant_id)::integer common_count,
      coalesce(sum(cur.market_price) filter(where prev.card_variant_id is not null),0)::numeric common_current,
      coalesce(sum(prev.market_price),0)::numeric common_previous
    from dates dt
    join _mx_rarity_members cur
      on cur.rarity_key=dt.rarity_key and cur.market_date=dt.market_date
    left join _mx_rarity_members prev
      on prev.rarity_key=cur.rarity_key and prev.market_date=dt.prev_date
     and prev.card_variant_id=cur.card_variant_id
    group by dt.rarity_key,dt.market_key,dt.market_date,dt.prev_date
  ), ratios as (
    select l.*,
      case when l.prev_date is not null and l.common_count>0 and l.common_previous>0
        then l.common_current/l.common_previous end link_ratio,
      case when l.prev_date is null or l.common_count=0 or l.common_previous<=0 then 1 else 0 end break_flag
    from linked l
  ), segments as (
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

-- ---------------------------------------------------------------------------
-- Complete sealed lattice: parent, Set, Era, every canonical Type, and the
-- intentionally documented Packs composite.  Bulk families are excluded from
-- the Total Sealed parent but remain their own discoverable/buildable markets.
-- ---------------------------------------------------------------------------

create or replace function public.stage_pokemon_market_explorer_sealed_lattice_v2(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '240s'
set work_mem = '64MB'
as $function$
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
    i.set_id,i.era_id,i.product_family,i.parent_membership
  from intervals i
  cross join lateral generate_series(
    i.market_date,
    least(p_market_date,i.next_date-1),
    interval '1 day'
  ) g(day);
  create index on _mx_sealed_dense(market_date,sealed_product_id);
  create index on _mx_sealed_dense(product_family,market_date,sealed_product_id);
  create index on _mx_sealed_dense(set_id,market_date,sealed_product_id);
  create index on _mx_sealed_dense(era_id,market_date,sealed_product_id);
  analyze _mx_sealed_dense;

  drop table if exists pg_temp._mx_sealed_members;
  create temp table _mx_sealed_members on commit drop as
  select 'sealedMarket'::text market_key,'parent'::text scope_kind,null::uuid set_id,null::uuid era_id,
         null::text taxonomy_key,d.*
  from _mx_sealed_dense d where d.parent_membership
  union all
  select 'sealed-set:'||d.set_id::text,'set',d.set_id,null::uuid,null::text,d.*
  from _mx_sealed_dense d where d.parent_membership and d.set_id is not null
  union all
  select 'sealed-era:'||d.era_id::text,'era',null::uuid,d.era_id,null::text,d.*
  from _mx_sealed_dense d where d.parent_membership and d.era_id is not null
  union all
  select 'sealed-type:'||d.product_family,'type',null::uuid,null::uuid,d.product_family,d.*
  from _mx_sealed_dense d
  union all
  select 'sealed-type:packs','type',null::uuid,null::uuid,'packs',d.*
  from _mx_sealed_dense d
  where d.product_family in ('loose_booster_pack','sleeved_booster_pack');

  create index on _mx_sealed_members(market_key,market_date,sealed_product_id);
  analyze _mx_sealed_members;

  -- Directory identities are determined from current-date membership, never by
  -- scanning history in the interactive reader.
  with current_stats as (
    select market_key,scope_kind,max(set_id) set_id,max(era_id) era_id,max(taxonomy_key) taxonomy_key,
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
    'sealed-surface-v2-dense-point-in-time-chain',
    'sealed',
    c.scope_kind='type',
    jsonb_build_object(
      'parentMembershipRule',
        case when c.market_key='sealedMarket' or c.scope_kind in ('set','era')
          then 'retail_overview_families_only' else 'type_specific' end,
      'bulkContainersExcludedFromTotalSealed',true,
      'classificationVersion','sealed-product-classification-v3-loose-pack-family',
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
         and rr.eligibility_state in ('PREPARED','PREPARED_CANDIDATE','SEARCHABLE_BUILDABLE')
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
    m.sealed_product_id,'sealed',m.set_id,m.market_price,m.market_date,
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
  from public.pokemon_market_explorer_prepared_directory_v1 d
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
$function$;

revoke all on function public.stage_pokemon_market_explorer_sealed_lattice_v2(uuid,date)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_sealed_lattice_v2(uuid,date)
to service_role;

-- Metrics exactly follow the current prepared-directory calendar-boundary rule:
-- an N-day return is available only when an observation exists on exactly N
-- elapsed calendar days before the shared comparison watermark.
create or replace function public.finalize_pokemon_market_explorer_surface_metrics_v2(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
declare v_rows integer;
begin
  with running as (
    select h.*,
      max(h.index_value) over(
        partition by h.generation_id,h.market_key
        order by h.market_date rows unbounded preceding
      ) running_high
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id
  ), stats as (
    select market_key,
      min(market_date) history_start,max(market_date) history_end,
      count(*)::integer point_count,
      max(index_value) filter(where market_date=p_market_date) end_index,
      max(tracked_value) filter(where market_date=p_market_date) end_tracked,
      max(constituent_count) filter(where market_date=p_market_date) end_count,
      max(index_value) filter(where market_date=p_market_date-7) b7,
      max(index_value) filter(where market_date=p_market_date-30) b30,
      max(index_value) filter(where market_date=p_market_date-90) b90,
      max(index_value) filter(where market_date=p_market_date-365) b365,
      max(index_value) since_high,
      min((index_value/nullif(running_high,0)-1.0)*100.0) max_drawdown
    from running
    group by market_key
  )
  update public.pokemon_market_explorer_surface_directory_v2 d
  set current_tracked_value=s.end_tracked,
      current_index_value=s.end_index,
      history_available=(s.end_index is not null),
      history_start_date=s.history_start,history_end_date=s.history_end,
      history_point_count=s.point_count,
      constituent_count=coalesce(s.end_count,d.constituent_count),
      return_7d_pct=case when s.end_index is not null and s.b7 is not null then (s.end_index/s.b7-1.0)*100.0 end,
      return_30d_pct=case when s.end_index is not null and s.b30 is not null then (s.end_index/s.b30-1.0)*100.0 end,
      return_90d_pct=case when s.end_index is not null and s.b90 is not null then (s.end_index/s.b90-1.0)*100.0 end,
      return_1y_pct=case when s.end_index is not null and s.b365 is not null then (s.end_index/s.b365-1.0)*100.0 end,
      current_drawdown_pct=case when s.end_index is not null and s.since_high>0 then (s.end_index/s.since_high-1.0)*100.0 end,
      max_drawdown_pct=s.max_drawdown
  from stats s
  where d.generation_id=p_generation_id and d.market_key=s.market_key;
  get diagnostics v_rows=row_count;
  return jsonb_build_object('updatedMarkets',v_rows);
end;
$function$;

revoke all on function public.finalize_pokemon_market_explorer_surface_metrics_v2(uuid,date)
from public,anon,authenticated;
grant execute on function public.finalize_pokemon_market_explorer_surface_metrics_v2(uuid,date)
to service_role;

-- ---------------------------------------------------------------------------
-- Candidate orchestration.  Heavy work is serialized and publication-time;
-- no interactive request calls this function.
-- ---------------------------------------------------------------------------

create or replace function public.build_pokemon_market_explorer_surface_candidate_v2(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '300s'
as $function$
declare
  v_generation uuid:=gen_random_uuid();
  v_min_sealed date;
  v_max_sealed date;
  v_seed jsonb;
  v_raw jsonb;
  v_rarity jsonb;
  v_sealed jsonb;
  v_metrics jsonb;
begin
  if p_base_generation_id is null or p_market_date is null or nullif(p_raw_methodology_version,'') is null then
    raise exception 'SURFACE_CANDIDATE_ARGUMENTS_REQUIRED';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  insert into public.pokemon_market_explorer_surface_generations_v2(
    generation_id,base_prepared_generation_id,market_date,raw_methodology_version,state
  ) values (
    v_generation,p_base_generation_id,p_market_date,p_raw_methodology_version,'BUILDING'
  );

  v_seed:=public.seed_pokemon_market_explorer_surface_from_prepared_v1(
    v_generation,p_base_generation_id
  );

  select
    (select min(o.captured_at::date) from public.sealed_product_price_observations o),
    (select max(d.market_date) from public.pokemon_market_explorer_sealed_daily_v1 d)
  into v_min_sealed,v_max_sealed;

  if v_min_sealed is not null and (v_max_sealed is null or v_max_sealed<p_market_date) then
    perform public.refresh_pokemon_market_explorer_sealed_daily_v1(
      case when v_max_sealed is null then v_min_sealed else v_max_sealed+1 end,
      p_market_date
    );
  end if;

  perform public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();
  perform public.refresh_pokemon_market_explorer_sealed_type_registry_v1();
  perform public.refresh_pokemon_market_explorer_rarity_registry_v1(p_market_date);

  v_raw:=public.stage_pokemon_market_explorer_raw_surface_v2(
    v_generation,p_market_date,p_raw_methodology_version
  );
  v_rarity:=public.stage_pokemon_market_explorer_rarity_candidates_v2(
    v_generation,p_market_date
  );
  v_sealed:=public.stage_pokemon_market_explorer_sealed_lattice_v2(
    v_generation,p_market_date
  );
  v_metrics:=public.finalize_pokemon_market_explorer_surface_metrics_v2(
    v_generation,p_market_date
  );

  update public.pokemon_market_explorer_surface_generations_v2
  set state='BUILT',built_at=clock_timestamp(),
      diagnostics=jsonb_build_object(
        'seed',v_seed,'raw',v_raw,'rarity',v_rarity,'sealed',v_sealed,'metrics',v_metrics
      )
  where generation_id=v_generation;

  return jsonb_build_object(
    'generationId',v_generation,'state','BUILT',
    'marketDate',p_market_date,'seed',v_seed,'raw',v_raw,
    'rarity',v_rarity,'sealed',v_sealed,'metrics',v_metrics
  );
exception when others then
  -- The caller transaction is expected to roll back.  Re-raise with the
  -- original SQLSTATE so no partially built generation can be promoted.
  raise;
end;
$function$;

revoke all on function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
to service_role;

-- ---------------------------------------------------------------------------
-- Validation/promotion.  Promotion is intentionally separate and is NOT called
-- by this migration.
-- ---------------------------------------------------------------------------

create or replace function public.validate_pokemon_market_explorer_surface_candidate_v2(
  p_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
declare
  v_state text;
  v_market_date date;
  v_issues jsonb:='[]'::jsonb;
  v_n integer;
begin
  select state,market_date into v_state,v_market_date
  from public.pokemon_market_explorer_surface_generations_v2
  where generation_id=p_generation_id
  for update;

  if not found or v_state not in ('BUILT','VALIDATED','REJECTED') then
    raise exception 'SURFACE_GENERATION_NOT_BUILT';
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id and d.history_available
    and not exists (
      select 1 from public.pokemon_market_explorer_surface_history_v2 h
      where h.generation_id=d.generation_id and h.market_key=d.market_key
        and h.market_date=v_market_date
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','HISTORY_NOT_CURRENT','count',v_n));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituent_totals_v2 t
  left join lateral (
    select count(*)::integer n,max(rank)::integer mx,count(distinct instrument_id)::integer instruments
    from public.pokemon_market_explorer_surface_constituents_v2 c
    where c.generation_id=t.generation_id and c.market_key=t.market_key
  ) x on true
  where t.generation_id=p_generation_id
    and (
      (t.availability='available' and (x.n<>t.total_count or x.mx<>t.total_count or x.instruments<>t.total_count))
      or (t.availability='empty' and x.n<>0)
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','CONSTITUENT_PAGING_INVARIANT','count',v_n));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id
    and d.composition_kind in ('composition','index_and_composition')
    and not exists (
      select 1 from public.pokemon_market_explorer_surface_constituent_totals_v2 t
      where t.generation_id=d.generation_id and t.market_key=d.market_key
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','MISSING_CONSTITUENT_TOTAL','count',v_n));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_raw_composition_runs_v1 r
  where r.generation_id=p_generation_id and r.status<>'READY';
  if v_n>0 or not exists (
    select 1 from public.pokemon_market_explorer_raw_composition_runs_v1
    where generation_id=p_generation_id and status='READY'
  ) then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','RAW_COMPOSITION_NOT_RECONCILED'));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituents_v2 c
  join public.pokemon_market_explorer_card_current_metadata m
    on c.asset='cards' and c.instrument_id=m.card_variant_id::text
  left join public.card_variants cv on cv.id=m.card_variant_id
  left join public.pokemon_canonical_cards cc on cc.id=m.canonical_card_id
  where c.generation_id=p_generation_id
    and coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url) is not null
    and nullif(c.item->>'imageUrl','') is null;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','CARD_IMAGE_DROPPED','count',v_n));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituents_v2 c
  where c.generation_id=p_generation_id and c.market_key='sealedMarket'
    and (c.item->>'isBulkContainer')::boolean is true;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','TOTAL_SEALED_CONTAINS_BULK_CONTAINER','count',v_n));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_history_v2 h
  where h.generation_id=p_generation_id and h.market_date>v_market_date;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','FUTURE_LOOKAHEAD','count',v_n));
  end if;

  update public.pokemon_market_explorer_surface_generations_v2
  set state=case when jsonb_array_length(v_issues)=0 then 'VALIDATED' else 'REJECTED' end,
      validated_at=clock_timestamp(),
      diagnostics=diagnostics||jsonb_build_object('validationIssues',v_issues)
  where generation_id=p_generation_id;

  return jsonb_build_object(
    'generationId',p_generation_id,
    'state',case when jsonb_array_length(v_issues)=0 then 'VALIDATED' else 'REJECTED' end,
    'issues',v_issues,
    'directoryRows',(select count(*) from public.pokemon_market_explorer_surface_directory_v2 where generation_id=p_generation_id),
    'historyRows',(select count(*) from public.pokemon_market_explorer_surface_history_v2 where generation_id=p_generation_id),
    'constituentRows',(select count(*) from public.pokemon_market_explorer_surface_constituents_v2 where generation_id=p_generation_id)
  );
end;
$function$;

revoke all on function public.validate_pokemon_market_explorer_surface_candidate_v2(uuid)
from public,anon,authenticated;
grant execute on function public.validate_pokemon_market_explorer_surface_candidate_v2(uuid)
to service_role;

create or replace function public.promote_pokemon_market_explorer_surface_v2(
  p_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '10s'
as $function$
declare v_old uuid;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );
  if not exists (
    select 1 from public.pokemon_market_explorer_surface_generations_v2
    where generation_id=p_generation_id and state='VALIDATED'
  ) then
    raise exception 'ONLY_VALIDATED_SURFACE_GENERATIONS_MAY_BE_PROMOTED';
  end if;
  select generation_id into v_old
  from public.pokemon_market_explorer_surface_serving_v2 where singleton=1
  for update;

  insert into public.pokemon_market_explorer_surface_serving_v2(
    singleton,generation_id,previous_generation_id,promoted_at
  ) values (1,p_generation_id,v_old,clock_timestamp())
  on conflict(singleton) do update
  set previous_generation_id=public.pokemon_market_explorer_surface_serving_v2.generation_id,
      generation_id=excluded.generation_id,promoted_at=excluded.promoted_at;

  return jsonb_build_object('generationId',p_generation_id,'previousGenerationId',v_old);
end;
$function$;

revoke all on function public.promote_pokemon_market_explorer_surface_v2(uuid)
from public,anon,authenticated;
grant execute on function public.promote_pokemon_market_explorer_surface_v2(uuid)
to service_role;

create or replace function public.rollback_pokemon_market_explorer_surface_v2()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '10s'
as $function$
declare v_cur uuid; v_prev uuid;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );
  select generation_id,previous_generation_id into v_cur,v_prev
  from public.pokemon_market_explorer_surface_serving_v2 where singleton=1
  for update;
  if v_prev is null then raise exception 'NO_SURFACE_ROLLBACK_GENERATION'; end if;
  if not exists (
    select 1 from public.pokemon_market_explorer_surface_generations_v2
    where generation_id=v_prev and state='VALIDATED'
  ) then raise exception 'ROLLBACK_GENERATION_NOT_VALIDATED'; end if;

  update public.pokemon_market_explorer_surface_serving_v2
  set generation_id=v_prev,previous_generation_id=v_cur,promoted_at=clock_timestamp()
  where singleton=1;
  return jsonb_build_object('generationId',v_prev,'previousGenerationId',v_cur);
end;
$function$;

revoke all on function public.rollback_pokemon_market_explorer_surface_v2()
from public,anon,authenticated;
grant execute on function public.rollback_pokemon_market_explorer_surface_v2()
to service_role;

-- ---------------------------------------------------------------------------
-- Bounded generic readers.  These are private service-role contracts; frontend
-- never learns market-type-specific SQL and no page recomputes membership.
-- ---------------------------------------------------------------------------

create or replace function public.get_pokemon_market_explorer_surface_directory_v2()
returns setof public.pokemon_market_explorer_surface_directory_v2
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
as $function$
  select d.*
  from public.pokemon_market_explorer_surface_serving_v2 s
  join public.pokemon_market_explorer_surface_directory_v2 d
    on d.generation_id=s.generation_id
  where s.singleton=1
  order by
    case d.asset when 'cards' then 1 when 'sealed' then 2 else 9 end,
    case d.scope_kind
      when 'parent' then 1 when 'era' then 2 when 'set' then 3
      when 'quick' then 4 when 'rarity' then 5 when 'type' then 6 else 9 end,
    d.label,d.market_key;
$function$;

create or replace function public.get_pokemon_market_explorer_surface_history_v2(
  p_market_keys text[],
  p_start_date date default null
)
returns setof public.pokemon_market_explorer_surface_history_v2
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '3s'
as $function$
declare v_generation uuid;
begin
  if p_market_keys is null or cardinality(p_market_keys)<1 or cardinality(p_market_keys)>50 then
    raise exception 'SURFACE_HISTORY_REQUIRES_1_TO_50_KEYS';
  end if;
  select generation_id into v_generation
  from public.pokemon_market_explorer_surface_serving_v2 where singleton=1;
  return query
  select h.*
  from public.pokemon_market_explorer_surface_history_v2 h
  where h.generation_id=v_generation
    and h.market_key=any(p_market_keys)
    and (p_start_date is null or h.market_date>=p_start_date)
  order by array_position(p_market_keys,h.market_key),h.market_date;
end;
$function$;

create or replace function public.get_pokemon_market_explorer_surface_constituents_v2(
  p_market_key text,
  p_generation_id uuid,
  p_after_rank integer default 0,
  p_limit integer default 100
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '2s'
as $function$
declare
  v_key text;
  v_total public.pokemon_market_explorer_surface_constituent_totals_v2%rowtype;
  v_rows jsonb;
begin
  if p_market_key is null or p_generation_id is null then
    raise exception 'MARKET_AND_GENERATION_REQUIRED';
  end if;
  if coalesce(p_after_rank,0)<0 or p_limit<1 or p_limit>100 then
    raise exception 'CONSTITUENT_PAGE_LIMIT_1_TO_100';
  end if;

  select coalesce(a.market_key,p_market_key) into v_key
  from (select p_market_key as k) x
  left join public.pokemon_market_explorer_surface_aliases_v2 a
    on a.generation_id=p_generation_id and a.alias_key=p_market_key;

  select * into v_total
  from public.pokemon_market_explorer_surface_constituent_totals_v2
  where generation_id=p_generation_id and market_key=v_key;

  if not found then
    return jsonb_build_object(
      'marketKey',v_key,'generationId',p_generation_id,
      'availability','unavailable','reason','COMPOSITION_NOT_AVAILABLE',
      'totalCount',0,'rows','[]'::jsonb
    );
  end if;

  select coalesce(jsonb_agg(c.item order by c.rank),'[]'::jsonb)
  into v_rows
  from public.pokemon_market_explorer_surface_constituents_v2 c
  where c.generation_id=p_generation_id and c.market_key=v_key
    and c.rank>coalesce(p_after_rank,0)
    and c.rank<=coalesce(p_after_rank,0)+p_limit;

  return jsonb_build_object(
    'marketKey',v_key,'requestedMarketKey',p_market_key,
    'generationId',p_generation_id,'availability',v_total.availability,
    'reason',v_total.availability_reason,'totalCount',v_total.total_count,
    'afterRank',coalesce(p_after_rank,0),'limit',p_limit,'rows',v_rows
  );
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_surface_directory_v2()
from public,anon,authenticated;
revoke all on function public.get_pokemon_market_explorer_surface_history_v2(text[],date)
from public,anon,authenticated;
revoke all on function public.get_pokemon_market_explorer_surface_constituents_v2(text,uuid,integer,integer)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_surface_directory_v2()
to service_role;
grant execute on function public.get_pokemon_market_explorer_surface_history_v2(text[],date)
to service_role;
grant execute on function public.get_pokemon_market_explorer_surface_constituents_v2(text,uuid,integer,integer)
to service_role;

commit;
