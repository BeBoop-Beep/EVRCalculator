alter table public.pokemon_market_explorer_card_current_metadata
  add column filter_rarity_key text
  generated always as (public.market_explorer_filter_rarity_key(rarity)) stored;

do $migration$
declare
  r record;
  v_definition text;
  v_rewritten text;
  v_total_replacements integer := 0;
  v_before integer;
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
  loop
    v_definition := pg_get_functiondef(r.oid);
    v_before := regexp_count(v_definition, 'public\.market_explorer_filter_rarity_key\(m\.rarity\)');
    if v_before = 0 then
      raise exception 'expected filter-rarity expression in function oid %', r.oid;
    end if;
    v_rewritten := replace(v_definition,
      'public.market_explorer_filter_rarity_key(m.rarity)',
      'm.filter_rarity_key');
    if regexp_count(v_rewritten, 'public\.market_explorer_filter_rarity_key\(m\.rarity\)') <> 0 then
      raise exception 'rarity expression remained in function oid %', r.oid;
    end if;
    v_total_replacements := v_total_replacements + v_before;
    execute v_rewritten;
  end loop;
  if v_total_replacements <> 6 then
    raise exception 'expected 6 filter-rarity replacements, got %', v_total_replacements;
  end if;
end;
$migration$;

drop index public.idx_pokemon_market_explorer_card_filter_rarity_v1;

analyze public.pokemon_market_explorer_card_current_metadata;
