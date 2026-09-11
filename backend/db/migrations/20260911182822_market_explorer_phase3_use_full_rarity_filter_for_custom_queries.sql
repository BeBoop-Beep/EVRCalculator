do $migration$
declare
  r record;
  v_definition text;
  v_rewritten text;
  v_total_replacements integer := 0;
  v_before integer;
  v_after integer;
begin
  for r in
    select p.oid
    from pg_proc p
    join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public'
      and p.oid::regprocedure::text in (
        'get_pokemon_market_explorer_filtered_cohort_materialized_series(uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer,uuid[])',
        'get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[])',
        'get_pokemon_market_explorer_filtered_cohort_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[])',
        'preflight_pokemon_market_explorer_filtered_cards_v1(uuid[],text[],bigint[],text[],text[],date)',
        'preflight_pokemon_market_explorer_query(uuid[],uuid[],text[],bigint[],text[],text[],date)'
      )
    order by p.oid::regprocedure::text
  loop
    v_definition := pg_get_functiondef(r.oid);
    v_before := regexp_count(v_definition, 'public\.market_explorer_rarity_segment\(m\.rarity\)');
    v_rewritten := replace(
      v_definition,
      'public.market_explorer_rarity_segment(m.rarity)',
      'public.market_explorer_filter_rarity_key(m.rarity)'
    );
    v_after := regexp_count(v_rewritten, 'public\.market_explorer_rarity_segment\(m\.rarity\)');
    if v_before = 0 or v_after <> 0 then
      raise exception 'unexpected rarity filter rewrite state for function oid %: before %, after %', r.oid, v_before, v_after;
    end if;
    v_total_replacements := v_total_replacements + v_before;
    execute v_rewritten;
  end loop;

  if v_total_replacements <> 6 then
    raise exception 'expected 6 custom-query rarity predicate replacements, got %', v_total_replacements;
  end if;
end;
$migration$;

comment on function public.market_explorer_rarity_segment(text) is
'Prepared Market Explorer rarity-market quality gate. Phase 3 intentionally leaves this narrow prepared-market primitive unchanged; custom query membership uses market_explorer_filter_rarity_key(text).';
