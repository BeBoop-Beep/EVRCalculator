alter table public.pokemon_market_explorer_query_cache
  drop constraint if exists pokemon_market_explorer_query_cache_asset_check;

alter table public.pokemon_market_explorer_query_cache
  add constraint pokemon_market_explorer_query_cache_asset_check
  check (asset = any (array['cards'::text, 'sealed'::text, 'mixed'::text]));

create or replace function public.get_pokemon_market_explorer_explicit_basket_series_v2(
  p_instruments jsonb,
  p_start_date date default null,
  p_end_date date default null
)
returns table(
  market_date date,
  selected_instrument_count integer,
  priced_instrument_count integer,
  basket_value numeric,
  previous_market_date date,
  common_instrument_count integer,
  common_current_value numeric,
  common_previous_value numeric,
  basket_as_of date,
  comparison_as_of date,
  status text,
  canonical_instruments jsonb,
  current_constituents jsonb
)
language plpgsql
stable
security invoker
set search_path to ''
set statement_timeout to '5s'
set work_mem to '16MB'
as $function$
declare
  v_item jsonb;
  v_asset text;
  v_id_text text;
  v_id uuid;
  v_raw_count integer;
  v_selected_count integer;
  v_valid_count integer;
  v_first_approved date;
  v_latest_approved date;
  v_start date;
  v_end date;
  v_card_retained_from date;
