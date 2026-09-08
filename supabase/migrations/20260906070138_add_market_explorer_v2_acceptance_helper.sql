create or replace function public.compare_pokemon_market_explorer_v2_shadow(
    p_set_ids uuid[],p_start_date date,p_end_date date,
    p_card_ids uuid[] default null,p_segment_ids text[] default null,p_pokemon_ids bigint[] default null,
    p_price_segment_ids text[] default null,p_release_age_cohort_ids text[] default null,p_top_n integer default null
)
returns jsonb
language sql
stable
set search_path to ''
set statement_timeout to '180s'
as $$
with legacy as materialized (
  select * from public.get_pokemon_market_explorer_filtered_cohort(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
), v2 as materialized (
  select * from public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,p_price_segment_ids,p_release_age_cohort_ids,p_top_n
  )
), keys as (
  select market_date from legacy union select market_date from v2
), compared as (
  select k.market_date,l.market_date is null legacy_missing,v.market_date is null v2_missing,
         case when l.market_date is null or v.market_date is null then true else (
           l.constituent_count is distinct from v.constituent_count or
           l.eligible_universe_count is distinct from v.eligible_universe_count or
           l.basket_value is distinct from v.basket_value or
           l.common_count is distinct from v.common_count or
           l.common_current_value is distinct from v.common_current_value or
           l.common_previous_value is distinct from v.common_previous_value or
           l.current_constituents is distinct from v.current_constituents
         ) end mismatch,
         case when l.market_date is not null and v.market_date is not null and (
           l.constituent_count is distinct from v.constituent_count or l.eligible_universe_count is distinct from v.eligible_universe_count
         ) then true else false end cohort_mismatch,
         case when l.market_date is not null and v.market_date is not null and (
           l.basket_value is distinct from v.basket_value or l.common_current_value is distinct from v.common_current_value or l.common_previous_value is distinct from v.common_previous_value
         ) then true else false end value_mismatch,
         case when l.market_date is not null and v.market_date is not null and l.current_constituents is distinct from v.current_constituents then true else false end payload_mismatch
  from keys k left join legacy l using(market_date) left join v2 v using(market_date)
)
select jsonb_build_object(
  'start_date',p_start_date,'end_date',p_end_date,
  'dates_checked',count(*),
  'missing_side',count(*) filter(where legacy_missing or v2_missing),
  'mismatches',count(*) filter(where mismatch),
  'cohort_mismatches',count(*) filter(where cohort_mismatch),
  'value_mismatches',count(*) filter(where value_mismatch),
  'payload_mismatches',count(*) filter(where payload_mismatch),
  'mismatch_dates',coalesce(jsonb_agg(market_date order by market_date) filter(where mismatch),'[]'::jsonb)
)
from compared;
$$;
revoke all on function public.compare_pokemon_market_explorer_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) from public,anon,authenticated;
grant execute on function public.compare_pokemon_market_explorer_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) to postgres,service_role;