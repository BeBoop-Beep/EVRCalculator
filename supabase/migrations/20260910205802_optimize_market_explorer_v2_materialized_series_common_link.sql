create or replace function public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_use_v2 boolean,
  p_card_ids uuid[] default null::uuid[],
  p_segment_ids text[] default null::text[],
  p_pokemon_ids bigint[] default null::bigint[],
  p_price_segment_ids text[] default null::text[],
  p_release_age_cohort_ids text[] default null::text[],
  p_top_n integer default null::integer,
  p_card_variant_ids uuid[] default null::uuid[]
)
returns table(
  market_date date,
  constituent_count bigint,
  eligible_universe_count bigint,
  basket_value numeric,
  common_count bigint,
  common_current_value numeric,
  common_previous_value numeric
)
language plpgsql
stable
security invoker
set search_path to ''
set work_mem to '64MB'
set statement_timeout to '300s'
as $function$
begin
  if coalesce(p_use_v2, false) then
    return query
    with dates as materialized (
      select
        q.market_date as market_date,
        lag(q.market_date) over (order by q.market_date) as previous_market_date
      from public.pokemon_market_date_quality q
      where q.tcg = 'pokemon'
        and q.status in ('READY','LEGACY_VERIFIED')
        and q.market_date between p_start_date and p_end_date
    ),
    panel as materialized (
      select
        d.market_date,
        d.previous_market_date,
        s.card_variant_id,
        s.market_price
      from public.pokemon_market_explorer_card_daily_states_v2_shadow s
      join dates d on d.market_date = s.market_date
      join public.pokemon_market_explorer_card_current_metadata m
        on m.card_variant_id = s.card_variant_id
       and m.set_id = s.set_id
      join public.sets sr on sr.id = s.set_id
      where s.market_date between p_start_date and p_end_date
        and s.set_id = any(p_set_ids)
        and (
          p_card_variant_ids is null or cardinality(p_card_variant_ids) = 0
          or m.card_variant_id = any(p_card_variant_ids)
        )
        and (
          p_card_ids is null or cardinality(p_card_ids) = 0
          or m.canonical_card_id = any(p_card_ids)
        )
        and (
          p_segment_ids is null or cardinality(p_segment_ids) = 0
          or public.market_explorer_rarity_segment(m.rarity) = any(p_segment_ids)
        )
        and (
          p_pokemon_ids is null or cardinality(p_pokemon_ids) = 0
          or exists (
            select 1
            from public.pokemon_card_desirability_links l
            where l.pokemon_canonical_card_id = m.canonical_card_id
              and l.pokemon_reference_id = any(p_pokemon_ids)
          )
        )
        and (
          p_price_segment_ids is null or cardinality(p_price_segment_ids) = 0
          or ('obtainable' = any(p_price_segment_ids) and s.market_price < 10)
          or ('intermediate' = any(p_price_segment_ids) and s.market_price >= 10 and s.market_price < 100)
          or ('premium' = any(p_price_segment_ids) and s.market_price >= 100)
        )
        and (
          p_release_age_cohort_ids is null or cardinality(p_release_age_cohort_ids) = 0
          or (
            sr.release_date is not null
            and d.market_date >= sr.release_date
            and (
              ('new' = any(p_release_age_cohort_ids)
                and d.market_date - sr.release_date <= 180)
              or ('recent' = any(p_release_age_cohort_ids)
                and d.market_date - sr.release_date between 181 and 730)
              or ('established' = any(p_release_age_cohort_ids)
                and d.market_date - sr.release_date between 731 and 1825)
              or ('legacy' = any(p_release_age_cohort_ids)
                and d.market_date - sr.release_date > 1825)
            )
          )
        )
    ),
    eligible as materialized (
      select p.market_date, count(*)::bigint as n
      from panel p
      group by p.market_date
    ),
    ranked as materialized (
      select
        p.*,
        row_number() over (
          partition by p.market_date
          order by p.market_price desc, p.card_variant_id
        ) as market_rank
      from panel p
      where p_top_n is not null
    ),
    selected as materialized (
      select p.*, null::bigint as market_rank
      from panel p
      where p_top_n is null
      union all
      select r.*
      from ranked r
      where r.market_rank <= p_top_n
    ),
    linked as materialized (
      select
        s.*,
        lag(s.market_date) over (
          partition by s.card_variant_id
          order by s.market_date
        ) as prior_selected_date,
        lag(s.market_price) over (
          partition by s.card_variant_id
          order by s.market_date
        ) as prior_selected_price
      from selected s
    )
    select
      l.market_date,
      count(*)::bigint,
      e.n::bigint,
      sum(l.market_price)::numeric,
      count(*) filter (
        where l.prior_selected_date = l.previous_market_date
      )::bigint,
      coalesce(
        sum(l.market_price) filter (
          where l.prior_selected_date = l.previous_market_date
        ),
        0
      )::numeric,
      coalesce(
        sum(l.prior_selected_price) filter (
          where l.prior_selected_date = l.previous_market_date
        ),
        0
      )::numeric
    from linked l
    join eligible e on e.market_date = l.market_date
    group by l.market_date, e.n
    order by l.market_date;
  else
    return query
    select
      q.market_date,
      q.constituent_count,
      q.eligible_universe_count,
      q.basket_value,
      q.common_count,
      q.common_current_value,
      q.common_previous_value
    from public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
      p_set_ids,
      p_start_date,
      p_end_date,
      p_card_ids,
      p_segment_ids,
      p_pokemon_ids,
      p_price_segment_ids,
      p_release_age_cohort_ids,
      p_top_n,
      p_card_variant_ids
    ) q;
  end if;
end;
$function$;