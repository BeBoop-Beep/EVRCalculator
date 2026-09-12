drop function if exists public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
);

create function public.preflight_pokemon_market_explorer_filtered_cards_v1(
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
    previous_approved_market_date date,
    previous_matching_constituent_count bigint,
    previous_matching_set_count bigint,
    common_constituent_count bigint,
    current_chain_link_ready boolean,
    scope_set_count bigint,
    scope_projection_ready_set_count bigint,
    scope_projection_missing_set_count bigint,
    scope_projection_ready boolean,
    history_probe_projection_ready boolean,
    projection_retained_from date,
    projection_computed_through date,
    count_source text,
    history_probe_source text,
    preflight_status text
)
language sql
stable
security invoker
set search_path to ''
set statement_timeout to '5s'
as $function$
with approved_current as materialized (
    select max(q.market_date) as comparison_as_of
    from public.pokemon_market_date_quality q
    where q.tcg = 'pokemon'
      and q.status in ('READY', 'LEGACY_VERIFIED')
      and (p_comparison_as_of is null or q.market_date <= p_comparison_as_of)
),
approved_pair as materialized (
    select
        c.comparison_as_of,
        (
            select max(q.market_date)
            from public.pokemon_market_date_quality q
            where q.tcg = 'pokemon'
              and q.status in ('READY', 'LEGACY_VERIFIED')
              and c.comparison_as_of is not null
              and q.market_date < c.comparison_as_of
        ) as previous_approved_market_date
    from approved_current c
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
coverage as materialized (
    select
        count(c.set_id) filter (
            where a.comparison_as_of is not null
              and c.computed_through >= a.comparison_as_of
        )::bigint as current_ready_set_count,
        count(c.set_id) filter (
            where a.previous_approved_market_date is not null
              and c.retained_from <= a.previous_approved_market_date
              and c.computed_through >= a.comparison_as_of
        )::bigint as history_probe_ready_set_count,
        max(c.retained_from) as projection_retained_from,
        min(c.computed_through) as projection_computed_through
    from requested_sets r
    cross join approved_pair a
    left join public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
      on c.set_id = r.set_id
),
readiness as materialized (
    select
        a.comparison_as_of,
        a.previous_approved_market_date,
        s.scope_set_count,
        coalesce(c.current_ready_set_count, 0)::bigint as current_ready_set_count,
        greatest(s.scope_set_count - coalesce(c.current_ready_set_count, 0), 0)::bigint
            as current_missing_set_count,
        (
            a.comparison_as_of is not null
            and s.scope_set_count > 0
            and coalesce(c.current_ready_set_count, 0) = s.scope_set_count
        ) as scope_projection_ready,
        (
            a.previous_approved_market_date is not null
            and s.scope_set_count > 0
            and coalesce(c.history_probe_ready_set_count, 0) = s.scope_set_count
        ) as history_probe_projection_ready,
        c.projection_retained_from,
        c.projection_computed_through
    from approved_pair a
    cross join scope_summary s
    cross join coverage c
),
static_variants as materialized (
    select m.card_variant_id, m.set_id
    from public.pokemon_market_explorer_card_current_metadata m
    join requested_sets r on r.set_id = m.set_id
    where (
        p_segment_ids is null or cardinality(p_segment_ids) = 0
        or public.market_explorer_rarity_segment(m.rarity) = any(p_segment_ids)
    )
      and (
        p_pokemon_ids is noull or cardinality(p_pokemon_ids) = 0
        or exists (
            select 1
            from public.pokemon_card_desirability_links l
            where l.pokemon_canonical_card_id = m.canonical_card_id
              and l.pokemon_reference_id = any(p_pokemon_ids)
        )
      )
),
probe_dates as materialized (
    select r.comparison_as_of as market_date, 'current'::text as probe_kind
    from readiness r
    where r.scope_projection_ready
      and r.comparison_as_of is not null
    union all
    select r.previous_approved_market_date, 'previous'::text
    from readiness r
    where r.history_probe_projection_ready
      and r.previous_approved_market_date is not null
),
filtered as materialized (
    select d.probe_kind, d.market_date, s.card_variant_id, s.set_id
    from probe_dates d
    join public.pokemon_market_explorer_card_daily_states_v2_shadow s
      on s.market_date = d.market_date
    join static_variants v
      on v.card_variant_id = s.card_variant_id
     and v.set_id = s.set_id
    join public.sets sr on sr.id = s.set_id
    where (
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
counts as materialized (
    select
        count(*) filter (where f.probe_kind = 'current')::bigint as current_count,
        count(distinct f.set_id) filter (where f.probe_kind = 'current')::bigint
            as current_set_count,
        count(*) filter (where f.probe_kind = 'previous')::bigint as previous_count,
        count(distinct f.set_id) filter (where f.probe_kind = 'previous')::bigint
            as previous_set_count
    from filtered f
),
common as materialized (
    select count(*)::bigint as common_count
    from filtered cur
    join filtered prev
      on prev.probe_kind = 'previous'
     and prev.card_variant_id = cur.card_variant_id
     and prev.set_id = cur.set_id
    where cur.probe_kind = 'current'
)
select
    case when r.scope_projection_ready then c.current_count else null end
        as matching_constituent_count,
    case when r.scope_projection_ready then c.current_set_count else null end
        as matching_set_count,
    r.comparison_as_of,
    r.previous_approved_market_date,
    case when r.history_probe_projection_ready then c.previous_count else null end
        as previous_matching_constituent_count,
    case when r.history_probe_projection_ready then c.previous_set_count else null end
        as previous_matching_set_count,
    case when r.history_probe_projection_ready then x.common_count else null end
        as common_constituent_count,
    case
        when r.history_probe_projection_ready and c.current_count > 0
        then x.common_count > 0
        else false
    end as current_chain_link_ready,
    r.scope_set_count,
    r.current_ready_set_count as scope_projection_ready_set_count,
    r.current_missing_set_count as scope_projection_missing_set_count,
    r.scope_projection_ready,
    r.history_probe_projection_ready,
    r.projection_retained_from,
    r.projection_computed_through,
    case when r.scope_projection_ready then 'daily_v2' else 'unavailable' end as count_source,
    case when r.history_probe_projection_ready then 'daily_v2' else 'unavailable' end
        as history_probe_source,
    case
        when r.scope_set_count = 0 then 'invalid_scope'
        when r.comparison_as_of is null then 'no_approved_market_date'
        when not r.scope_projection_ready then 'projection_lagging'
        when c.current_count = 0 then 'empty'
        when not r.history_probe_projection_ready then 'history_probe_unavailable'
        when c.previous_count = 0 then 'current_only'
        when x.common_count = 0 then 'disconnected_current_segment'
        else 'ready'
    end as preflight_status
from readiness r
cross join counts c
cross join common x;
$function$;

comment on function public.preflight_pokemon_market_explorer_filtered_cards_v1(
    uuid[], text[], bigint[], text[], text[], date
) is'Cheap read-only Filtered Cards preflight. Counts the current V2 daily filtered cohort and probes only the immediately previous approved market date, using the same Set/Rarity/Pokemon/price/release-age predicates as the canonical V2 cohort. Returns null counts rather than falling back to expensive interval history when the hot projection is not ready. previous/common counts describe the current history edge; they do not claim that older disconnected chain segments are absent. Exact Basket membership is intentionally excluded.';

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