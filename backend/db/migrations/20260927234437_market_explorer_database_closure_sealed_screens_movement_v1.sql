begin;

-- Mirrors production migration 20260927234437:
-- market_explorer_database_closure_sealed_screens_movement_v1.
-- Keep consumer parent markets broad (all ordinary retail sealed products)
-- while excluding only bulk/container packaging.

create or replace function public.market_explorer_sealed_product_family_v2(p_name text)
returns text
language plpgsql
immutable
security invoker
set search_path = ''
as $function$
declare
  t text := pg_catalog.lower(pg_catalog.regexp_replace(coalesce(p_name,''), '\\s+', ' ', 'g'));
begin
  if t ~ '\m(master[[:space:]]+)?carton\M' then return 'master_carton'; end if;
  if t ~ '\mcase\M' then return 'case'; end if;
  if t ~ '\mdisplay\M' then return 'display'; end if;
  if t ~ 'pok[ée]mon center' and t ~ '\melite trainer box\M|\metb\M' then return 'pokemon_center_elite_trainer_box'; end if;
  if t ~ '\melite trainer box\M|\metb\M' then return 'elite_trainer_box'; end if;
  if t ~ '\menhanced booster box\M' then return 'enhanced_booster_box'; end if;
  if t ~ '\mhalf booster box\M' then return 'half_booster_box'; end if;
  if t ~ '\mbooster box\M' then return 'booster_box'; end if;
  if t ~ '\mbuild[[:space:]]*(&|and)[[:space:]]*battle\M' and t ~ '\mstadium\M' then return 'build_and_battle_stadium'; end if;
  if t ~ '\mbuild[[:space:]]*(&|and)[[:space:]]*battle\M' then return 'build_and_battle_box'; end if;
  if t ~ '\mbooster bundle\M' then return 'booster_bundle'; end if;
  if t ~ '\msleeved\M' and t ~ '\mbooster\M' then return 'sleeved_booster_pack'; end if;
  if t ~ '\mthree[ -]?pack\M|\m3[ -]?pack\M' and t ~ '\mblister\M' then return 'three_pack_blister'; end if;
  if t ~ '\m(two|2)[ -]?pack\M' and t ~ '\mblister\M' then return 'two_pack_blister'; end if;
  if t ~ '\msingle[ -]?pack\M|\mchecklane\M' and t ~ '\mblister\M|\mchecklane\M' then return 'single_pack_blister'; end if;
  if t ~ '\mblister\M' then return 'other_blister'; end if;
  if t ~ '\mfun pack\M' then return 'fun_pack'; end if;
  if t ~ '\multra[- ]premium collection\M|\mupc\M' then return 'ultra_premium_collection'; end if;
  if t ~ '\msuper[- ]premium collection\M|\mspc\M' then return 'super_premium_collection'; end if;
  if t ~ '\mpremium collection\M' then return 'premium_collection'; end if;
  if t ~ '\mmini tins?\M' then return 'mini_tin'; end if;
  if t ~ '\mtins?\M' then return 'tin'; end if;
  if t ~ '\mchests?\M' then return 'chest'; end if;
  if t ~ '\mworld championship deck\M' then return 'world_championship_deck'; end if;
  if t ~ '\mtheme deck\M' then return 'theme_deck'; end if;
  if t ~ '\m(league[[:space:]]+)?battle deck\M|\mv battle deck\M|\mex battle deck\M' then return 'battle_deck'; end if;
  if t ~ '\mcollection box\M|\mcollector.?s box\M' then return 'collection_box'; end if;
  if t ~ '\mtrainer.?s toolkit\M' then return 'trainers_toolkit'; end if;
  if t ~ '\mbinders?\M' then return 'binder'; end if;
  if t ~ '\mposters?\M' then return 'poster'; end if;
  if t ~ '\m(pre[- ]?release|prerelease)\M' then return 'prerelease_product'; end if;
  if t ~ '\mfirst partner pack\M' then return 'first_partner_pack'; end if;
  if t ~ '\mbooster pack\M' and t ~ '\m(art|arts)\M' and t ~ '\m(bundle|set)\M' then return 'booster_pack_art_bundle'; end if;
  if t ~ '\mbooster pack\M' then return 'loose_booster_pack'; end if;
  if t ~ '\mset of\M|\mart set\M|\mbundle\M' then return 'multi_product_bundle'; end if;
  if t ~ '\mcollection\M' then return 'collection_product'; end if;
  return 'other';