begin
  if p_instruments is null or pg_catalog.jsonb_typeof(p_instruments) <> 'array' then
    raise exception 'Exact Basket V2 instruments must be a JSON array'
      using errcode = '22023';
  end if;

  v_raw_count := pg_catalog.jsonb_array_length(p_instruments);
  if v_raw_count < 1 or v_raw_count > 25 then
    raise exception 'Exact Basket V2 requires 1 to 25 instruments'
      using errcode = '22023';
  end if;

  for v_item in select value from pg_catalog.jsonb_array_elements(p_instruments)
  loop
    if pg_catalog.jsonb_typeof(v_item) <> 'object' then
      raise exception 'Each Exact Basket V2 instrument must be an object'
        using errcode = '22023';
    end if;

    v_asset := pg_catalog.lower(pg_catalog.btrim(coalesce(v_item->>'asset', '')));
    v_id_text := pg_catalog.btrim(coalesce(v_item->>'instrumentId', ''));

    if v_asset not in ('cards', 'sealed') then
      raise exception 'Exact Basket V2 instrument asset must be cards or sealed'
        using errcode = '22023';
    end if;
    if v_id_text = '' then
      raise exception 'Exact Basket V2 instrumentId is required'
        using errcode = '22023';
    end if;

    begin
      v_id := v_id_text::uuid;
    exception when invalid_text_representation then
      raise exception 'Exact Basket V2 instrumentId must be a UUID'
        using errcode = '22023';
    end;
  end loop;

  select min(q.market_date), max(q.market_date)
    into v_first_approved, v_latest_approved
  from public.pokemon_market_date_quality q
  where q.tcg = 'pokemon'
    and q.status in ('READY', 'LEGACY_VERIFIED');

  if v_latest_approved is null then
    return query
    select null::date, 0, 0, null::numeric, null::date, 0, 0::numeric, 0::numeric,
           null::date, null::date, 'unavailable'::text,
           '[]'::jsonb, '[]'::jsonb;
    return;
  end if;

  v_end := least(coalesce(p_end_date, v_latest_approved), v_latest_approved);
  v_start := greatest(coalesce(p_start_date, v_first_approved), v_first_approved);
  if v_start > v_end then
    raise exception 'Exact Basket V2 start date must not be after end date'
      using errcode = '22023';
  end if;

  select max(c.retained_from)
    into v_card_retained_from
  from public.pokemon_market_explorer_card_daily_coverage_v2_shadow c;
  v_card_retained_from := coalesce(v_card_retained_from, v_first_approved);

  with raw_selected as materialized (
    select
      pg_catalog.lower(pg_catalog.btrim(value->>'asset')) as asset,
      pg_catalog.btrim(value->>'instrumentId')::uuid as instrument_id
    from pg_catalog.jsonb_array_elements(p_instruments)
  ),
  selected as materialized (
    select distinct r.asset, r.instrument_id
    from raw_selected r
  ),
  valid_cards as materialized (
    select s.asset, s.instrument_id
    from selected s
    join public.pokemon_market_explorer_card_current_metadata m
      on s.asset = 'cards' and m.card_variant_id = s.instrument_id
    where exists (
      select 1
      from public.pokemon_market_explorer_card_daily_states_v2_shadow d
      where d.card_variant_id = s.instrument_id
        and d.market_date = v_latest_approved
        and d.market_price > 0
    )
  ),
  valid_sealed as materialized (
    select s.asset, s.instrument_id
    from selected s
    where s.asset = 'sealed'
      and exists (
        select 1
        from public.sealed_products sp
        join public.pokemon_set_sealed_market_snapshot_latest snap
          on snap.set_id = sp.set_id and snap.tcg = 'pokemon'
        cross join lateral pg_catalog.jsonb_array_elements(
          coalesce(snap.payload_json->'products', '[]'::jsonb)
        ) p(item)
        where sp.id = s.instrument_id
          and nullif(p.item->>'sealedProductId', '')::uuid = s.instrument_id
          and coalesce((p.item->>'currentPrice')::numeric, 0) > 0
          and exists (
            select 1
            from pg_catalog.jsonb_array_elements(coalesce(p.item->'history', '[]'::jsonb)) h(item)
            where coalesce((h.item->>'marketPrice')::numeric, 0) > 0
          )
      )
  ),
  valid as materialized (
    select * from valid_cards
    union all
    select * from valid_sealed
  )
  select (select count(*)::integer from selected),
         (select count(*)::integer from valid)
    into v_selected_count, v_valid_count;

  if v_selected_count < 1 or v_selected_count > 25 then
    raise exception 'Exact Basket V2 canonical membership must contain 1 to 25 instruments'
      using errcode = '22023';
  end if;
  if v_valid_count <> v_selected_count then
    raise exception 'Exact Basket V2 contains an unknown, aggregate, or currently ineligible leaf instrument'
      using errcode = '22023';
  end if;

  return query
  with raw_selected as materialized (
    select
      pg_catalog.lower(pg_catalog.btrim(value->>'asset')) as asset,
      pg_catalog.btrim(value->>'instrumentId')::uuid as instrument_id
    from pg_catalog.jsonb_array_elements(p_instruments)
  ),
  selected as materialized (
    select distinct r.asset, r.instrument_id
    from raw_selected r
  ),
  canonical as materialized (
    select coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object('asset', s.asset, 'instrumentId', s.instrument_id)
        order by s.asset, s.instrument_id
      ), '[]'::jsonb
    ) as body
    from selected s
  ),
  approved_dates as materialized (
    select q.market_date
    from public.pokemon_market_date_quality q
    where q.tcg = 'pokemon'
      and q.status in ('READY', 'LEGACY_VERIFIED')
      and q.market_date <= v_end
  ),
  card_meta as materialized (
    select
      'cards'::text as asset,
      s.instrument_id,
      m.set_id,
      m.card_name as name,
      st.name as set_name,
      m.image_url,
      m.card_number,
      m.rarity,
      m.edition,
      m.printing_type,
      m.special_type,
      null::text as product_family,
      null::text as variant_label
    from selected s
    join public.pokemon_market_explorer_card_current_metadata m
      on s.asset = 'cards' and m.card_variant_id = s.instrument_id
    left join public.sets st on st.id = m.set_id
  ),
  sealed_meta as materialized (
    select distinct on (s.instrument_id)
      'sealed'::text as asset,
      s.instrument_id,
      sp.set_id,
      coalesce(nullif(p.item->>'name', ''), sp.name) as name,
      coalesce(st.name, snap.payload_json->'set'->>'name') as set_name,
      coalesce(nullif(p.item->>'imageUrl', ''), sp.image_small_url, sp.image_large_url) as image_url,
      null::text as card_number,
      null::text as rarity,
      null::text as edition,
      null::text as printing_type,
      null::text as special_type,
      coalesce(nullif(p.item->>'productFamily', ''), sp.product_type) as product_family,
      nullif(p.item->>'variantLabel', '') as variant_label,
      p.item as product_item
    from selected s
    join public.sealed_products sp
      on s.asset = 'sealed' and sp.id = s.instrument_id
    join public.pokemon_set_sealed_market_snapshot_latest snap
      on snap.set_id = sp.set_id and snap.tcg = 'pokemon'
    cross join lateral pg_catalog.jsonb_array_elements(
      coalesce(snap.payload_json->'products', '[]'::jsonb)
    ) p(item)
    left join public.sets st on st.id = sp.set_id
    where nullif(p.item->>'sealedProductId', '')::uuid = s.instrument_id
    order by s.instrument_id, snap.market_date desc nulls last, snap.set_id
  ),
  instrument_meta as materialized (
    select asset, instrument_id, set_id, name, set_name, image_url,
           card_number, rarity, edition, printing_type, special_type,
           product_family, variant_label
    from card_meta
    union all
    select asset, instrument_id, set_id, name, set_name, image_url,
           card_number, rarity, edition, printing_type, special_type,
           product_family, variant_label
    from sealed_meta
  ),
  card_panel_old as materialized (
    select
      d.market_date,
      c.asset,
      c.instrument_id,
      i.market_price
    from card_meta c
    join public.pokemon_market_price_intervals_v2_shadow i
      on i.card_variant_id = c.instrument_id
    join approved_dates d
      on d.market_date < v_card_retained_from
     and i.valid_from <= d.market_date
     and (i.valid_to is null or d.market_date < i.valid_to)
    where i.market_price > 0
  ),
  card_panel_hot as materialized (
    select
      d.market_date,
      c.asset,
      c.instrument_id,
      d.market_price
    from card_meta c
    join public.pokemon_market_explorer_card_daily_states_v2_shadow d
      on d.card_variant_id = c.instrument_id
     and d.market_date >= v_card_retained_from
     and d.market_date <= v_end
    join approved_dates q on q.market_date = d.market_date
    where d.market_price > 0
  ),
  sealed_panel as materialized (
    select
      (h.item->>'date')::date as market_date,
      s.asset,
      s.instrument_id,
      (h.item->>'marketPrice')::numeric as market_price
    from sealed_meta s
    cross join lateral pg_catalog.jsonb_array_elements(
      coalesce(s.product_item->'history', '[]'::jsonb)
    ) h(item)
    join approved_dates d on d.market_date = (h.item->>'date')::date
    where coalesce((h.item->>'marketPrice')::numeric, 0) > 0
  ),
  panel as materialized (
    select * from card_panel_old
    union all
    select * from card_panel_hot
    union all
    select * from sealed_panel
  ),
  observations as materialized (
    select
      p.market_date,
      count(*)::integer as priced_count,
      sum(p.market_price)::numeric as basket_value
    from panel p
    group by p.market_date
  ),
  observations_with_previous as materialized (
    select
      o.*,
      pg_catalog.lag(o.market_date) over (order by o.market_date) as previous_market_date
    from observations o
  ),
  linked as materialized (
    select
      o.market_date,
      o.previous_market_date,
      o.priced_count,
      o.basket_value,
      count(prev.instrument_id)::integer as common_count,
      coalesce(sum(cur.market_price) filter (where prev.instrument_id is not null), 0)::numeric
        as common_current_value,
      coalesce(sum(prev.market_price), 0)::numeric as common_previous_value
    from observations_with_previous o
    join panel cur on cur.market_date = o.market_date
    left join panel prev
      on prev.market_date = o.previous_market_date
     and prev.asset = cur.asset
     and prev.instrument_id = cur.instrument_id
    group by o.market_date, o.previous_market_date, o.priced_count, o.basket_value
  ),
  safe_as_of as materialized (
    select max(o.market_date) as basket_as_of
    from observations o
    where o.priced_count = v_selected_count
  ),
  current_basket as materialized (
    select o.basket_value
    from observations o
    join safe_as_of a on a.basket_as_of = o.market_date
  ),
  current_ranked as materialized (
    select
      p.asset,
      p.instrument_id,
      p.market_price,
      m.set_id,
      m.name,
      m.set_name,
      m.image_url,
      m.card_number,
      m.rarity,
      m.edition,
      m.printing_type,
      m.special_type,
      m.product_family,
      m.variant_label,
      pg_catalog.row_number() over (
        order by p.market_price desc, p.asset, p.instrument_id
      )::integer as rank
    from panel p
    join safe_as_of a on a.basket_as_of = p.market_date
    join instrument_meta m
      on m.asset = p.asset and m.instrument_id = p.instrument_id
  ),
  current_items as materialized (
    select coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_strip_nulls(
          pg_catalog.jsonb_build_object(
            'rank', r.rank,
            'asset', r.asset,
            'instrumentId', r.instrument_id,
            'cardVariantId', case when r.asset = 'cards' then r.instrument_id else null end,
            'sealedProductId', case when r.asset = 'sealed' then r.instrument_id else null end,
            'name', r.name,
            'setId', r.set_id,
            'setName', r.set_name,
            'imageUrl', r.image_url,
            'cardNumber', r.card_number,
            'rarity', r.rarity,
            'edition', r.edition,
            'printingType', r.printing_type,
            'specialType', r.special_type,
            'productFamily', r.product_family,
            'variantLabel', r.variant_label,
            'marketPrice', r.market_price,
            'quantity', 1,
            'valueShare', r.market_price / nullif(b.basket_value, 0),
            'valueSharePercent', (r.market_price / nullif(b.basket_value, 0)) * 100,
            'asOf', a.basket_as_of
          )
        )
        order by r.rank
      ), '[]'::jsonb
    ) as body
    from current_ranked r
    cross join current_basket b
    cross join safe_as_of a
  )
  select
    l.market_date,
    v_selected_count,
    l.priced_count,
    l.basket_value,
    l.previous_market_date,
    l.common_count,
    l.common_current_value,
    l.common_previous_value,
    a.basket_as_of,
    a.basket_as_of,
    case when a.basket_as_of = v_end then 'ready' else 'stale' end::text,
    case when l.market_date = a.basket_as_of then c.body else null::jsonb end,
    case when l.market_date = a.basket_as_of then i.body else null::jsonb end
  from linked l
  cross join safe_as_of a
  cross join canonical c
  cross join current_items i
  where a.basket_as_of is not null
    and l.market_date between v_start and a.basket_as_of

  union all

  select
    null::date,
    v_selected_count,
    0,
    null::numeric,
    null::date,
    0,
    0::numeric,
    0::numeric,
    null::date,
    null::date,
    'unavailable'::text,
    c.body,
    '[]'::jsonb
  from canonical c
  cross join safe_as_of a
  where a.basket_as_of is null
  order by market_date nulls last;
