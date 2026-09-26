do $$
declare
  v_oid oid;
  v_def text;
  v_old text := E'WHERE (cv.special_type IS NULL OR cv.special_type = \'\')\n          AND (cv.printing_type IS NULL OR cv.printing_type IN (\'holo\', \'non-holo\'))';
  v_new text := E'WHERE (cv.special_type IS NULL OR cv.special_type = \'\'\n               OR EXISTS (\n                   SELECT 1 FROM public.cards c_name\n                   WHERE c_name.id = ccl.card_id\n                     AND lower(regexp_replace(coalesce(c_name.name, \'\'), \'[^a-zA-Z0-9]+\', \'\', \'g\')) = \'pokeball\'\n               ))\n          AND (cv.printing_type IS NULL OR cv.printing_type IN (\'holo\', \'non-holo\'))';
  v_name text;
begin
  foreach v_name in array array['refresh_pokemon_set_value_daily_history','get_pokemon_cards_daily_constituents'] loop
    select p.oid into v_oid
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname=v_name and p.prokind='f'
    order by p.oid limit 1;
    if v_oid is null then raise exception 'Function % not found',v_name; end if;
    select pg_get_functiondef(v_oid) into v_def;
    if position(v_old in v_def)=0 then
      raise exception 'Expected variant-filter fragment not found in %; refusing unsafe rewrite',v_name;
    end if;
    v_def := replace(v_def,v_old,v_new);
    execute v_def;
  end loop;
end $$;