end;
$function$;

create or replace function public.market_explorer_sealed_product_family_v1(p_name text)
returns text language sql immutable security invoker set search_path=''
as $function$
  select public.market_explorer_sealed_product_family_v2(p_name);
$function$;

create or replace function public.market_explorer_sealed_parent_member_v1(p_family text)
returns boolean language sql immutable security invoker set search_path=''
as $function$
  select coalesce(p_family,'') not in ('case','display','master_carton');
$function$;

-- Registry labels for deterministic repeat families discovered in canonical inventory.
create or replace function public.market_explorer_sealed_family_label_v2(p_family text)
returns text language sql immutable security invoker set search_path=''
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
  when 'two_pack_blister' then 'Two-Pack Blister'
  when 'single_pack_blister' then 'Single-Pack Blister'
  when 'other_blister' then 'Other Blister'
  when 'ultra_premium_collection' then 'Ultra-Premium Collection'
  when 'super_premium_collection' then 'Super-Premium Collection'
  when 'premium_collection' then 'Premium Collection'
  when 'collection_box' then 'Collection Box'
  when 'collection_product' then 'Collection Product'
  when 'mini_tin' then 'Mini Tin'
  when 'tin' then 'Tin'
  when 'chest' then 'Chest'
  when 'battle_deck' then 'Battle Deck'
  when 'theme_deck' then 'Theme Deck'
  when 'world_championship_deck' then 'World Championship Deck'
  when 'binder' then 'Binder'
  when 'poster' then 'Poster'
  when 'prerelease_product' then 'Prerelease Product'
  when 'first_partner_pack' then 'First Partner Pack'
  when 'booster_pack_art_bundle' then 'Booster Pack Art Bundle'
  when 'multi_product_bundle' then 'Multi-Product Bundle'
  when 'fun_pack' then 'Fun Pack'
  when 'trainers_toolkit' then 'Trainer''s Toolkit'
  when 'case' then 'Case'
  when 'display' then 'Display'
  when 'master_carton' then 'Master Carton'
  else 'Other'
end;
$function$;

create or replace function public.market_explorer_sealed_family_label_v1(p_family text)
returns text language sql immutable security invoker set search_path=''
as $function$
  select public.market_explorer_sealed_family_label_v2(p_family);
$function$;

create or replace function public.market_explorer_sealed_family_definition_v2(p_family text)
returns text language sql immutable security invoker set search_path=''
as $function$
  select case
    when p_family in ('case','display','master_carton') then 'Bulk/container-level sealed packaging; valid as its own Type market but excluded from consumer parent markets'
    when p_family='other' then 'Residual sealed inventory that cannot yet be deterministically classified from canonical metadata'
    else 'Deterministic canonical sealed retail product family'
  end;
$function$;

-- Global Screens remain cross-asset when p_asset is NULL and are hard-capped to 10.
create or replace function public.get_pokemon_market_explorer_prepared_screen_v1(
  p_screen_key text,
  p_asset text default null::text,
  p_limit integer default 10
)
returns table(
  rank integer,
  market_key text,
  label text,
  asset text,
  market_type text,
  metric_value numeric,
  comparison_as_of date,
  generation_id uuid,
  generated_at timestamptz
)
language plpgsql stable security invoker
set search_path='' set statement_timeout='5s'
as $function$
declare
  v_generation uuid;
  v_promoted_at timestamptz;
  v_limit integer:=least(coalesce(p_limit,10),10);
