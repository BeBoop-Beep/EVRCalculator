create or replace function public.get_pokemon_market_explorer_set_context_ranking_v1(
  p_set_id uuid,
  p_ranking text,
  p_timeframe text default '7D',
  p_limit integer default 10,
  p_as_of date default null
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
set work_mem = '16MB'
as $$
declare
  v_as_of date;
  v_days integer;
  v_baseline date;
  v_current_count integer;
  v_baseline_count integer;
  v_items jsonb;
begin
  if p_set_id is null then
    raise exception 'set id is required';
  end if;
  if p_ranking not in ('value','risers','fallers') then
    raise exception 'ranking must be value, risers, or fallers';
  end if;
  if p_limit is null or p_limit < 1 or p_limit > 25 then
    raise exception 'ranking limit must be 1..25';
  end if;
  if p_timeframe not in ('7D','30D','90D') then
    raise exception 'supported contextual timeframes are 7D, 30D, 90D';
  end if;

  select coalesce(
    p_as_of,
    max(q.market_date) filter(where q.status in ('READY','LEGACY_VERIFIED'))
  ) into v_as_of
  from public.pokemon_market_date_quality q;

  if v_as_of is null then
    return jsonb_build_object('available',false,'reason','no_approved_market_date','items','[]'::jsonb);
  end if;

  v_days := case p_timeframe when '7D' then 7 when '30D' then 30 when '90D' then 90 end;
  v_baseline := v_as_of - v_days;

  select count(*) into v_current_count
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d
  where d.set_id=p_set_id and d.market_date=v_as_of and d.market_price > 0;

  if v_current_count=0 then
    return jsonb_build_object(
      'available',false,'reason','current_projection_unavailable','setId',p_set_id,
      'ranking',p_ranking,'timeframe',p_timeframe,'asOf',v_as_of,'baselineDate',v_baseline,
      'items','[]'::jsonb
    );
  end if;

  if p_ranking in ('risers','fallers') then
    select count(*) into v_baseline_count
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    where d.set_id=p_set_id and d.market_date=v_baseline and d.market_price > 0;
    if v_baseline_count=0 then
      return jsonb_build_object(
        'available',false,'reason','baseline_projection_unavailable','setId',p_set_id,
        'ranking',p_ranking,'timeframe',p_timeframe,'asOf',v_as_of,'baselineDate',v_baseline,
        'items','[]'::jsonb
      );
    end if;
  end if;

  if p_ranking='value' then
    select coalesce(jsonb_agg(to_jsonb(x) order by x.rank),'[]'::jsonb)
    into v_items
    from (
      select row_number() over(order by d.market_price desc,d.card_variant_id)::integer as rank,
             d.card_variant_id as "cardVariantId",
             m.canonical_card_id as "canonicalCardId",
             m.card_name as name,
             m.card_number as "cardNumber",
             m.rarity,
             m.edition,
             m.printing_type as "printingType",
             m.special_type as "specialType",
             m.image_url as "imageUrl",
             d.market_price::numeric as "marketPrice",
             null::numeric as "baselinePrice",
             null::numeric as "changeAmount",
             null::numeric as "changePercent"
      from public.pokemon_market_explorer_card_daily_states_v2_shadow d
      left join public.pokemon_market_explorer_card_current_metadata m using(card_variant_id)
      where d.set_id=p_set_id and d.market_date=v_as_of and d.market_price > 0
      order by d.market_price desc,d.card_variant_id
      limit p_limit
    ) x;
  else
    select coalesce(jsonb_agg(to_jsonb(x) order by x.rank),'[]'::jsonb)
    into v_items
    from (
      select row_number() over(
               order by
                 case when p_ranking='risers' then ((cur.market_price/base.market_price)-1.0)*100.0 end desc nulls last,
                 case when p_ranking='fallers' then ((cur.market_price/base.market_price)-1.0)*100.0 end asc nulls last,
                 cur.market_price desc,
                 cur.card_variant_id
             )::integer as rank,
             cur.card_variant_id as "cardVariantId",
             m.canonical_card_id as "canonicalCardId",
             m.card_name as name,
             m.card_number as "cardNumber",
             m.rarity,
             m.edition,
             m.printing_type as "printingType",
             m.special_type as "specialType",
             m.image_url as "imageUrl",
             cur.market_price::numeric as "marketPrice",
             base.market_price::numeric as "baselinePrice",
             (cur.market_price-base.market_price)::numeric as "changeAmount",
             (((cur.market_price/base.market_price)-1.0)*100.0)::numeric as "changePercent"
      from public.pokemon_market_explorer_card_daily_states_v2_shadow cur
      join public.pokemon_market_explorer_card_daily_states_v2_shadow base
        on base.card_variant_id=cur.card_variant_id
       and base.set_id=cur.set_id
       and base.market_date=v_baseline
       and base.market_price > 0
      left join public.pokemon_market_explorer_card_current_metadata m using(card_variant_id)
      where cur.set_id=p_set_id and cur.market_date=v_as_of and cur.market_price > 0
      order by
        case when p_ranking='risers' then ((cur.market_price/base.market_price)-1.0)*100.0 end desc nulls last,
        case when p_ranking='fallers' then ((cur.market_price/base.market_price)-1.0)*100.0 end asc nulls last,
        cur.market_price desc,
        cur.card_variant_id
      limit p_limit
    ) x;
  end if;

  return jsonb_build_object(
    'available',true,
    'setId',p_set_id,
    'ranking',p_ranking,
    'timeframe',p_timeframe,
    'asOf',v_as_of,
    'baselineDate',case when p_ranking='value' then null else v_baseline end,
    'limit',p_limit,
    'items',v_items,
    'source','pokemon_market_explorer_card_daily_states_v2_shadow'
  );
end;
$$;

revoke all on function public.get_pokemon_market_explorer_set_context_ranking_v1(uuid,text,text,integer,date) from public, anon, authenticated;
grant execute on function public.get_pokemon_market_explorer_set_context_ranking_v1(uuid,text,text,integer,date) to service_role;

comment on function public.get_pokemon_market_explorer_set_context_ranking_v1(uuid,text,text,integer,date) is
'Phase 5 bounded contextual Set analytical read. Value ranks current V2 card variants; risers/fallers compare exact elapsed 7D/30D/90D V2 observations. Does not create or mutate Market membership or query-cache state.';
