BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL, p_segment_ids text[] DEFAULT NULL,
  p_pokemon_ids bigint[] DEFAULT NULL, p_price_segment_ids text[] DEFAULT NULL,
  p_release_age_cohort_ids text[] DEFAULT NULL, p_top_n integer DEFAULT NULL
)
RETURNS TABLE(market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb)
LANGUAGE sql STABLE SECURITY INVOKER
AS $function$
  SELECT * FROM public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
) TO service_role;

COMMIT;
