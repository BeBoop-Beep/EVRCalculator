-- Market Explorer data-surface expansion: normalized authorities.
-- Forward-only, additive, private-by-default.  No serving pointer is changed here.
-- The interactive readers introduced by the companion migration read only compact,
-- generation-pinned tables; these refresh/staging functions are publication-time work.

begin;

-- ---------------------------------------------------------------------------
-- A. Full card-rarity preparedness registry.
-- ---------------------------------------------------------------------------

create table if not exists public.pokemon_market_explorer_rarity_registry_v1 (
  rarity_key text primary key check (rarity_key <> ''),
  label text not null,
  taxonomy_version text not null,
  current_market_date date,
  current_priced_card_count integer not null default 0 check (current_priced_card_count >= 0),
  represented_set_count integer not null default 0 check (represented_set_count >= 0),
  image_count integer not null default 0 check (image_count >= 0),
  history_start_date date,
  history_end_date date,
  history_point_count integer not null default 0 check (history_point_count >= 0),
  eligibility_state text not null default 'UNAVAILABLE'
    check (eligibility_state in (
      'PREPARED','CUSTOM_BUILD_AVAILABLE','INSUFFICIENT_COHORT',
      'INSUFFICIENT_HISTORY','UNAVAILABLE'
    )),
  prepared_market_key text,
  reason text,
  audited_at timestamptz not null default clock_timestamp()
);

alter table public.pokemon_market_explorer_rarity_registry_v1 enable row level security;
revoke all on public.pokemon_market_explorer_rarity_registry_v1 from public, anon, authenticated;
grant select, insert, update, delete on public.pokemon_market_explorer_rarity_registry_v1 to service_role;

insert into public.pokemon_market_explorer_rarity_registry_v1
  (rarity_key,label,taxonomy_version,reason)
