-- Explicit vintage edition markets for Market tab + Market Explorer.
--
-- Product contract:
--   * Standard/modern roots remain one market: set:<set_id>
--   * edition_split roots expose independent first_edition + unlimited markets
--   * base_three_printings exposes first_edition + shadowless + unlimited
--   * no generic edition-mixed vintage Set market is published
--   * every scoped market uses the same scope for Set Value, Index, constituents
--
-- This migration does NOT alter Set-page default behavior. The Set-page UX is
-- intentionally deferred; this adds a scope-aware read authority and teaches the
-- Market Explorer prepared publication to consume the explicit Market snapshot.

create or replace function public.get_pokemon_market_set_scope_constituents_v1(
  p_set_id uuid,
  p_market_scope text,
  p_market_date date,
  p_card_ids uuid[] default null::uuid[]
)
returns table(
  canonical_card_id uuid,
  set_id uuid,
  market_date date,
  market_price numeric,
  card_variant_id uuid,
  source text,
  captured_at date
)
language sql
stable
security invoker
set search_path = ''
set "TimeZone" to 'America/Phoenix'
set statement_timeout = '15s'
as $function$
with requested_scope as (
  select
    e.set_id,
    e.profile,
    case p_market_scope
      when 'first_edition' then '1st-edition'
      when 'unlimited' then 'unlimited'
      when 'shadowless' then 'shadowless'
    end as edition
  from public.pokemon_edition_split_root_sets_v2 e
  where e.set_id = p_set_id
    and (
      (e.profile = 'edition_split' and p_market_scope in ('first_edition','unlimited'))
      or
      (e.profile = 'base_three_printings' and p_market_scope in ('first_edition','shadowless','unlimited'))
    )
),
members as materialized (
  select s.id as set_id
  from public.sets s
  join requested_scope rs on rs.set_id = s.id
  where s.parent_opening_set_id is null and s.catalog_only = false
  union all
  select child.id
  from public.sets child
  join requested_scope rs on true
  where child.parent_opening_set_id = rs.set_id
    and child.counts_toward_parent_set_value = true
),
eligible_cards as materialized (
  select pcc.id as canonical_card_id, pcc.set_id, pcc.rarity
  from public.pokemon_canonical_cards pcc
  join members m on m.set_id = pcc.set_id
  where pcc.set_value_eligible = true
    and (p_card_ids is null or pcc.id = any(p_card_ids))
),
near_mint as (
  select c.id
  from public.conditions c
  where lower(c.name) = 'near mint'
  order by c.id
  limit 1
),
candidates as materialized (
  select
    ec.canonical_card_id,
    ec.set_id,
    interval_row.card_variant_id,
    interval_row.market_price,
    obs.latest_observed_date,
    obs.source,
    row_number() over (
      partition by ec.canonical_card_id
      order by
        case meta.identity_basis
          when 'explicit_legacy_identity_link' then 0
          when 'parent_pokemon_tcg_api_id' then 1
          when 'variant_pokemon_tcg_api_id' then 2
          when 'normalized_name_number_fallback' then 3
          else 9
        end,
        case when meta.special_type is null or meta.special_type = '' then 0 else 1 end,
        case
          when ec.rarity in ('Common','Uncommon') and meta.printing_type = 'non-holo' then 0
          when ec.rarity in ('Common','Uncommon') and meta.printing_type = 'holo' then 1
          when ec.rarity in ('Common','Uncommon') and meta.printing_type = 'reverse-holo' then 2
          when meta.printing_type = 'holo' then 0
          when meta.printing_type = 'non-holo' then 1
          when meta.printing_type = 'reverse-holo' then 2
          else 9
        end,
        obs.latest_observed_date desc nulls last,
        interval_row.card_variant_id
    ) as selection_rank
  from requested_scope rs
  join eligible_cards ec on true
  join public.pokemon_market_price_intervals_v2_shadow interval_row
    on interval_row.set_id = ec.set_id
   and interval_row.valid_from <= p_market_date
   and (interval_row.valid_to is null or p_market_date < interval_row.valid_to)
  join public.pokemon_market_explorer_card_current_metadata meta
    on meta.card_variant_id = interval_row.card_variant_id
   and meta.set_id = ec.set_id
   and meta.canonical_card_id = ec.canonical_card_id
   and meta.edition = rs.edition
  cross join near_mint nm
  left join lateral (
    select
      max(least(r.observed_through, p_market_date)) as latest_observed_date,
      (array_agg(r.source order by least(r.observed_through, p_market_date) desc, r.source desc))[1] as source
    from public.card_variant_price_observation_ranges_v2 r
    where r.card_variant_id = interval_row.card_variant_id
      and r.condition_id = nm.id
      and r.currency = 'USD'
      and r.observed_from <= p_market_date
  ) obs on true
)
select
  c.canonical_card_id,
  c.set_id,
  p_market_date,
  c.market_price,
  c.card_variant_id,
  c.source,
  c.latest_observed_date
