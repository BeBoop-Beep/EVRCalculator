create or replace function public.get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow(
    p_set_ids uuid[],p_start_date date,p_end_date date,
    p_card_ids uuid[] default null,p_segment_ids text[] default null,p_pokemon_ids bigint[] default null,
    p_price_segment_ids text[] default null,p_release_age_cohort_ids text[] default null,p_top_n integer default null
)
returns table(
    market_date date,constituent_count bigint,eligible_universe_count bigint,basket_value numeric,
    common_count bigint,common_current_value numeric,common_previous_value numeric,current_constituents jsonb
)
language plpgsql
stable
set search_path to ''
set statement_timeout to '300s'
as $$
begin
  if public.pokemon_market_explorer_daily_v2_shadow_covers(p_set_ids,p_start_date,p_end_date) then
    return query
    select * from public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(
      p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,p_price_segment_ids,p_release_age_cohort_ids,p_top_n
    );
  else
    return query
    select * from public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
      p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,p_price_segment_ids,p_release_age_cohort_ids,p_top_n
    );
  end if;
end;
$$;
revoke all on function public.get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) to postgres,service_role;