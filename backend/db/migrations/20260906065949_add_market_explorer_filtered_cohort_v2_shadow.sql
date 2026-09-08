do $$
declare
  v_def text;
begin
  select pg_get_functiondef('public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)'::regprocedure) into v_def;
  v_def:=replace(v_def,'FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(','FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(');
  v_def:=replace(v_def,'public.pokemon_market_explorer_card_daily_coverage','public.pokemon_market_explorer_card_daily_coverage_v2_shadow');
  v_def:=replace(v_def,'public.pokemon_market_explorer_card_daily_states','public.pokemon_market_explorer_card_daily_states_v2_shadow');
  execute v_def;
end
$$;
revoke all on function public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) to postgres,service_role;