from candidates c
where c.selection_rank = 1
order by c.canonical_card_id;
$function$;

revoke all on function public.get_pokemon_market_set_scope_constituents_v1(uuid,text,date,uuid[])
  from public, anon, authenticated;
grant execute on function public.get_pokemon_market_set_scope_constituents_v1(uuid,text,date,uuid[])
  to service_role;

-- Scope-aware prepared constituent staging. Fail closed when the explicit
-- Market snapshot marks a scoped market unavailable; otherwise use the same
-- scoped variant selection contract that backs root Set Value history.
do $patch_stage$
declare
  v_definition text;
  v_old_source text := 'from public.get_pokemon_cards_daily_constituents(array[d.set_id], d.source_as_of, d.source_as_of, null::uuid[]) q';
  v_new_source text := $replace$
from (
          select q0.*
          from public.get_pokemon_cards_daily_constituents(array[d.set_id], d.source_as_of, d.source_as_of, null::uuid[]) q0
          where coalesce(d.metadata->>'marketScope','standard') = 'standard'
          union all
          select q1.*
          from public.get_pokemon_market_set_scope_constituents_v1(
            d.set_id, d.metadata->>'marketScope', d.source_as_of, null::uuid[]
          ) q1
          where coalesce(d.metadata->>'marketScope','standard') <> 'standard'
        ) q$replace$;
  v_old_start text := $replace$if d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' and d.set_id is not null then
      -- Same membership authority as the v2 reader (root/subset expansion lives in the resolver).$replace$;
  v_new_start text := $replace$if d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' and d.set_id is not null then
      if d.source_as_of is null or d.source_status = 'unavailable' then
        insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
          (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability, availability_reason)
        values (
          p_generation_id, d.market_key, 'cards', d.source_kind,
          coalesce(d.metadata->>'marketScope', d.prepared_series_key), d.source_as_of, 0,
          'unavailable', 'No certified Set market value exists for this explicit market scope'
        );
      else$replace$;
  v_old_next text := $replace$    elsif d.source_kind = 'prepared_sealed_snapshots' and d.market_type = 'prepared_format' and d.asset = 'sealed' then$replace$;
  v_new_next text := $replace$      end if;
    elsif d.source_kind = 'prepared_sealed_snapshots' and d.market_type = 'prepared_format' and d.asset = 'sealed' then$replace$;
  v_old_item text := $replacebegin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'stage_pokemon_market_explorer_prepared_constituents_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_generation_id uuid';

  if v_definition is null then
    raise exception 'prepared constituent staging function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'get_pokemon_market_set_scope_constituents_v1') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_source) = 0
     or pg_catalog.strpos(v_definition, v_old_start) = 0
     or pg_catalog.strpos(v_definition, v_old_next) = 0
     or pg_catalog.strpos(v_definition, v_old_item) = 0 then
    raise exception 'prepared constituent staging body did not match expected v1 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_source, v_new_source);
  v_definition := pg_catalog.replace(v_definition, v_old_start, v_new_start);
  v_definition := pg_catalog.replace(v_definition, v_old_next, v_new_next);
  v_definition := pg_catalog.replace(v_definition, v_old_item, v_new_item);
  execute v_definition;
end
$patch_stage$;

