do $patch$
declare
  v_definition text;
  v_old_cards text := $old$  valid_cards as materialized (
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
  ),$old$;
  v_new_cards text := $new$  valid_cards as materialized (
    select s.asset, s.instrument_id
    from selected s
    join public.pokemon_market_explorer_card_current_metadata m
      on s.asset = 'cards' and m.card_variant_id = s.instrument_id
  ),$new$;
  v_old_sealed text := $old$  valid_sealed as materialized (
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
  ),$old$;
  v_new_sealed text := $new$  valid_sealed as materialized (
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
      )
  ),$new$;
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'get_pokemon_market_explorer_explicit_basket_series_v2'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_instruments jsonb, p_start_date date, p_end_date date';

  if v_definition is null
     or pg_catalog.strpos(v_definition, v_old_cards) = 0
     or pg_catalog.strpos(v_definition, v_old_sealed) = 0 then
    raise exception 'Phase 6 Exact Basket V2 identity-validation patch did not match expected body';
  end if;

  v_definition := pg_catalog.replace(v_definition, v_old_cards, v_new_cards);
  v_definition := pg_catalog.replace(v_definition, v_old_sealed, v_new_sealed);
  v_definition := pg_catalog.replace(
    v_definition,
    'Exact Basket V2 contains an unknown, aggregate, or currently ineligible leaf instrument',
    'Exact Basket V2 contains an unknown or non-leaf instrument'
  );
  execute v_definition;
end
$patch$;
