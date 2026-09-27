-- Compact, read-only membership/readiness preflight for Cards Market Explorer.
-- It intentionally accepts only resolved set scope. Era expansion remains in
-- the application service that already owns canonical tracked-set resolution.
create or replace function public.preflight_pokemon_market_explorer_query(
  p_set_ids uuid[],
  p_card_variant_ids uuid[] default null,
  p_segment_ids text[] default null,
  p_pokemon_ids bigint[] default null,
  p_price_segment_ids text[] default null,
  p_release_age_cohort_ids text[] default null,
  p_comparison_as_of date default null
)
returns table(
  matched_current_constituent_count bigint,
  matched_set_count bigint,
  has_current_membership boolean,
  has_usable_history boolean,
  canonical_through date,
  reason_code text
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '5s'
as $$
declare
  v_canonical_through date;
  v_previous_date date;
begin
  if p_set_ids is null or cardinality(p_set_ids) = 0 then
    raise exception 'p_set_ids must contain resolved tracked set ids'
      using errcode = '22023';
  end if;
  if p_card_variant_ids is not null and cardinality(p_card_variant_ids) > 0 then
    raise exception 'explicit instrument membership is not supported by filtered preflight'
      using errcode = '22023';
  end if;

  select least(
    coalesce(p_comparison_as_of, max(q.market_date)),
    max(q.market_date),
    min(c.computed_through)
  )
  into v_canonical_through
  from public.pokemon_market_date_quality q
  cross join public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
  where q.tcg = 'pokemon'
    and q.status in ('READY', 'LEGACY_VERIFIED')
    and c.set_id = any(p_set_ids);

  if v_canonical_through is null
     or (select count(*) from public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
         where c.set_id = any(p_set_ids) and c.computed_through >= v_canonical_through)
        <> cardinality(p_set_ids) then
    return query select 0::bigint, 0::bigint, false, false,
      v_canonical_through, 'SOURCE_COVERAGE_MISSING'::text;
    return;
  end if;

  select max(q.market_date) into v_previous_date
  from public.pokemon_market_date_quality q
  where q.tcg = 'pokemon'
    and q.status in ('READY', 'LEGACY_VERIFIED')
    and q.market_date < v_canonical_through;

  return query
  with static_variants as materialized (
    select m.card_variant_id, m.set_id
    from public.pokemon_market_explorer_card_current_metadata m
    join public.sets sr on sr.id = m.set_id
    where m.set_id = any(p_set_ids)
      and (p_segment_ids is null or cardinality(p_segment_ids) = 0
           or public.market_explorer_rarity_segment(m.rarity) = any(p_segment_ids))
      and (p_pokemon_ids is null or cardinality(p_pokemon_ids) = 0 or exists (
        select 1 from public.pokemon_card_desirability_links l
        where l.pokemon_canonical_card_id = m.canonical_card_id
          and l.pokemon_reference_id = any(p_pokemon_ids)
      ))
      and (p_release_age_cohort_ids is null or cardinality(p_release_age_cohort_ids) = 0 or (
        sr.release_date is not null and v_canonical_through >= sr.release_date and (
          ('new' = any(p_release_age_cohort_ids) and v_canonical_through - sr.release_date <= 180)
          or ('recent' = any(p_release_age_cohort_ids) and v_canonical_through - sr.release_date between 181 and 730)
          or ('established' = any(p_release_age_cohort_ids) and v_canonical_through - sr.release_date between 731 and 1825)
          or ('legacy' = any(p_release_age_cohort_ids) and v_canonical_through - sr.release_date > 1825)
        )
      ))
  ), current_members as materialized (
    select s.card_variant_id, s.set_id
    from static_variants v
    join public.pokemon_market_explorer_card_daily_states_v2_shadow s
      on s.card_variant_id = v.card_variant_id
     and s.set_id = v.set_id
     and s.market_date = v_canonical_through
    where p_price_segment_ids is null or cardinality(p_price_segment_ids) = 0
      or ('obtainable' = any(p_price_segment_ids) and s.market_price < 10)
      or ('intermediate' = any(p_price_segment_ids) and s.market_price >= 10 and s.market_price < 100)
      or ('premium' = any(p_price_segment_ids) and s.market_price >= 100)
  ), counts as (
    select count(*)::bigint as member_count, count(distinct set_id)::bigint as set_count
    from current_members
  ), history as (
    select exists (
      select 1
      from current_members cur
      join public.pokemon_market_explorer_card_daily_states_v2_shadow prev
        on prev.card_variant_id = cur.card_variant_id
       and prev.set_id = cur.set_id
       and prev.market_date = v_previous_date
      where p_price_segment_ids is null or cardinality(p_price_segment_ids) = 0
        or ('obtainable' = any(p_price_segment_ids) and prev.market_price < 10)
        or ('intermediate' = any(p_price_segment_ids) and prev.market_price >= 10 and prev.market_price < 100)
        or ('premium' = any(p_price_segment_ids) and prev.market_price >= 100)
    ) as ready
  )
  select c.member_count, c.set_count, c.member_count > 0,
         c.member_count > 0 and h.ready,
         v_canonical_through,
         case when c.member_count = 0 then 'EMPTY_NOW'
              when not h.ready then 'NO_USABLE_HISTORY'
              else 'READY' end
  from counts c cross join history h;
end;
$$;

comment on function public.preflight_pokemon_market_explorer_query(
  uuid[],uuid[],text[],bigint[],text[],text[],date
) is 'Read-only two-date Cards Market Explorer filtered membership/readiness preflight; never builds an index or returns constituent IDs.';

revoke all on function public.preflight_pokemon_market_explorer_query(
  uuid[],uuid[],text[],bigint[],text[],text[],date
) from public, anon, authenticated;
grant execute on function public.preflight_pokemon_market_explorer_query(
  uuid[],uuid[],text[],bigint[],text[],text[],date
) to service_role;
