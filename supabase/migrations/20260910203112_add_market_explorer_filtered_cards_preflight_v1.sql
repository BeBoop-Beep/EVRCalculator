create or replace function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    p_set_ids uuid[],
    p_segment_ids text[] default null,
    p_pokemon_ids bigint[] default null,
    p_price_segment_ids text[] default null,
    p_release_age_cohort_ids text[] default null,
    p_comparison_as_of date default null
)
returns table(
    matching_constituent_count bigint,
    matching_set_count bigint,
    comparison_as_of date,
    scope_set_count bigint,
    scope_projection_ready_set_count bigint,
    scope_projection_missing_set_count bigint,
    scope_projection_ready boolean,
    projection_retained_from date,
    projection_computed_through date,
    matching_history_ready_set_count bigint,
    matching_history_missing_set_count bigint,
    matching_history_current_set_count bigint,
    history_first_date date,
    history_latest_date date,
    history_buildable boolean,
    count_source text,
    preflight_status text
)
language sql
stable
security invoker
set search_path to ''
set statement_timeout to '5s'
as $function$
with approved as materialized (
    select max(q.market_date) as comparison_as_of
    from public.pokemon_market_date_quality q
    where q.tcg = 'pokemon'
      and q.status in ('READY', 'LEGACY_VERIFIED')
      and (p_comparison_as_of is null or q.market_date <= p_comparison_as_of)
),
requested_sets as materialized (
    select distinct u.set_id
    from unnest(coalesce(p_set_ids, '{}'::uuid[])) as u(set_id)
    where u.set_id is not null
),
scope_summary as materialized (
    select count(*)::bigint as scope_set_count
    from requested_sets
),
scope_projection as materialized (
    select
        count(c.set_id) filter (
            where a.comparison_as_of is not null
              and c.retained_from <= a.comparison_as_of
              and c.computed_through >= a.comparison_as_of
        )::bigint as ready_set_count,
        max(c.retained_from) as projection_retained_from,
        min(c.computed_through) as projection_computed_through
    from requested_sets r
    cross join approved a
    left join public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
      on c.set_id = r.set_id
),
source_choice as materialized (
    select
        a.comparison_as_of,
        s.scope_set_count,
        coalesce(p.ready_set_count, 0)::bigint as ready_set_count,
        greatest(s.scope_set_count - coalesce(p.ready_set_count, 0), 0)::bigint as missing_set_count,
        (
            a.comparison_as_of is not null
            and s.scope_set_count > 0
            and coalesce(p.ready_set_count, 0) = s.scope_set_count
        ) as scope_projection_ready,
        p.projection_retained_from,
        p.projection_computed_through
    from approved a
    cross join scope_summary s
    cross join scope_projection p
),
current_prices as materialized (
    select s.card_variant_id, s.set_id, s.market_price
    from public.pokemon_market_explorer_card_daily_states_v2_shadow s
    join requested_sets r on r.set_id = s.set_id
    cross join source_choice ch
    where ch.scope_projection_ready
      and s.market_date = ch.comparison_as_of

    union all

    select i.card_variant_id, i.set_id, i.market_price
    from public.pokemon_market_price_intervals_v2_shadow i
    join requested_sets r on r.set_id = i.set_id
    cross join source_choice ch
    where not ch.scope_projection_ready
      and ch.comparison_as_of is not null
      and i.valid_from <= ch.comparison_as_of
      and (i.valid_to is null or ch.comparison_as_of < i.valid_to)
),
filtered as materialized (
    select cp.card_variant_id, cp.set_id
    from current_prices cp
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id = cp.card_variant_id
     and m.set_id = cp.set_id
    join public.sets sr on sr.id = cp.set_id
    cross join source_choice ch
    where (
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
        or ('obtainable' = any(p_price_segment_ids) and cp.market_price < 10)
        or ('intermediate' = any(p_price_segment_ids) and cp.market_price >= 10 and cp.market_price < 100)
        or ('premium' = any(p_price_segment_ids) and cp.market_price >= 100)
      )
      and (
        p_release_age_cohort_ids is null or cardinality(p_release_age_cohort_ids) = 0
        or (
            sr.release_date is not null
            and ch.comparison_as_of >= sr.release_date
            and (
                ('new' = any(p_release_age_cohort_ids)
                    and ch.comparison_as_of - sr.release_date <= 180)
                or ('recent' = any(p_release_age_cohort_ids)
                    and ch.comparison_as_of - sr.release_date between 181 and 730)
                or ('established' = any(p_release_age_cohort_ids)
                    and ch.comparison_as_of - sr.release_date between 731 and 1825)
                or ('legacy' = any(p_release_age_cohort_ids)
                    and ch.comparison_as_of - sr.release_date > 1825)
            )
        )
      )
),
match_summary as materialized (
    select
        count(*)::bigint as matching_constituent_count,
        count(distinct f.set_id)::bigint as matching_set_count,
        coalesce(array_agg(distinct f.set_id), '{}'::uuid[]) as matching_set_ids
    from filtered f
),
history_summary as materialized (
    select
        count(distinct x.set_id) filter (where h.has_history is true)::bigint
            as history_ready_set_count,
        count(distinct x.set_id) filter (
            where h.has_history is true
              and a.comparison_as_of is not null
              and h.latest_snapshot_date >= a.comparison_as_of
        )::bigint as history_current_set_count,
        min(h.first_snapshot_date) filter (where h.has_history is true) as history_first_date,
        max(h.latest_snapshot_date) filter (where h.has_history is true) as history_latest_date
    from match_summary m
    cross join approved a
    left join lateral unnest(m.matching_set_ids) as x(set_id) on true
    left join public.pokemon_set_value_daily_history_coverage h
      on h.set_id = x.set_id
)
select
    m.matching_constituent_count,
    m.matching_set_count,
    ch.comparison_as_of,
    ch.scope_set_count,
    ch.ready_set_count as scope_projection_ready_set_count,
    ch.missing_set_count as scope_projection_missing_set_count,
    ch.scope_projection_ready,
    ch.projection_retained_from,
    ch.projection_computed_through,
    coalesce(h.history_ready_set_count, 0)::bigint as matching_history_ready_set_count,
    greatest(m.matching_set_count - coalesce(h.history_ready_set_count, 0), 0)::bigint
        as matching_history_missing_set_count,
    coalesce(h.history_current_set_count, 0)::bigint as matching_history_current_set_count,
    h.history_first_date,
    h.history_latest_date,
    (
        m.matching_constituent_count > 0
        and coalesce(h.history_ready_set_count, 0) = m.matching_set_count
        and coalesce(h.history_current_set_count, 0) = m.matching_set_count
    ) as history_buildable,
    case
        when ch.comparison_as_of is null then 'none'
        when ch.scope_projection_ready then 'daily_v2'
        else 'interval_v2_fallback'
    end as count_source,
    case
        when ch.comparison_as_of is null then 'no_approved_market_date'
        when m.matching_constituent_count = 0 then 'empty'
        when coalesce(h.history_ready_set_count, 0) < m.matching_set_count then 'history_unavailable'
        when coalesce(h.history_current_set_count, 0) < m.matching_set_count then 'history_lagging'
        when not ch.scope_projection_ready then 'projection_lagging'
        else 'ready'
    end as preflight_status
from match_summary m
cross join source_choice ch
cross join history_summary h;
$function$;

comment on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) is
'Cheap read-only point-in-time preflight for Filtered Cards Market Explorer queries. Uses the V2 daily projection when the requested set scope is covered through comparison_as_of and falls back to V2 price intervals only when the daily projection is not fully ready. Mirrors the live rarity, Pokemon, price-segment, release-age, and set-scope predicates before Top-N. Exact Basket membership is intentionally excluded.';

revoke all on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) from public;
revoke all on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) from anon;
revoke all on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) from authenticated;
grant execute on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) to service_role;