values
  ('aceSpecRare','ACE SPEC Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('amazingRare','Amazing Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('blackWhiteRare','Black White Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('classicCollection','Classic Collection','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('common','Common','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('doubleRare','Double Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('holoRare','Holo Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('hyperRare','Hyper Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('illustrationRare','Illustration Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('legend','LEGEND','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('megaHyperRare','Mega Hyper Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('megaAttackRare','Mega Attack Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('promo','Promo','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('radiantRare','Radiant Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rare','Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareAce','Rare ACE','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareBreak','Rare BREAK','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHolo','Rare Holo','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloEx','Rare Holo EX','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloGx','Rare Holo GX','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloLvX','Rare Holo LV.X','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloStar','Rare Holo Star','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloV','Rare Holo V','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloVmax','Rare Holo VMAX','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareHoloVstar','Rare Holo VSTAR','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rarePrime','Rare Prime','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rarePrismStar','Rare Prism Star','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareRainbow','Rare Rainbow','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareSecret','Rare Secret','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareShining','Rare Shining','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareShiny','Rare Shiny','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareShinyGx','Rare Shiny GX','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('rareUltra','Rare Ultra','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('shinyRare','Shiny Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('shinyUltraRare','Shiny Ultra Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('specialIllustrationRare','Special Illustration Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('trainerGalleryRareHolo','Trainer Gallery Rare Holo','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('ultraRare','Ultra Rare','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited'),
  ('uncommon','Uncommon','pokemon-card-rarity-filter-taxonomy-v1','Not yet audited')
on conflict (rarity_key) do update
set label=excluded.label, taxonomy_version=excluded.taxonomy_version;

create or replace function public.refresh_pokemon_market_explorer_rarity_registry_v1(
  p_market_date date default null
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '120s'
as $function$
declare
  v_market_date date;
  v_rows integer;
begin
  select coalesce(
    p_market_date,
    max(d.market_date) filter (where q.status in ('READY','LEGACY_VERIFIED'))
  )
  into v_market_date
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d
  left join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=d.market_date;

  if v_market_date is null then
    raise exception 'RARITY_AUDIT_NO_ACCEPTED_MARKET_DATE';
  end if;

  with current_stats as materialized (
    select
      public.market_explorer_filter_rarity_key(m.rarity) as rarity_key,
      count(*)::integer as card_count,
      count(distinct m.set_id)::integer as set_count,
      count(*) filter (
        where coalesce(
          cv.image_small_url, cc.image_small_url,
          cv.image_large_url, cc.image_large_url, m.image_url
        ) is not null
      )::integer as image_count
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id=d.card_variant_id
    left join public.card_variants cv on cv.id=m.card_variant_id
    left join public.pokemon_canonical_cards cc on cc.id=m.canonical_card_id
    where d.market_date=v_market_date
      and d.market_price>0
    group by public.market_explorer_filter_rarity_key(m.rarity)
  ),
  history_stats as materialized (
    select
      public.market_explorer_filter_rarity_key(m.rarity) as rarity_key,
      min(d.market_date) as history_start,
      max(d.market_date) as history_end,
      count(distinct d.market_date)::integer as history_points
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id=d.card_variant_id
    join public.pokemon_market_date_quality q
      on q.tcg='pokemon' and q.market_date=d.market_date
     and q.status in ('READY','LEGACY_VERIFIED')
    where d.market_price>0
    group by public.market_explorer_filter_rarity_key(m.rarity)
  ),
  prepared as (
    select distinct on (coalesce(
      nullif(d.metadata->>'rarityKey',''),
      nullif(d.metadata->>'segmentKey',''),
      nullif(d.metadata->>'filterRarityKey','')
    ))
      coalesce(
        nullif(d.metadata->>'rarityKey',''),
        nullif(d.metadata->>'segmentKey',''),
        nullif(d.metadata->>'segmentId',''),
        nullif(d.metadata->>'filterRarityKey','')
      ) as rarity_key,
      d.market_key
    from public.pokemon_market_explorer_prepared_directory_v1 d
    where d.asset='cards' and d.market_type='prepared_rarity'
    order by coalesce(
      nullif(d.metadata->>'rarityKey',''),
      nullif(d.metadata->>'segmentKey',''),
      nullif(d.metadata->>'segmentId',''),
      nullif(d.metadata->>'filterRarityKey','')
    ), d.market_key
  )
  update public.pokemon_market_explorer_rarity_registry_v1 r
  set
    current_market_date=v_market_date,
    current_priced_card_count=coalesce(c.card_count,0),
    represented_set_count=coalesce(c.set_count,0),
    image_count=coalesce(c.image_count,0),
    history_start_date=h.history_start,
    history_end_date=h.history_end,
    history_point_count=coalesce(h.history_points,0),
    prepared_market_key=p.market_key,
    eligibility_state=case
      when p.market_key is not null then 'PREPARED'
      when coalesce(c.card_count,0) < 25 or coalesce(c.set_count,0) < 3
        then 'INSUFFICIENT_COHORT'
      when coalesce(h.history_points,0) < 2 or h.history_end is distinct from v_market_date
        then 'INSUFFICIENT_HISTORY'
      when coalesce(c.card_count,0) > 0
        then 'CUSTOM_BUILD_AVAILABLE'
      else 'UNAVAILABLE'
    end,
    reason=case
      when p.market_key is not null then 'Maintained prepared market is published'
      when coalesce(c.card_count,0) < 25 or coalesce(c.set_count,0) < 3
        then format('Below 25-card / 3-set cross-market gate (%s cards, %s sets)',
                    coalesce(c.card_count,0),coalesce(c.set_count,0))
      when coalesce(h.history_points,0) < 2
        then 'Fewer than two accepted history dates'
      when h.history_end is distinct from v_market_date
        then 'History does not reach the audited market date'
      when coalesce(c.card_count,0)>0
        then 'Cohort is eligible for a prepared candidate; candidate publication is separate'
      else 'No current positively priced constituents'
    end,
    audited_at=clock_timestamp()
  from current_stats c
  full join history_stats h using (rarity_key)
  left join prepared p using (rarity_key)
  where r.rarity_key=coalesce(c.rarity_key,h.rarity_key,p.rarity_key);

  get diagnostics v_rows=row_count;

  -- Taxonomy rows with no data are intentionally retained as truthful unavailable options.
  update public.pokemon_market_explorer_rarity_registry_v1 r
  set current_market_date=v_market_date,
      current_priced_card_count=0,represented_set_count=0,image_count=0,
      history_start_date=null,history_end_date=null,history_point_count=0,
      prepared_market_key=null,eligibility_state='UNAVAILABLE',
      reason='No current positively priced constituents',
      audited_at=clock_timestamp()
  where not exists (
    select 1
    from public.pokemon_market_explorer_card_current_metadata m
    where public.market_explorer_filter_rarity_key(m.rarity)=r.rarity_key
  );

  return jsonb_build_object(
    'marketDate',v_market_date,
    'taxonomyVersion','pokemon-card-rarity-filter-taxonomy-v1',
    'registryRows',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1),
    'prepared',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1 where eligibility_state='PREPARED'),
    'preparedCandidates',(select count(*) from public.pokemon_market_explorer_rarity_registry_v1 where eligibility_state='CUSTOM_BUILD_AVAILABLE')
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_rarity_registry_v1(date)
from public, anon, authenticated;
grant execute on function public.refresh_pokemon_market_explorer_rarity_registry_v1(date)
to service_role;

-- ---------------------------------------------------------------------------
-- B. Canonical sealed classification and normalized daily authority.
-- Keep the Total Sealed parent retail-only.  Cases/displays remain searchable
-- and buildable but are not silently added to the parent basket.
-- ---------------------------------------------------------------------------

create or replace function public.market_explorer_sealed_product_family_v1(p_name text)
returns text
language plpgsql
immutable
security invoker
set search_path = ''
as $function$
declare
  t text := pg_catalog.lower(pg_catalog.regexp_replace(coalesce(p_name,''), '\s+', ' ', 'g'));
begin
  if t ~ '\mcase\M' then return 'case'; end if;
  if t ~ '\mdisplay\M' then return 'display'; end if;
  if t ~ '\mset of\M' or t ~ '\mart set\M' then return 'multi_product_bundle'; end if;
  if t ~ 'pok[ée]mon center' and t ~ '\melite trainer box\M|\metb\M' then return 'pokemon_center_elite_trainer_box'; end if;
  if t ~ '\melite trainer box\M|\metb\M' then return 'elite_trainer_box'; end if;
  if t ~ '\menhanced booster box\M' then return 'enhanced_booster_box'; end if;
  if t ~ '\mhalf booster box\M' then return 'half_booster_box'; end if;
  if t ~ '\mbooster box\M' then return 'booster_box'; end if;
  if t ~ '\mbuild[ -]?and[ -]?battle\M' and t ~ '\mstadium\M' then return 'build_and_battle_stadium'; end if;
  if t ~ '\mbuild[ -]?and[ -]?battle\M' then return 'build_and_battle_box'; end if;
  if t ~ '\mbooster bundle\M' then return 'booster_bundle'; end if;
  if t ~ '\msleeved\M' and t ~ '\mbooster\M' then return 'sleeved_booster_pack'; end if;
  if t ~ '\mthree[ -]?pack\M|\m3[ -]?pack\M' and t ~ '\mblister\M' then return 'three_pack_blister'; end if;
  if t ~ '\msingle[ -]?pack\M|\mchecklane\M' and t ~ '\mblister\M|\mchecklane\M' then return 'single_pack_blister'; end if;
  if t ~ '\mfun pack\M' then return 'fun_pack'; end if;
  if t ~ '\mbooster pack\M' then return 'loose_booster_pack'; end if;
  if t ~ '\mbundle\M|\mcollection\M|\mtin\M|\mchest\M|\mbox set\M' then return 'collection_product'; end if;
  return 'other';
end;
$function$;

create or replace function public.market_explorer_sealed_family_label_v1(p_family text)
returns text
language sql
immutable
security invoker
set search_path = ''
as $function$
  select case p_family
    when 'booster_box' then 'Booster Box'
    when 'half_booster_box' then 'Half Booster Box'
    when 'enhanced_booster_box' then 'Enhanced Booster Box'
    when 'elite_trainer_box' then 'Elite Trainer Box'
    when 'pokemon_center_elite_trainer_box' then 'Pokémon Center Elite Trainer Box'
    when 'booster_bundle' then 'Booster Bundle'
    when 'loose_booster_pack' then 'Loose Booster Pack'
    when 'sleeved_booster_pack' then 'Sleeved Booster Pack'
    when 'build_and_battle_box' then 'Build & Battle Box'
    when 'build_and_battle_stadium' then 'Build & Battle Stadium'
    when 'three_pack_blister' then 'Three-Pack Blister'
    when 'single_pack_blister' then 'Single-Pack Blister'
    when 'collection_product' then 'Collection Product'
    when 'case' then 'Case'
    when 'display' then 'Display'
    when 'multi_product_bundle' then 'Multi-Product Bundle'
    when 'fun_pack' then 'Fun Pack'
    else 'Other'
  end;
$function$;

create or replace function public.market_explorer_sealed_parent_member_v1(p_family text)
returns boolean
language sql
immutable
security invoker
set search_path = ''
as $function$
  select p_family = any(array[
    'booster_box','half_booster_box','enhanced_booster_box',
    'elite_trainer_box','pokemon_center_elite_trainer_box','booster_bundle',
    'loose_booster_pack','sleeved_booster_pack'
  ]::text[]);
$function$;

create or replace function public.market_explorer_sealed_variant_label_v1(p_name text)
returns text
language sql
immutable
security invoker
set search_path = ''
as $function$
  select nullif(
    pg_catalog.substring(
      coalesce(p_name,''),
      '[[]([^]]+)[]][[:space:]]*$'
    ),
    ''
  );
$function$;

create table if not exists public.pokemon_market_explorer_sealed_daily_v1 (
  sealed_product_id text not null,
  market_date date not null,
  market_price numeric not null check (market_price > 0),
  set_id uuid,
  era_id uuid,
  product_family text not null,
  parent_membership boolean not null,
  source text,
  source_observation_id text,
  captured_at timestamptz,
  classification_version text not null,
  refreshed_at timestamptz not null default clock_timestamp(),
  primary key (sealed_product_id, market_date)
);
create index if not exists pokemon_market_explorer_sealed_daily_v1_set_date_idx
  on public.pokemon_market_explorer_sealed_daily_v1(set_id,market_date,sealed_product_id)
  include (market_price,product_family,parent_membership);
create index if not exists pokemon_market_explorer_sealed_daily_v1_era_date_idx
  on public.pokemon_market_explorer_sealed_daily_v1(era_id,market_date,sealed_product_id)
  include (market_price,product_family,parent_membership);
create index if not exists pokemon_market_explorer_sealed_daily_v1_family_date_idx
  on public.pokemon_market_explorer_sealed_daily_v1(product_family,market_date,sealed_product_id)
  include (market_price,parent_membership);
create index if not exists pokemon_market_explorer_sealed_daily_v1_date_idx
  on public.pokemon_market_explorer_sealed_daily_v1(market_date,sealed_product_id)
  include (market_price,set_id,era_id,product_family,parent_membership);

alter table public.pokemon_market_explorer_sealed_daily_v1 enable row level security;
revoke all on public.pokemon_market_explorer_sealed_daily_v1 from public, anon, authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_sealed_daily_v1 to service_role;

create table if not exists public.pokemon_market_explorer_sealed_current_metadata_v1 (
  sealed_product_id text primary key,
  set_id uuid,
  era_id uuid,
  name text not null,
  set_name text,
  era_name text,
  product_family text not null,
  product_family_label text not null,
  variant_label text,
  is_case boolean not null,
  is_display boolean not null,
  is_bulk_container boolean not null,
  is_multi_product_bundle boolean not null,
  parent_membership boolean not null,
  classification_version text not null,
  image_small_url text,
  image_large_url text,
  latest_market_date date,
  latest_market_price numeric,
  search_text text not null,
  updated_at timestamptz not null default clock_timestamp()
);
create index if not exists pokemon_market_explorer_sealed_meta_set_family_idx
  on public.pokemon_market_explorer_sealed_current_metadata_v1(set_id,product_family,sealed_product_id);
create index if not exists pokemon_market_explorer_sealed_meta_era_family_idx
  on public.pokemon_market_explorer_sealed_current_metadata_v1(era_id,product_family,sealed_product_id);
create index if not exists pokemon_market_explorer_sealed_meta_family_current_idx
  on public.pokemon_market_explorer_sealed_current_metadata_v1(product_family,latest_market_date,sealed_product_id)
  include (latest_market_price,set_id,era_id,parent_membership);
create index if not exists pokemon_market_explorer_sealed_meta_search_prefix_idx
  on public.pokemon_market_explorer_sealed_current_metadata_v1
  (pg_catalog.lower(search_text) text_pattern_ops);

alter table public.pokemon_market_explorer_sealed_current_metadata_v1 enable row level security;
revoke all on public.pokemon_market_explorer_sealed_current_metadata_v1 from public, anon, authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_sealed_current_metadata_v1 to service_role;

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
    public.market_explorer_sealed_parent_member_v1(r.product_family),
    r.source,r.source_observation_id,r.captured_at,
    'sealed-product-classification-v3-loose-pack-family',clock_timestamp()
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
    (f.family in ('case','display') or pg_catalog.lower(p.name) ~ '\mcarton\M'),
    f.family='multi_product_bundle',
    public.market_explorer_sealed_parent_member_v1(f.family),
    'sealed-product-classification-v3-loose-pack-family',
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
    'classificationVersion','sealed-product-classification-v3-loose-pack-family',
    'pricedRows',(select count(*) from public.pokemon_market_explorer_sealed_current_metadata_v1 where latest_market_price>0)
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_current_metadata_v1()
to service_role;

create table if not exists public.pokemon_market_explorer_sealed_type_registry_v1 (
  product_family text primary key,
  display_label text not null,
  definition text not null,
  classification_version text not null,
  current_product_count integer not null default 0 check (current_product_count>=0),
  current_priced_count integer not null default 0 check (current_priced_count>=0),
  history_start_date date,
  history_end_date date,
  history_point_count integer not null default 0 check (history_point_count>=0),
  represented_set_count integer not null default 0 check (represented_set_count>=0),
  represented_era_count integer not null default 0 check (represented_era_count>=0),
  eligibility_state text not null default 'UNAVAILABLE'
    check (eligibility_state in (
      'PREPARED','PREPARED_CANDIDATE','SEARCHABLE_BUILDABLE',
      'INSUFFICIENT_HISTORY','UNAVAILABLE'
    )),
  prepared_market_key text,
  parent_membership boolean not null,
  bulk_container boolean not null,
  audited_at timestamptz not null default clock_timestamp()
);
alter table public.pokemon_market_explorer_sealed_type_registry_v1 enable row level security;
revoke all on public.pokemon_market_explorer_sealed_type_registry_v1 from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_sealed_type_registry_v1 to service_role;

insert into public.pokemon_market_explorer_sealed_type_registry_v1
  (product_family,display_label,definition,classification_version,parent_membership,bulk_container)
values
 ('booster_box','Booster Box','Full booster display box','sealed-product-classification-v3-loose-pack-family',true,false),
 ('half_booster_box','Half Booster Box','Half-size booster display box','sealed-product-classification-v3-loose-pack-family',true,false),
 ('enhanced_booster_box','Enhanced Booster Box','Enhanced booster display box','sealed-product-classification-v3-loose-pack-family',true,false),
 ('elite_trainer_box','Elite Trainer Box','Standard Elite Trainer Box','sealed-product-classification-v3-loose-pack-family',true,false),
 ('pokemon_center_elite_trainer_box','Pokémon Center Elite Trainer Box','Pokémon Center exclusive Elite Trainer Box','sealed-product-classification-v3-loose-pack-family',true,false),
 ('booster_bundle','Booster Bundle','Booster bundle','sealed-product-classification-v3-loose-pack-family',true,false),
 ('loose_booster_pack','Loose Booster Pack','Unsleeved individual booster pack','sealed-product-classification-v3-loose-pack-family',true,false),
 ('sleeved_booster_pack','Sleeved Booster Pack','Sleeved individual booster pack','sealed-product-classification-v3-loose-pack-family',true,false),
 ('build_and_battle_box','Build & Battle Box','Build & Battle prerelease box','sealed-product-classification-v3-loose-pack-family',false,false),
 ('build_and_battle_stadium','Build & Battle Stadium','Build & Battle Stadium','sealed-product-classification-v3-loose-pack-family',false,false),
 ('three_pack_blister','Three-Pack Blister','Three-pack blister','sealed-product-classification-v3-loose-pack-family',false,false),
 ('single_pack_blister','Single-Pack Blister','Single-pack or checklane blister','sealed-product-classification-v3-loose-pack-family',false,false),
 ('collection_product','Collection Product','Collection, tin, chest, or box-set product','sealed-product-classification-v3-loose-pack-family',false,false),
 ('case','Case','Bulk case/container packaging level','sealed-product-classification-v3-loose-pack-family',false,true),
 ('display','Display','Bulk display/container packaging level','sealed-product-classification-v3-loose-pack-family',false,true),
 ('multi_product_bundle','Multi-Product Bundle','Set-of or art-set bundle','sealed-product-classification-v3-loose-pack-family',false,false),
 ('fun_pack','Fun Pack','Fun pack','sealed-product-classification-v3-loose-pack-family',false,false),
 ('other','Other','Canonical sealed inventory not classified into a named family','sealed-product-classification-v3-loose-pack-family',false,false)
on conflict (product_family) do update
set display_label=excluded.display_label,definition=excluded.definition,
    classification_version=excluded.classification_version,
    parent_membership=excluded.parent_membership,bulk_container=excluded.bulk_container;

create or replace function public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
declare v_rows integer;
begin
  with meta as (
    select product_family,
      count(*)::integer product_count,
      count(*) filter (where latest_market_price>0)::integer priced_count,
      count(distinct set_id)::integer set_count,
      count(distinct era_id)::integer era_count
    from public.pokemon_market_explorer_sealed_current_metadata_v1
    group by product_family
  ), hist as (
    select product_family,min(market_date) history_start,max(market_date) history_end,
      count(distinct market_date)::integer history_points
    from public.pokemon_market_explorer_sealed_daily_v1
    group by product_family
  ), old_prepared as (
    select
      case d.metadata->>'segmentKey'
        when 'boosterBox' then 'booster_box'
        when 'eliteTrainerBox' then 'elite_trainer_box'
        when 'pokemonCenterEliteTrainerBox' then 'pokemon_center_elite_trainer_box'
        when 'boosterBundle' then 'booster_bundle'
        else null
      end product_family,
      d.market_key
    from public.pokemon_market_explorer_prepared_directory_v1 d
    where d.asset='sealed' and d.market_type='prepared_format'
  )
  update public.pokemon_market_explorer_sealed_type_registry_v1 r
  set current_product_count=coalesce(m.product_count,0),
      current_priced_count=coalesce(m.priced_count,0),
      represented_set_count=coalesce(m.set_count,0),
      represented_era_count=coalesce(m.era_count,0),
      history_start_date=h.history_start,
      history_end_date=h.history_end,
      history_point_count=coalesce(h.history_points,0),
      prepared_market_key=p.market_key,
      eligibility_state=case
        when p.market_key is not null then 'PREPARED'
        when coalesce(m.priced_count,0)=0 then 'UNAVAILABLE'
        when coalesce(h.history_points,0)<2 then 'INSUFFICIENT_HISTORY'
        when coalesce(m.set_count,0)>=2 and coalesce(m.priced_count,0)>=2
          then 'PREPARED_CANDIDATE'
        else 'SEARCHABLE_BUILDABLE'
      end,
      audited_at=clock_timestamp()
  from meta m
  full join hist h using(product_family)
  left join old_prepared p using(product_family)
  where r.product_family=coalesce(m.product_family,h.product_family,p.product_family);
  get diagnostics v_rows=row_count;

  update public.pokemon_market_explorer_sealed_type_registry_v1 r
  set current_product_count=0,current_priced_count=0,represented_set_count=0,represented_era_count=0,
      history_start_date=null,history_end_date=null,history_point_count=0,
      eligibility_state='UNAVAILABLE',prepared_market_key=null,audited_at=clock_timestamp()
  where not exists (
    select 1 from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where m.product_family=r.product_family
  );

  return jsonb_build_object(
    'rows',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1),
    'updated',v_rows,
    'preparedCandidates',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1 where eligibility_state='PREPARED_CANDIDATE'),
    'parentFamilies',(select count(*) from public.pokemon_market_explorer_sealed_type_registry_v1 where parent_membership)
  );
end;
$function$;

revoke all on function public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
from public,anon,authenticated;
grant execute on function public.refresh_pokemon_market_explorer_sealed_type_registry_v1()
to service_role;

-- ---------------------------------------------------------------------------
-- C. Raw parent composition leaves.  This does NOT change the Raw index.
-- It stages display composition and requires exact reconciliation to the
-- selected persisted Raw index row before the roster can be used.
-- ---------------------------------------------------------------------------

create table if not exists public.pokemon_market_explorer_raw_composition_runs_v1 (
  generation_id uuid primary key,
  market_date date not null,
  methodology_version text not null,
  expected_basket_value numeric not null,
  composition_basket_value numeric,
  raw_index_set_count integer not null,
  raw_index_card_count integer not null,
  composition_leaf_count integer not null default 0,
  status text not null check (status in ('STAGING','READY','FAILED_RECONCILIATION')),
  reason text,
  staged_at timestamptz not null default clock_timestamp()
);

create table if not exists public.pokemon_market_explorer_raw_composition_v1 (
  generation_id uuid not null references public.pokemon_market_explorer_raw_composition_runs_v1(generation_id) on delete cascade,
  rank integer not null check (rank>=1),
  card_variant_id uuid not null,
  canonical_card_id uuid not null,
  set_id uuid not null,
  root_set_id uuid not null,
  market_scope text,
  card_name text,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  market_price numeric not null check (market_price>0),
  price_as_of date not null,
  image_url text,
  image_small_url text,
  image_large_url text,
  primary key (generation_id,rank),
  unique (generation_id,card_variant_id)
);
create index if not exists pokemon_market_explorer_raw_composition_v1_instrument_idx
  on public.pokemon_market_explorer_raw_composition_v1(card_variant_id,generation_id);
create index if not exists pokemon_market_explorer_raw_composition_v1_set_idx
  on public.pokemon_market_explorer_raw_composition_v1(generation_id,root_set_id,set_id,rank);

alter table public.pokemon_market_explorer_raw_composition_runs_v1 enable row level security;
alter table public.pokemon_market_explorer_raw_composition_v1 enable row level security;
revoke all on public.pokemon_market_explorer_raw_composition_runs_v1,
  public.pokemon_market_explorer_raw_composition_v1 from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_raw_composition_runs_v1,
  public.pokemon_market_explorer_raw_composition_v1 to service_role;

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
set statement_timeout = '120s'
as $function$
declare
  v_raw public.pokemon_market_index_daily_history%rowtype;
  v_value numeric;
  v_count integer;
  v_status text;
  v_reason text;
begin
  if p_generation_id is null or p_market_date is null or nullif(p_methodology_version,'') is null then
    raise exception 'RAW_COMPOSITION_ARGUMENTS_REQUIRED';
  end if;

  select * into v_raw
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon' and h.index_key='raw'
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
    select distinct coalesce(x->>'setId',x->>'set_id')::uuid as root_set_id
    from jsonb_array_elements(v_raw.constituents_json) x
    where coalesce(x->>'setId',x->>'set_id') is not null
  ), members as materialized (
    select r.root_set_id,r.root_set_id as set_id from roots r
    union
    select r.root_set_id,s.id
    from roots r
    join public.sets s on s.parent_opening_set_id=r.root_set_id
    where coalesce(s.counts_toward_parent_set_value,false)
      and not coalesce(s.catalog_only,false)
  ), leaves as materialized (
    select
      d.card_variant_id,m.canonical_card_id,d.set_id,mem.root_set_id,
      m.card_name,m.card_number,m.rarity,m.edition,m.printing_type,m.special_type,
      d.market_price,d.market_date,
      cv.image_small_url as variant_small,
      cv.image_large_url as variant_large,
      cc.image_small_url as canonical_small,
      cc.image_large_url as canonical_large,
      m.image_url as metadata_image,
      case
        when exists (
          select 1 from public.pokemon_market_set_scope_contract_v1 c
          where c.set_id=mem.root_set_id and c.market_scope<>'standard'
        ) then
          case m.edition
            when '1st-edition' then 'first_edition'
            when 'shadowless' then 'shadowless'
            when 'unlimited' then 'unlimited'
            else null
          end
        else 'standard'
      end as market_scope
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    join members mem on mem.set_id=d.set_id
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id=d.card_variant_id and m.set_id=d.set_id
    join public.pokemon_canonical_cards cc
      on cc.id=m.canonical_card_id and coalesce(cc.set_value_eligible,false)
    left join public.card_variants cv on cv.id=d.card_variant_id
    where d.market_date=p_market_date and d.market_price>0
  ), ranked as (
    select l.*,row_number() over(order by l.market_price desc,l.card_variant_id)::integer as rank
    from leaves l
  )
  insert into public.pokemon_market_explorer_raw_composition_v1(
    generation_id,rank,card_variant_id,canonical_card_id,set_id,root_set_id,market_scope,
    card_name,card_number,rarity,edition,printing_type,special_type,
    market_price,price_as_of,image_url,image_small_url,image_large_url
  )
  select p_generation_id,r.rank,r.card_variant_id,r.canonical_card_id,r.set_id,r.root_set_id,r.market_scope,
    r.card_name,r.card_number,r.rarity,r.edition,r.printing_type,r.special_type,
    r.market_price,r.market_date,
    coalesce(r.variant_small,r.canonical_small,r.variant_large,r.canonical_large,r.metadata_image),
    coalesce(r.variant_small,r.canonical_small),
    coalesce(r.variant_large,r.canonical_large)
  from ranked r;

  select coalesce(sum(market_price),0),count(*)::integer
  into v_value,v_count
  from public.pokemon_market_explorer_raw_composition_v1
  where generation_id=p_generation_id;

  if round(v_value,2)=round(v_raw.basket_value,2) and v_count=v_raw.card_count then
    v_status:='READY';
    v_reason:=null;
  else
    v_status:='FAILED_RECONCILIATION';
    v_reason:=format(
      'Raw composition did not reconcile: value %s vs %s; leaf count %s vs raw card count %s',
      round(v_value,2),round(v_raw.basket_value,2),v_count,v_raw.card_count
    );
  end if;

  update public.pokemon_market_explorer_raw_composition_runs_v1
  set composition_basket_value=v_value,composition_leaf_count=v_count,
      status=v_status,reason=v_reason,staged_at=clock_timestamp()
  where generation_id=p_generation_id;

  return jsonb_build_object(
    'generationId',p_generation_id,'marketDate',p_market_date,
    'methodologyVersion',p_methodology_version,
    'status',v_status,'reason',v_reason,
    'rawIndexSetCount',v_raw.set_count,
    'rawIndexCardCount',v_raw.card_count,
    'compositionLeafCount',v_count,
    'expectedBasketValue',v_raw.basket_value,
    'compositionBasketValue',v_value
  );
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_raw_composition_v1(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_raw_composition_v1(uuid,date,text)
to service_role;

-- Batch image/identity enrichment for the already-proven compact v3 prepared
-- constituent cache.  It is publication-time only; page reads stay join-free.
create or replace function public.enrich_pokemon_market_explorer_prepared_constituent_images_v1(
  p_generation_id uuid
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
  update public.pokemon_market_explorer_prepared_constituents_v1 p
  set item =
    p.item ||
    jsonb_build_object(
      'asset','cards',
      'instrumentId',p.instrument_id,
      'cardVariantId',cm.card_variant_id,
      'canonicalCardId',cm.canonical_card_id,
      'setId',cm.set_id,
      'name',cm.card_name,
      'cardName',cm.card_name,
      'cardNumber',cm.card_number,
      'rarity',cm.rarity,
      'edition',cm.edition,
      'printingType',cm.printing_type,
      'specialType',cm.special_type,
      'imageUrl',coalesce(
        cv.image_small_url,cc.image_small_url,
        cv.image_large_url,cc.image_large_url,cm.image_url
      ),
      'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
      'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url),
      'priceAsOf',p.price_as_of
    )
  from public.pokemon_market_explorer_card_current_metadata cm
  left join public.card_variants cv on cv.id=cm.card_variant_id
  left join public.pokemon_canonical_cards cc on cc.id=cm.canonical_card_id
  where p.generation_id=p_generation_id
    and p.asset='cards'
    and p.instrument_id=cm.card_variant_id::text;
  get diagnostics v_rows=row_count;

  return jsonb_build_object(
    'generationId',p_generation_id,
    'cardRowsEnriched',v_rows,
    'cardRowsWithImage',(
      select count(*)
      from public.pokemon_market_explorer_prepared_constituents_v1 x
      where x.generation_id=p_generation_id and x.asset='cards'
        and nullif(x.item->>'imageUrl','') is not null
    )
  );
end;
$function$;

revoke all on function public.enrich_pokemon_market_explorer_prepared_constituent_images_v1(uuid)
from public,anon,authenticated;
grant execute on function public.enrich_pokemon_market_explorer_prepared_constituent_images_v1(uuid)
to service_role;

-- ---------------------------------------------------------------------------
-- D. Versioned sealed Quick Market registry: research/proposal only.
-- Nothing here publishes arbitrary thresholds.
-- ---------------------------------------------------------------------------

create table if not exists public.pokemon_market_explorer_sealed_quick_registry_v1 (
  quick_key text primary key,
  label text not null,
  status text not null check (status in ('PROPOSED','APPROVED','REJECTED')),
  definition jsonb not null,
  research_basis jsonb not null default '{}'::jsonb,
  approved_at timestamptz,
  updated_at timestamptz not null default clock_timestamp()
);
alter table public.pokemon_market_explorer_sealed_quick_registry_v1 enable row level security;
revoke all on public.pokemon_market_explorer_sealed_quick_registry_v1 from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_sealed_quick_registry_v1 to service_role;

insert into public.pokemon_market_explorer_sealed_quick_registry_v1(
  quick_key,label,status,definition,research_basis
) values
 ('new-release-sealed','New Release Sealed','PROPOSED',
   '{"dimension":"releaseAge","candidateOnly":true}'::jsonb,
   '{"reason":"Requires live release-age distribution research before approval"}'::jsonb),
 ('established-sealed','Established Sealed','PROPOSED',
   '{"dimension":"releaseAge","candidateOnly":true}'::jsonb,
   '{"reason":"Requires live release-age distribution research before approval"}'::jsonb),
 ('premium-sealed','Premium Sealed','PROPOSED',
   '{"dimension":"priceDistribution","candidateOnly":true}'::jsonb,
   '{"reason":"No arbitrary price threshold is approved"}'::jsonb),
 ('single-pack-market','Single-Pack Market','PROPOSED',
   '{"families":["loose_booster_pack","sleeved_booster_pack"],"candidateOnly":true}'::jsonb,
   '{"reason":"Family-composite semantics require product approval"}'::jsonb),
 ('box-market','Box Market','PROPOSED',
   '{"dimension":"familyComposite","candidateOnly":true}'::jsonb,
   '{"reason":"Unlike product families must not be merged without approval"}'::jsonb)
on conflict (quick_key) do nothing;

-- Readiness only: no Demand Pressure or Fair Value metric rows exist here.
create table if not exists public.pokemon_market_explorer_focus_readiness_v1 (
  feature_key text primary key,
  status text not null,
  required_authority text not null,
  notes text not null,
  updated_at timestamptz not null default clock_timestamp()
);
alter table public.pokemon_market_explorer_focus_readiness_v1 enable row level security;
revoke all on public.pokemon_market_explorer_focus_readiness_v1 from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_explorer_focus_readiness_v1 to service_role;

insert into public.pokemon_market_explorer_focus_readiness_v1(feature_key,status,required_authority,notes)
values
 ('demandPressure','DEMAND_PRESSURE_NOT_READY',
  'Legitimate completed-sale / sold-quantity observations with identity, condition, currency, timestamps and provenance',
  'Active asks/listings are not completed sales and must not be relabeled as demand.'),
 ('indexFairValue','INDEX_FAIR_VALUE_NOT_READY_FOR_PRODUCTION',
  'Frozen validated Fair Value model-run authority with point-in-time card estimates and provenance',
  'Research-only predictions are not a production price authority.')
on conflict (feature_key) do update
set status=excluded.status,required_authority=excluded.required_authority,
    notes=excluded.notes,updated_at=clock_timestamp();

commit;