begin
  if p_limit is null or p_limit<1 then raise exception 'screen limit must be positive'; end if;
  if p_asset is not null and p_asset not in ('cards','sealed','graded') then raise exception 'unsupported screen asset'; end if;
  if p_screen_key not in ('top-performers','worst-performers','rarity-leaders','sealed-format-leaders','momentum-leaders','largest-drawdowns')
    then raise exception 'unsupported prepared screen'; end if;

  select s.generation_id,s.promoted_at into v_generation,v_promoted_at
  from public.pokemon_market_explorer_surface_serving_v2 s where s.singleton=1;
  if v_generation is null then raise exception 'PERFORMANCE_SCREEN_V2_NOT_SERVING'; end if;

  if p_screen_key in ('top-performers','worst-performers') then
    return query
    select p.rank,p.market_key,p.label,p.asset,p.market_type,p.metric_7d_pct,
           p.comparison_as_of,v_generation,v_promoted_at
    from public.get_pokemon_market_explorer_performance_screen_v1(
      p_screen_key,coalesce(p_asset,'all'),v_generation,v_limit
    ) p order by p.rank;
    return;
  end if;

  return query
  with candidates as (
    select d.*,
      case when p_screen_key in ('rarity-leaders','sealed-format-leaders','momentum-leaders') then d.return_30d_pct
           when p_screen_key='largest-drawdowns' then d.current_drawdown_pct end metric
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=v_generation and d.screen_eligible
      and d.availability='available' and d.history_available
      and (p_asset is null or d.asset=p_asset)
      and (p_screen_key<>'rarity-leaders' or (d.asset='cards' and d.scope_kind='rarity'))
      and (p_screen_key<>'sealed-format-leaders' or (d.asset='sealed' and d.scope_kind='type'))
  ), ranked as (
    select c.*,
      row_number() over(order by
        case when p_screen_key='largest-drawdowns' then c.metric end asc nulls last,
        case when p_screen_key<>'largest-drawdowns' then c.metric end desc nulls last,
        c.market_key)::integer screen_rank
    from candidates c where c.metric is not null
  )
  select r.screen_rank,r.market_key,r.label,r.asset,r.scope_kind,r.metric,
         r.comparison_as_of,v_generation,v_promoted_at
  from ranked r where r.screen_rank<=v_limit order by r.screen_rank;
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_prepared_screen_v1(text,text,integer)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_prepared_screen_v1(text,text,integer) to service_role;

-- Bounded independent per-product sealed movement authority.
create or replace function public.get_pokemon_market_explorer_sealed_constituent_movement_v1(
  p_sealed_product_ids uuid[],
  p_as_of date
)
returns table(
  sealed_product_id uuid,
  as_of date,
  end_price numeric,
  baseline_1d_date date,
  movement_1d_pct numeric,
  baseline_7d_date date,
  movement_7d_pct numeric,
  baseline_30d_date date,
  movement_30d_pct numeric,
  baseline_3m_date date,
  movement_3m_pct numeric
)
language plpgsql stable security invoker
set search_path='' set statement_timeout='2s'
as $function$
begin
  if p_sealed_product_ids is null or cardinality(p_sealed_product_ids)<1
     or cardinality(p_sealed_product_ids)>100 or p_as_of is null then
    raise exception 'SEALED_MOVEMENT_REQUIRES_1_TO_100_IDS_AND_AS_OF';
  end if;

  return query
  with ids as materialized (select distinct x.id from unnest(p_sealed_product_ids) x(id)),
  endpoint as materialized (
    select i.id,e.captured_at::date end_date,e.market_price end_price
    from ids i
    left join lateral (
      select o.captured_at,o.market_price
      from public.sealed_product_price_observations o
      where o.sealed_product_id=i.id
        and o.captured_at>=p_as_of::timestamptz
        and o.captured_at<(p_as_of+1)::timestamptz
        and o.market_price>0
        and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
      order by o.captured_at desc,o.id desc limit 1
    ) e on true
  )
  select e.id,p_as_of,e.end_price,
    b1.d, case when e.end_price>0 and b1.p>0 then (e.end_price/b1.p-1.0)*100.0 end,
    b7.d, case when e.end_price>0 and b7.p>0 then (e.end_price/b7.p-1.0)*100.0 end,
    b30.d,case when e.end_price>0 and b30.p>0 then (e.end_price/b30.p-1.0)*100.0 end,
    b90.d,case when e.end_price>0 and b90.p>0 then (e.end_price/b90.p-1.0)*100.0 end
  from endpoint e
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<p_as_of::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b1 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-7+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b7 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-30+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b30 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-90+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b90 on true
  order by array_position(p_sealed_product_ids,e.id);
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_sealed_constituent_movement_v1(uuid[],date)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_sealed_constituent_movement_v1(uuid[],date)
to service_role;

-- Rebuild compact sealed authorities with the new retail-membership policy.
select public.refresh_pokemon_market_explorer_sealed_daily_v1(
  (select min(captured_date) from public.sealed_product_price_observations),
  (select max(captured_date) from public.sealed_product_price_observations)
);
select public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();
select public.refresh_pokemon_market_explorer_sealed_type_registry_v1();

commit;
