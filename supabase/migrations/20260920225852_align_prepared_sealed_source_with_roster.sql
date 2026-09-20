-- The D3 sealed roster is the global market snapshot, not the latest
-- per-set product-history point. The prepared source date must be a date
-- supported by both authorities; the existing complete-roster guard then
-- requires the roster snapshot to match that date exactly.
do $$
declare
  v_sql text;
  v_old text := '  select min(family_max)' || chr(10) ||
    '  into v_sealed_source_asof';
  v_new text := '  select least(min(family_max),' || chr(10) ||
    '    (select s.market_date from public.pokemon_explore_set_value_snapshot_latest s' || chr(10) ||
    '     where s.tcg=''pokemon'' and s.scope=''market''))' || chr(10) ||
    '  into v_sealed_source_asof';
begin
  select pg_get_functiondef('public.refresh_pokemon_market_explorer_prepared_directory_v1()'::regprocedure)
    into v_sql;
  if position(v_old in v_sql)=0 then
    raise exception 'prepared sealed source expression changed; refusing unsafe rewrite';
  end if;
  execute replace(v_sql,v_old,v_new);
end;
$$;