end
$function$;

comment on function public.get_pokemon_market_explorer_explicit_basket_series_v2(jsonb,date,date)
is 'Phase 6 Exact Basket V2. Resolves 1-25 asset-qualified physical card/sealed leaves only; one unit per canonical instrument; computes tracked value and common-cohort link values at one coherent basket as-of. No Builder filters or ranking axes are accepted. Existing application market-index primitives remain the canonical chain-link/index builder.';

revoke all on function public.get_pokemon_market_explorer_explicit_basket_series_v2(jsonb,date,date) from public;
revoke all on function public.get_pokemon_market_explorer_explicit_basket_series_v2(jsonb,date,date) from anon;
revoke all on function public.get_pokemon_market_explorer_explicit_basket_series_v2(jsonb,date,date) from authenticated;
grant execute on function public.get_pokemon_market_explorer_explicit_basket_series_v2(jsonb,date,date) to service_role;

create or replace function public.invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids uuid[])
returns jsonb
language plpgsql
security invoker
set search_path to ''
as $function$
declare
  v_era_ids text[];
  v_set_text text[];
  v_affected bigint := 0;
  v_generation bigint;
begin
  if p_set_ids is null or pg_catalog.cardinality(p_set_ids) = 0 then
    raise exception 'p_set_ids required';
  end if;

  select pg_catalog.array_agg(distinct x::text)
    into v_set_text
  from pg_catalog.unnest(p_set_ids) x;

  select pg_catalog.array_agg(distinct s.era_id::text)
    into v_era_ids
  from public.sets s
  where s.id = any(p_set_ids) and s.era_id is not null;

  update public.pokemon_market_explorer_query_cache q
     set status = 'stale',
         build_token = null,
         build_started_at = null,
         build_expires_at = null,
         updated_at = pg_catalog.clock_timestamp()
   where q.status in ('ready','building')
     and (
       (
         q.asset = 'cards'
         and (
           exists (
             select 1
             from pg_catalog.jsonb_array_elements_text(coalesce(q.normalized_spec->'setIds','[]'::jsonb)) s
             where s = any(v_set_text)
           )
           or exists (
             select 1
             from pg_catalog.jsonb_array_elements_text(coalesce(q.normalized_spec->'eraIds','[]'::jsonb)) e
             where e = any(coalesce(v_era_ids, array[]::text[]))
           )
           or (
             pg_catalog.jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb)) = 0
             and pg_catalog.jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb)) = 0
           )
         )
       )
       or (
         q.asset = 'mixed'
         and q.normalized_spec->>'membershipMode' = 'explicit'
         and exists (
           select 1
           from pg_catalog.jsonb_array_elements(coalesce(q.normalized_spec->'instruments','[]'::jsonb)) i(item)
           where (
             pg_catalog.lower(pg_catalog.btrim(i.item->>'asset')) = 'cards'
             and exists (
               select 1
               from public.pokemon_market_explorer_card_current_metadata m
               where m.card_variant_id = nullif(pg_catalog.btrim(i.item->>'instrumentId'),'')::uuid
                 and m.set_id = any(p_set_ids)
             )
           ) or (
             pg_catalog.lower(pg_catalog.btrim(i.item->>'asset')) = 'sealed'
             and exists (
               select 1
               from public.sealed_products sp
               where sp.id = nullif(pg_catalog.btrim(i.item->>'instrumentId'),'')::uuid
                 and sp.set_id = any(p_set_ids)
             )
           )
         )
       )
     );
  get diagnostics v_affected = row_count;

  update public.pokemon_market_explorer_cache_state
     set repair_generation = repair_generation + 1,
         updated_at = pg_catalog.clock_timestamp()
   where asset = 'cards'
   returning repair_generation into v_generation;

  return pg_catalog.jsonb_build_object(
    'affectedCacheRows', v_affected,
    'cardsRepairGeneration', v_generation,
    'setIds', pg_catalog.to_jsonb(v_set_text),
    'eraIds', pg_catalog.to_jsonb(coalesce(v_era_ids, array[]::text[]))
  );
end
$function$;

revoke all on function public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) from public;
revoke all on function public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) from anon;
revoke all on function public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) from authenticated;
grant execute on function public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) to service_role;
