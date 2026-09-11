do $patch$
declare
  v_definition text;
  v_old text := 'and l.market_date between v_start and a.basket_as_of';
  v_new text := 'and l.market_date between least(v_start, a.basket_as_of) and a.basket_as_of';
begin
  select pg_catalog.pg_get_functiondef(p.oid)
    into v_definition
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'get_pokemon_market_explorer_explicit_basket_series_v2'
    and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_instruments jsonb, p_start_date date, p_end_date date';

  if v_definition is null or pg_catalog.strpos(v_definition, v_old) = 0 then
    raise exception 'Phase 6 Exact Basket V2 function body did not match expected range predicate';
  end if;

  execute pg_catalog.replace(v_definition, v_old, v_new);
end
$patch$;
