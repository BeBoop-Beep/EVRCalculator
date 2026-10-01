begin;

-- Market Explorer rarity staging already keeps historical rows narrow and uses
-- a previous-date self-join for chain-linking. The remaining production timeout
-- occurred after history construction when current-day totals/constituents
-- rescanned the full ~2.5M-row historical temp relation.
--
-- Materialize the current day once (~28k rows) and route only current-output
-- reads through that subset. Historical chain-link math is untouched.
do $body$
declare
  v_def text;
  v_anchor_old text := '  create index on _mx_rarity_members(rarity_key,market_date,card_variant_id);' || chr(10) ||
                       '  analyze _mx_rarity_members;' || chr(10) || chr(10) ||
                       '  insert into public.pokemon_market_explorer_surface_directory_v2(';
  v_anchor_new text := '  create index on _mx_rarity_members(rarity_key,market_date,card_variant_id);' || chr(10) ||
                       '  analyze _mx_rarity_members;' || chr(10) || chr(10) ||
                       '  drop table if exists pg_temp._mx_rarity_current;' || chr(10) ||
                       '  create temp table _mx_rarity_current on commit drop as' || chr(10) ||
                       '  select * from _mx_rarity_members where market_date=p_market_date;' || chr(10) ||
                       '  create index on _mx_rarity_current(market_key,market_price desc,card_variant_id);' || chr(10) ||
                       '  analyze _mx_rarity_current;' || chr(10) || chr(10) ||
                       '  insert into public.pokemon_market_explorer_surface_directory_v2(';
begin
  select pg_get_functiondef(
    'public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)'::regprocedure
  ) into v_def;

  if position('create temp table _mx_rarity_current on commit drop as' in v_def)>0 then
    return;
  end if;

  if position(v_anchor_old in v_def)=0 then
    raise exception 'RARITY_CURRENT_SUBSET_ANCHOR_NOT_FOUND';
  end if;
  if position('from _mx_rarity_members x' in v_def)=0 then
    raise exception 'RARITY_CURRENT_SUBSET_X_SOURCE_NOT_FOUND';
  end if;
  if position('from _mx_rarity_members d' in v_def)=0 then
    raise exception 'RARITY_CURRENT_SUBSET_D_SOURCE_NOT_FOUND';
  end if;

  v_def := replace(v_def,v_anchor_old,v_anchor_new);
  v_def := replace(v_def,'from _mx_rarity_members x','from _mx_rarity_current x');
  v_def := replace(v_def,'from _mx_rarity_members d','from _mx_rarity_current d');

  execute v_def;
end;
$body$;

commit;