-- Patch the large Phase-5 prepared publisher surgically so the currently
-- deployed optimizations remain intact. The guarded publisher continues to
-- promote atomically and stage v3 constituents after the generation switch.
do $patch_refresh$
declare
  v_definition text;
  v_old_key text := $replace$'set:' || (e->>'setId'), 'set', e->>'name', 'cards',$replace$;
  v_new_key text := $replace$coalesce(nullif(e->>'marketKey',''), 'set:' || (e->>'setId')), 'set', e->>'name', 'cards',$replace$;
  v_old_series text := $replace$'set-cards-market-index:' || (e->>'setId'),$replace$;
  v_new_series text := $replace$'set-cards-market-index:' || coalesce(nullif(e->>'marketKey',''), e->>'setId'),$replace$;
  v_old_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_new_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'marketScope', coalesce(nullif(e->>'marketScope',''), 'standard'),
      'baseSetName', e->>'baseSetName',
      'marketProfile', e->>'marketProfile',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_old_public_sets text := $replace$select (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'$replace$;
  v_new_public_sets text := $replace$select distinct (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and coalesce(nullif(e->>'marketScope',''), 'standard') = 'standard'$replace$;
  v_marker text := $replace$  -- Maintained prepared series are already current-chain normalized histories.$replace$;
  v_scoped_history text := $replace$
  -- Edition-scoped vintage Set markets. These histories are rebuilt from the
  -- same certified scoped root Set Value authority published on /Market.
  -- Because every included row is a complete fixed edition basket, the ratio
  -- to the first certified basket value is the exact fixed-basket Market Index.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with scoped_markets as (
    select
      e->>'marketKey' as market_key,
      (e->>'setId')::uuid as set_id,
      e->>'marketScope' as market_scope
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and nullif(e->>'marketKey','') is not null
      and coalesce(nullif(e->>'marketScope',''), 'standard') in ('first_edition','unlimited','shadowless')
  ), points as (
    select
      sm.market_key,
      h.market_date,
      h.set_value,
      first_value(h.set_value) over (
        partition by sm.market_key
        order by h.market_date
        rows between unbounded preceding and unbounded following
      ) as base_value
    from scoped_markets sm
    join public.pokemon_market_root_set_value_daily_history_v2_shadow h
      on h.set_id = sm.set_id
     and h.market_scope = sm.market_scope
    where h.certified_on_date = true
      and h.market_date <= v_comparison_asof
      and h.set_value > 0
  )
  select market_key, market_date,
         100.0 * set_value / nullif(base_value,0),
         set_value, 0, v_generation_id
  from points
  where base_value > 0;

$replace$;
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'refresh_pokemon_market_explorer_prepared_directory_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = '';

  if v_definition is null then
    raise exception 'prepared directory refresh function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'Edition-scoped vintage Set markets') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_key) = 0
     or pg_catalog.strpos(v_definition, v_old_series) = 0
     or pg_catalog.strpos(v_definition, v_old_meta) = 0
     or pg_catalog.strpos(v_definition, v_old_public_sets) = 0
     or pg_catalog.strpos(v_definition, v_marker) = 0 then
    raise exception 'prepared directory refresh body did not match expected Phase-5 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_key, v_new_key);
  v_definition := pg_catalog.replace(v_definition, v_old_series, v_new_series);
  v_definition := pg_catalog.replace(v_definition, v_old_meta, v_new_meta);
  v_definition := pg_catalog.replace(v_definition, v_old_public_sets, v_new_public_sets);
  v_definition := pg_catalog.replace(v_definition, v_marker, v_scoped_history || v_marker);
  execute v_definition;
end
$patch_refresh$;

comment on function public.get_pokemon_market_set_scope_constituents_v1(uuid,text,date,uuid[]) is
'Canonical explicit-edition Market Set constituent reader. One selected physical variant per canonical card within one edition scope/date; used by Market tab and prepared Market Explorer. Standard Set-page behavior is intentionally unchanged.';
printingType', cv.printing_type, 'specialType', cv.special_type,
          'marketPrice', r.market_price, 'asOf', r.market_date)$replace$;
  v_new_item text := $replacebegin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'stage_pokemon_market_explorer_prepared_constituents_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_generation_id uuid';

  if v_definition is null then
    raise exception 'prepared constituent staging function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'get_pokemon_market_set_scope_constituents_v1') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_source) = 0
     or pg_catalog.strpos(v_definition, v_old_start) = 0
     or pg_catalog.strpos(v_definition, v_old_next) = 0 then
    raise exception 'prepared constituent staging body did not match expected v1 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_source, v_new_source);
  v_definition := pg_catalog.replace(v_definition, v_old_start, v_new_start);
  v_definition := pg_catalog.replace(v_definition, v_old_next, v_new_next);
  execute v_definition;
end
$patch_stage$;

-- Patch the large Phase-5 prepared publisher surgically so the currently
-- deployed optimizations remain intact. The guarded publisher continues to
-- promote atomically and stage v3 constituents after the generation switch.
do $patch_refresh$
declare
  v_definition text;
  v_old_key text := $replace$'set:' || (e->>'setId'), 'set', e->>'name', 'cards',$replace$;
  v_new_key text := $replace$coalesce(nullif(e->>'marketKey',''), 'set:' || (e->>'setId')), 'set', e->>'name', 'cards',$replace$;
  v_old_series text := $replace$'set-cards-market-index:' || (e->>'setId'),$replace$;
  v_new_series text := $replace$'set-cards-market-index:' || coalesce(nullif(e->>'marketKey',''), e->>'setId'),$replace$;
  v_old_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_new_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'marketScope', coalesce(nullif(e->>'marketScope',''), 'standard'),
      'baseSetName', e->>'baseSetName',
      'marketProfile', e->>'marketProfile',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_old_public_sets text := $replace$select (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'$replace$;
  v_new_public_sets text := $replace$select distinct (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and coalesce(nullif(e->>'marketScope',''), 'standard') = 'standard'$replace$;
  v_marker text := $replace$  -- Maintained prepared series are already current-chain normalized histories.$replace$;
  v_scoped_history text := $replace$
  -- Edition-scoped vintage Set markets. These histories are rebuilt from the
  -- same certified scoped root Set Value authority published on /Market.
  -- Because every included row is a complete fixed edition basket, the ratio
  -- to the first certified basket value is the exact fixed-basket Market Index.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with scoped_markets as (
    select
      e->>'marketKey' as market_key,
      (e->>'setId')::uuid as set_id,
      e->>'marketScope' as market_scope
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and nullif(e->>'marketKey','') is not null
      and coalesce(nullif(e->>'marketScope',''), 'standard') in ('first_edition','unlimited','shadowless')
  ), points as (
    select
      sm.market_key,
      h.market_date,
      h.set_value,
      first_value(h.set_value) over (
        partition by sm.market_key
        order by h.market_date
        rows between unbounded preceding and unbounded following
      ) as base_value
    from scoped_markets sm
    join public.pokemon_market_root_set_value_daily_history_v2_shadow h
      on h.set_id = sm.set_id
     and h.market_scope = sm.market_scope
    where h.certified_on_date = true
      and h.market_date <= v_comparison_asof
      and h.set_value > 0
  )
  select market_key, market_date,
         100.0 * set_value / nullif(base_value,0),
         set_value, 0, v_generation_id
  from points
  where base_value > 0;

$replace$;
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'refresh_pokemon_market_explorer_prepared_directory_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = '';

  if v_definition is null then
    raise exception 'prepared directory refresh function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'Edition-scoped vintage Set markets') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_key) = 0
     or pg_catalog.strpos(v_definition, v_old_series) = 0
     or pg_catalog.strpos(v_definition, v_old_meta) = 0
     or pg_catalog.strpos(v_definition, v_old_public_sets) = 0
     or pg_catalog.strpos(v_definition, v_marker) = 0 then
    raise exception 'prepared directory refresh body did not match expected Phase-5 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_key, v_new_key);
  v_definition := pg_catalog.replace(v_definition, v_old_series, v_new_series);
  v_definition := pg_catalog.replace(v_definition, v_old_meta, v_new_meta);
  v_definition := pg_catalog.replace(v_definition, v_old_public_sets, v_new_public_sets);
  v_definition := pg_catalog.replace(v_definition, v_marker, v_scoped_history || v_marker);
  execute v_definition;
end
$patch_refresh$;

comment on function public.get_pokemon_market_set_scope_constituents_v1(uuid,text,date,uuid[]) is
'Canonical explicit-edition Market Set constituent reader. One selected physical variant per canonical card within one edition scope/date; used by Market tab and prepared Market Explorer. Standard Set-page behavior is intentionally unchanged.';
printingType', cv.printing_type, 'specialType', cv.special_type,
          'marketScope', coalesce(d.metadata->>'marketScope','standard'),
          'marketPrice', r.market_price, 'asOf', r.market_date)$replace$;
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'stage_pokemon_market_explorer_prepared_constituents_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_generation_id uuid';

  if v_definition is null then
    raise exception 'prepared constituent staging function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'get_pokemon_market_set_scope_constituents_v1') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_source) = 0
     or pg_catalog.strpos(v_definition, v_old_start) = 0
     or pg_catalog.strpos(v_definition, v_old_next) = 0 then
    raise exception 'prepared constituent staging body did not match expected v1 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_source, v_new_source);
  v_definition := pg_catalog.replace(v_definition, v_old_start, v_new_start);
  v_definition := pg_catalog.replace(v_definition, v_old_next, v_new_next);
  execute v_definition;
end
$patch_stage$;

-- Patch the large Phase-5 prepared publisher surgically so the currently
-- deployed optimizations remain intact. The guarded publisher continues to
-- promote atomically and stage v3 constituents after the generation switch.
do $patch_refresh$
declare
  v_definition text;
  v_old_key text := $replace$'set:' || (e->>'setId'), 'set', e->>'name', 'cards',$replace$;
  v_new_key text := $replace$coalesce(nullif(e->>'marketKey',''), 'set:' || (e->>'setId')), 'set', e->>'name', 'cards',$replace$;
  v_old_series text := $replace$'set-cards-market-index:' || (e->>'setId'),$replace$;
  v_new_series text := $replace$'set-cards-market-index:' || coalesce(nullif(e->>'marketKey',''), e->>'setId'),$replace$;
  v_old_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_new_meta text := $replace$'symbolUrl', e->>'symbolUrl',
      'marketScope', coalesce(nullif(e->>'marketScope',''), 'standard'),
      'baseSetName', e->>'baseSetName',
      'marketProfile', e->>'marketProfile',
      'certificationStatus', e->>'certificationStatus'$replace$;
  v_old_public_sets text := $replace$select (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'$replace$;
  v_new_public_sets text := $replace$select distinct (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and coalesce(nullif(e->>'marketScope',''), 'standard') = 'standard'$replace$;
  v_marker text := $replace$  -- Maintained prepared series are already current-chain normalized histories.$replace$;
  v_scoped_history text := $replace$
  -- Edition-scoped vintage Set markets. These histories are rebuilt from the
  -- same certified scoped root Set Value authority published on /Market.
  -- Because every included row is a complete fixed edition basket, the ratio
  -- to the first certified basket value is the exact fixed-basket Market Index.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with scoped_markets as (
    select
      e->>'marketKey' as market_key,
      (e->>'setId')::uuid as set_id,
      e->>'marketScope' as market_scope
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
      and nullif(e->>'marketKey','') is not null
      and coalesce(nullif(e->>'marketScope',''), 'standard') in ('first_edition','unlimited','shadowless')
  ), points as (
    select
      sm.market_key,
      h.market_date,
      h.set_value,
      first_value(h.set_value) over (
        partition by sm.market_key
        order by h.market_date
        rows between unbounded preceding and unbounded following
      ) as base_value
    from scoped_markets sm
    join public.pokemon_market_root_set_value_daily_history_v2_shadow h
      on h.set_id = sm.set_id
     and h.market_scope = sm.market_scope
    where h.certified_on_date = true
      and h.market_date <= v_comparison_asof
      and h.set_value > 0
  )
  select market_key, market_date,
         100.0 * set_value / nullif(base_value,0),
         set_value, 0, v_generation_id
  from points
  where base_value > 0;

$replace$;
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'refresh_pokemon_market_explorer_prepared_directory_v1'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = '';

  if v_definition is null then
    raise exception 'prepared directory refresh function is missing';
  end if;
  if pg_catalog.strpos(v_definition, 'Edition-scoped vintage Set markets') > 0 then
    return;
  end if;
  if pg_catalog.strpos(v_definition, v_old_key) = 0
     or pg_catalog.strpos(v_definition, v_old_series) = 0
     or pg_catalog.strpos(v_definition, v_old_meta) = 0
     or pg_catalog.strpos(v_definition, v_old_public_sets) = 0
     or pg_catalog.strpos(v_definition, v_marker) = 0 then
    raise exception 'prepared directory refresh body did not match expected Phase-5 contract';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_key, v_new_key);
  v_definition := pg_catalog.replace(v_definition, v_old_series, v_new_series);
  v_definition := pg_catalog.replace(v_definition, v_old_meta, v_new_meta);
  v_definition := pg_catalog.replace(v_definition, v_old_public_sets, v_new_public_sets);
  v_definition := pg_catalog.replace(v_definition, v_marker, v_scoped_history || v_marker);
  execute v_definition;
end
$patch_refresh$;

comment on function public.get_pokemon_market_set_scope_constituents_v1(uuid,text,date,uuid[]) is
'Canonical explicit-edition Market Set constituent reader. One selected physical variant per canonical card within one edition scope/date; used by Market tab and prepared Market Explorer. Standard Set-page behavior is intentionally unchanged.';
