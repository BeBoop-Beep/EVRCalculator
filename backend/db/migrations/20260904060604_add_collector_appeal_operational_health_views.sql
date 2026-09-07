create or replace view public.pokemon_collector_source_run_health_v
with (security_invoker = true)
as
select
    s.id as source_run_id,
    s.source_name,
    s.source_kind,
    s.run_key,
    s.capture_version,
    s.status,
    s.started_at,
    s.completed_at,
    s.captured_at,
    s.item_count as declared_item_count,
    coalesce(e.entity_observation_count, 0)::integer as entity_observation_count,
    coalesce(p.playability_observation_count, 0)::integer as playability_observation_count,
    (coalesce(e.entity_observation_count, 0) + coalesce(p.playability_observation_count, 0))::integer as total_observation_count,
    coalesce(e.matched_entity_count, 0)::integer as matched_entity_count,
    coalesce(e.unresolved_entity_count, 0)::integer as unresolved_entity_count,
    coalesce(p.matched_playability_count, 0)::integer as matched_playability_count,
    coalesce(p.unresolved_playability_count, 0)::integer as unresolved_playability_count,
    case
        when s.source_kind in ('fan_ranking','search_interest') then coalesce(e.entity_observation_count, 0)::integer
        when s.source_kind = 'playability' then coalesce(p.playability_observation_count, 0)::integer
        else (coalesce(e.entity_observation_count, 0) + coalesce(p.playability_observation_count, 0))::integer
    end as expected_evidence_row_count,
    case
        when s.item_count is null then null
        when s.source_kind in ('fan_ranking','search_interest') then s.item_count = coalesce(e.entity_observation_count, 0)
        when s.source_kind = 'playability' then s.item_count = coalesce(p.playability_observation_count, 0)
        else s.item_count = (coalesce(e.entity_observation_count, 0) + coalesce(p.playability_observation_count, 0))
    end as item_count_consistent,
    (s.status <> 'running') as is_terminal,
    (s.status in ('success','partial_failure')) as usable_for_model,
    s.source_fingerprint,
    s.diagnostics_json
from public.pokemon_collector_source_runs s
left join lateral (
    select
        count(*) as entity_observation_count,
        count(*) filter (where o.match_status = 'matched') as matched_entity_count,
        count(*) filter (where o.match_status in ('unmatched','ambiguous')) as unresolved_entity_count
    from public.pokemon_collector_entity_observations o
    where o.source_run_id = s.id
) e on true
left join lateral (
    select
        count(*) as playability_observation_count,
        count(*) filter (where o.match_status = 'matched') as matched_playability_count,
        count(*) filter (where o.match_status in ('unmatched','ambiguous')) as unresolved_playability_count
    from public.pokemon_playability_event_observations o
    where o.source_run_id = s.id
) p on true;

create or replace view public.pokemon_collector_appeal_model_run_health_v
with (security_invoker = true)
as
select
    m.id as model_run_id,
    m.model_version,
    m.as_of_date,
    m.status,
    m.validation_passed,
    cardinality(m.source_run_ids) as declared_source_count,
    coalesce(src.linked_source_count, 0)::integer as linked_source_count,
    coalesce(src.bad_source_count, 0)::integer as bad_source_count,
    coalesce(es.entity_score_count, 0)::integer as entity_score_count,
    coalesce(ps.playability_score_count, 0)::integer as playability_score_count,
    coalesce(cs.card_score_count, 0)::integer as actual_card_score_count,
    coalesce(ss.set_score_count, 0)::integer as actual_set_score_count,
    m.card_score_count as declared_card_score_count,
    m.set_score_count as declared_set_score_count,
    cardinality(m.source_run_ids) = coalesce(src.linked_source_count, 0) as source_lineage_consistent,
    (m.card_score_count is null or m.card_score_count = coalesce(cs.card_score_count, 0)) as card_count_consistent,
    (m.set_score_count is null or m.set_score_count = coalesce(ss.set_score_count, 0)) as set_count_consistent,
    (cur.model_run_id is not null) as is_current,
    (
        m.status = 'validated'
        and m.validation_passed
        and coalesce(src.bad_source_count, 0) = 0
        and cardinality(m.source_run_ids) = coalesce(src.linked_source_count, 0)
        and coalesce(cs.card_score_count, 0) > 0
        and coalesce(ss.set_score_count, 0) > 0
        and (m.card_score_count is null or m.card_score_count = coalesce(cs.card_score_count, 0))
        and (m.set_score_count is null or m.set_score_count = coalesce(ss.set_score_count, 0))
    ) as ready_to_promote,
    m.validation_json,
    m.diagnostics_json,
    m.started_at,
    m.completed_at,
    m.published_at
from public.pokemon_collector_appeal_model_runs m
left join lateral (
    select
        count(*) as linked_source_count,
        count(*) filter (where s.status not in ('success','partial_failure')) as bad_source_count
    from public.pokemon_collector_appeal_model_run_sources l
    join public.pokemon_collector_source_runs s on s.id = l.source_run_id
    where l.model_run_id = m.id
) src on true
left join lateral (
    select count(*) as entity_score_count
    from public.pokemon_collector_entity_scores x
    where x.model_run_id = m.id
) es on true
left join lateral (
    select count(*) as playability_score_count
    from public.pokemon_playability_scores x
    where x.model_run_id = m.id
) ps on true
left join lateral (
    select count(*) as card_score_count
    from public.pokemon_card_collector_appeal_scores x
    where x.model_run_id = m.id
) cs on true
left join lateral (
    select count(*) as set_score_count
    from public.pokemon_set_collector_desirability_scores x
    where x.model_run_id = m.id
) ss on true
left join public.pokemon_collector_appeal_current cur on cur.model_run_id = m.id and cur.scope = 'pokemon';

revoke all on public.pokemon_collector_source_run_health_v from public, anon, authenticated;
revoke all on public.pokemon_collector_appeal_model_run_health_v from public, anon, authenticated;
grant select on public.pokemon_collector_source_run_health_v to service_role;
grant select on public.pokemon_collector_appeal_model_run_health_v to service_role;

comment on view public.pokemon_collector_source_run_health_v is
'DB operational audit surface for Collector source-run evidence counts, matching coverage, terminal state, and declared item-count consistency.';
comment on view public.pokemon_collector_appeal_model_run_health_v is
'DB operational audit surface for Collector Appeal source lineage, actual versus declared output counts, validation state, current status, and promotion readiness.';