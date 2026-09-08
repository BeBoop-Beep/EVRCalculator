DO $do$
DECLARE
  v_def text;
BEGIN
  IF to_regprocedure('public.get_pokemon_market_explorer_cohort_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)') IS NULL THEN
    SELECT pg_get_functiondef('public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)'::regprocedure)
      INTO v_def;
    v_def := replace(v_def,
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort(',
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_cohort_legacy_shadow(');
    EXECUTE v_def;
  END IF;

  IF to_regprocedure('public.get_pokemon_market_explorer_cohort_daily_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)') IS NULL THEN
    SELECT pg_get_functiondef('public.get_pokemon_market_explorer_filtered_cohort_daily(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)'::regprocedure)
      INTO v_def;
    v_def := replace(v_def,
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily(',
      'CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_cohort_daily_legacy_shadow(');
    EXECUTE v_def;
  END IF;
END
$do$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_cohort_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_cohort_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) TO postgres, service_role;
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_cohort_daily_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_cohort_daily_legacy_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) TO postgres, service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[], p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb
)
LANGUAGE sql STABLE SET search_path=''
AS $function$
  SELECT * FROM public.get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[], p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb
)
LANGUAGE sql STABLE SET search_path=''
AS $function$
  SELECT * FROM public.get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
$function$;

CREATE OR REPLACE FUNCTION public.accept_pokemon_market_explorer_filtered_cohort_two_date(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[], p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb
)
LANGUAGE sql STABLE SET search_path='' SET statement_timeout='60s'
AS $function$
  SELECT * FROM public.get_pokemon_market_explorer_cohort_legacy_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
$function$;