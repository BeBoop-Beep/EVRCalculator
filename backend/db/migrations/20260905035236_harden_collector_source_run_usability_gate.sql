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
    coalesce(e.entity_observation_count, 0::bigint)::integer as entity_observation_count,
    coalesce(p.playability_observation_count, 0::bigint)::integer as playability_observation_count,
    (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint))::integer as total_observation_count,
    coalesce(e.matched_entity_count, 0::bigint)::integer as matched_entity_count,
    coalesce(e.unresolved_entity_count, 0::bigint)::integer as unresolved_entity_count,
    coalesce(p.matched_playability_count, 0::bigint)::integer as matched_playability_count,
    coalesce(p.unresolved_playability_count, 0::bigint)::integer as unresolved_playability_count,
    case
        when s.source_kind = any (array['fan_ranking'::text, 'search_interest'::text]) then coalesce(e.entity_observation_count, 0::bigint)::integer
        when s.source_kind = 'playability'::text then coalesce(p.playability_observation_count, 0::bigint)::integer
        else (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint))::integer
    end as expected_evidence_row_count,
    case
        when s.item_count is null then null::boolean
        when s.source_kind = any (array['fan_ranking'::text, 'search_interest'::text]) then s.item_count = coalesce(e.entity_observation_count, 0::bigint)
        when s.source_kind = 'playability'::text then s.item_count = coalesce(p.playability_observation_count, 0::bigint)
        else s.item_count = (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint))
    end as item_count_consistent,
    s.status <> 'running'::text as is_terminal,
    (
        s.status = any (array['success'::text, 'partial_failure'::text])
        and (
            case
                when s.source_kind = any (array['fan_ranking'::text, 'search_interest'::text]) then
                    coalesce(e.entity_observation_count, 0::bigint) > 0
                    and (s.item_count is null or s.item_count = coalesce(e.entity_observation_count, 0::bigint))
                when s.source_kind = 'playability'::text then
                    coalesce(p.playability_observation_count, 0::bigint) > 0
                    and (s.item_count is null or s.item_count = coalesce(p.playability_observation_count, 0::bigint))
                else
                    (
                        (
                            (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint)) > 0
                            and (
                                s.item_count is null
                                or s.item_count = (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint))
                            )
                        )
                        or (
                            (coalesce(e.entity_observation_count, 0::bigint) + coalesce(p.playability_observation_count, 0::bigint)) = 0
                            and s.raw_payload_json <> '{}'::jsonb
                        )
                    )
            end
        )
    ) as usable_for_model,
    s.source_fingerprint,
    s.diagnostics_json
from public.pokemon_collector_source_runs s
left join lateral (
    select
        count(*) as entity_observation_count,
        count(*) filter (where o.match_status = 'matched'::text) as matched_entity_count,
        count(*) filter (where o.match_status = any (array['unmatched'::text, 'ambiguous'::text])) as unresolved_entity_count
    from public.pokemon_collector_entity_observations o
    where o.source_run_id = s.id
) e on true
left join lateral (
    select
        count(*) as playability_observation_count,
        count(*) filter (where o.match_status = 'matched'::text) as matched_playability_count,
        count(*) filter (where o.match_status = any (array['unmatched'::text, 'ambiguous'::text])) as unresolved_playability_count
    from public.pokemon_playability_event_observations o
    where o.source_run_id = s.id
) p on true;

create or replace view public.pokemon_collector_source_latest_valid_v
with (security_invoker = true)
as
select distinct on (s.source_name)
    s.id as source_run_id,
    s.source_name,
    s.source_kind,
    s.run_key,
    s.capture_version,
    s.status,
    s.source_url,
    s.geo,
    s.anchor_term,
    s.window_start,
    s.window_end,
    s.started_at,
    s.completed_at,
    s.captured_at,
    s.source_fingerprint,
    s.item_count,
    s.diagnostics_json
from public.pokemon_collector_source_runs s
join public.pokemon_collector_source_run_health_v h on h.source_run_id = s.id
where h.usable_for_model
order by s.source_name, coalesce(s.captured_at, s.completed_at) desc, s.completed_at desc, s.id;

create or replace function public.is_pokemon_collector_source_refresh_due(
    p_source_name text,
    p_max_age interval default interval '7 days'
)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_latest timestamptz;
begin
    if p_source_name is null or btrim(p_source_name) = '' then
        raise exception 'source_name is required';
    end if;
    if p_max_age is null or p_max_age <= interval '0 seconds' then
        raise exception 'p_max_age must be positive';
    end if;

    select max(coalesce(captured_at, completed_at)) into v_latest
    from public.pokemon_collector_source_latest_valid_v
    where source_name = p_source_name;

    return v_latest is null or v_latest < timezone('utc', now()) - p_max_age;
end;
$$;

create or replace function public.validate_pokemon_collector_appeal_model_run(
    p_model_run_id uuid,
    p_diagnostics jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_run public.pokemon_collector_appeal_model_runs%rowtype;
    v_source_count integer;
    v_bad_source_count integer;
    v_card_count integer;
    v_set_count integer;
    v_bad_scored_card_count integer;
    v_card_without_set_count integer;
    v_set_without_card_count integer;
    v_duplicate_rank_count integer;
    v_out_of_range_rank_count integer;
    v_report jsonb;
    v_passed boolean;
begin
    if p_diagnostics is null or jsonb_typeof(p_diagnostics) <> 'object' then
        raise exception 'p_diagnostics must be a JSON object';
    end if;

    select * into v_run
    from public.pokemon_collector_appeal_model_runs
    where id = p_model_run_id
    for update;

    if not found then
        raise exception 'Collector Appeal model run % not found', p_model_run_id;
    end if;

    if v_run.status <> 'building' then
        raise exception 'Collector Appeal model run % must be building to validate; status=%', p_model_run_id, v_run.status;
    end if;

    select count(*) into v_source_count
    from public.pokemon_collector_appeal_model_run_sources
    where model_run_id = p_model_run_id;

    select count(*) into v_bad_source_count
    from public.pokemon_collector_appeal_model_run_sources l
    left join public.pokemon_collector_source_run_health_v h on h.source_run_id = l.source_run_id
    where l.model_run_id = p_model_run_id
      and coalesce(h.usable_for_model, false) = false;

    select count(*) into v_card_count
    from public.pokemon_card_collector_appeal_scores
    where model_run_id = p_model_run_id;

    select count(*) into v_set_count
    from public.pokemon_set_collector_desirability_scores
    where model_run_id = p_model_run_id;

    select count(*) into v_bad_scored_card_count
    from public.pokemon_card_collector_appeal_scores
    where model_run_id = p_model_run_id
      and score_status = 'scored'
      and (
          subject_baseline_score is null
          or combined_lift is null
          or collector_card_appeal_score is null
          or collector_card_appeal_score < subject_baseline_score
      );

    select count(*) into v_card_without_set_count
    from public.pokemon_card_collector_appeal_scores c
    where c.model_run_id = p_model_run_id
      and not exists (
          select 1
          from public.pokemon_set_collector_desirability_scores s
          where s.model_run_id = c.model_run_id
            and s.set_id = c.set_id
      );

    select count(*) into v_set_without_card_count
    from public.pokemon_set_collector_desirability_scores s
    where s.model_run_id = p_model_run_id
      and not exists (
          select 1
          from public.pokemon_card_collector_appeal_scores c
          where c.model_run_id = s.model_run_id
            and c.set_id = s.set_id
      );

    select count(*) into v_duplicate_rank_count
    from (
        select collector_desirability_rank
        from public.pokemon_set_collector_desirability_scores
        where model_run_id = p_model_run_id
          and collector_desirability_rank is not null
        group by collector_desirability_rank
        having count(*) > 1
    ) d;

    select count(*) into v_out_of_range_rank_count
    from public.pokemon_set_collector_desirability_scores
    where model_run_id = p_model_run_id
      and collector_desirability_rank is not null
      and collector_desirability_rank > v_set_count;

    v_passed :=
        v_source_count = cardinality(v_run.source_run_ids)
        and v_bad_source_count = 0
        and v_card_count > 0
        and v_set_count > 0
        and v_bad_scored_card_count = 0
        and v_card_without_set_count = 0
        and v_set_without_card_count = 0
        and v_duplicate_rank_count = 0
        and v_out_of_range_rank_count = 0
        and v_run.price_policy = 'excluded'
        and v_run.hit_eligibility_policy = 'independent'
        and not private.collector_json_has_forbidden_price_key(v_run.scoring_config_json);

    v_report := jsonb_build_object(
        'passed', v_passed,
        'validated_at', timezone('utc', now()),
        'source_count', v_source_count,
        'expected_source_count', cardinality(v_run.source_run_ids),
        'bad_source_count', v_bad_source_count,
        'card_score_count', v_card_count,
        'set_score_count', v_set_count,
        'bad_scored_card_count', v_bad_scored_card_count,
        'card_without_set_count', v_card_without_set_count,
        'set_without_card_count', v_set_without_card_count,
        'duplicate_rank_count', v_duplicate_rank_count,
        'out_of_range_rank_count', v_out_of_range_rank_count,
        'price_policy', v_run.price_policy,
        'hit_eligibility_policy', v_run.hit_eligibility_policy
    );

    update public.pokemon_collector_appeal_model_runs
    set status = case when v_passed then 'validated' else 'failed' end,
        validation_passed = v_passed,
        validation_json = v_report,
        diagnostics_json = diagnostics_json || p_diagnostics,
        card_score_count = v_card_count,
        set_score_count = v_set_count,
        completed_at = timezone('utc', now()),
        updated_at = timezone('utc', now())
    where id = p_model_run_id;

    return v_report;
end;
$$;

create or replace function public.promote_pokemon_collector_appeal_model_run(p_model_run_id uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_run public.pokemon_collector_appeal_model_runs%rowtype;
    v_card_count integer;
    v_set_count integer;
begin
    select * into v_run
    from public.pokemon_collector_appeal_model_runs
    where id = p_model_run_id
    for update;
    if not found then
        raise exception 'Collector Appeal model run % not found', p_model_run_id;
    end if;
    if v_run.status <> 'validated' or not v_run.validation_passed then
        raise exception 'Collector Appeal model run % is not validated', p_model_run_id;
    end if;
    if cardinality(v_run.source_run_ids) = 0 then
        raise exception 'Collector Appeal model run % has no source-run lineage', p_model_run_id;
    end if;
    if exists (
        select 1
        from unnest(v_run.source_run_ids) as s(source_run_id)
        left join public.pokemon_collector_source_run_health_v h on h.source_run_id = s.source_run_id
        where coalesce(h.usable_for_model, false) = false
    ) then
        raise exception 'Collector Appeal model run % references unusable source evidence', p_model_run_id;
    end if;
    if v_run.price_policy <> 'excluded' or v_run.hit_eligibility_policy <> 'independent' then
        raise exception 'Collector Appeal model run % violates price/hit-eligibility separation contract', p_model_run_id;
    end if;
    select count(*) into v_card_count from public.pokemon_card_collector_appeal_scores where model_run_id = p_model_run_id;
    select count(*) into v_set_count from public.pokemon_set_collector_desirability_scores where model_run_id = p_model_run_id;
    if v_card_count = 0 or v_set_count = 0 then
        raise exception 'Collector Appeal model run % has incomplete outputs: cards %, sets %', p_model_run_id, v_card_count, v_set_count;
    end if;
    if v_run.card_score_count is not null and v_run.card_score_count <> v_card_count then
        raise exception 'Collector Appeal card-score count mismatch: expected %, found %', v_run.card_score_count, v_card_count;
    end if;
    if v_run.set_score_count is not null and v_run.set_score_count <> v_set_count then
        raise exception 'Collector Appeal set-score count mismatch: expected %, found %', v_run.set_score_count, v_set_count;
    end if;
    update public.pokemon_collector_appeal_model_runs
    set status = 'published', card_score_count = v_card_count, set_score_count = v_set_count,
        completed_at = coalesce(completed_at, timezone('utc', now())),
        published_at = timezone('utc', now()), updated_at = timezone('utc', now())
    where id = p_model_run_id;
    insert into public.pokemon_set_collector_appeal_history (
        model_run_id, set_id, snapshot_date, model_version, aggregation_version,
        collector_desirability_score, collector_desirability_rank, score_coverage_ratio,
        scored_card_count, published_at
    )
    select s.model_run_id, s.set_id, v_run.as_of_date, v_run.model_version, s.aggregation_version,
           s.collector_desirability_score, s.collector_desirability_rank, s.score_coverage_ratio,
           s.scored_card_count, timezone('utc', now())
    from public.pokemon_set_collector_desirability_scores s
    where s.model_run_id = p_model_run_id;
    insert into public.pokemon_collector_appeal_current(scope, model_run_id, model_version, as_of_date, promoted_at)
    values ('pokemon', p_model_run_id, v_run.model_version, v_run.as_of_date, timezone('utc', now()))
    on conflict (scope) do update
    set model_run_id = excluded.model_run_id, model_version = excluded.model_version,
        as_of_date = excluded.as_of_date, promoted_at = excluded.promoted_at;
    return p_model_run_id;
end;
$$;

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
    coalesce(src.linked_source_count, 0::bigint)::integer as linked_source_count,
    coalesce(src.bad_source_count, 0::bigint)::integer as bad_source_count,
    coalesce(es.entity_score_count, 0::bigint)::integer as entity_score_count,
    coalesce(ps.playability_score_count, 0::bigint)::integer as playability_score_count,
    coalesce(cs.card_score_count, 0::bigint)::integer as actual_card_score_count,
    coalesce(ss.set_score_count, 0::bigint)::integer as actual_set_score_count,
    m.card_score_count as declared_card_score_count,
    m.set_score_count as declared_set_score_count,
    cardinality(m.source_run_ids) = coalesce(src.linked_source_count, 0::bigint) as source_lineage_consistent,
    m.card_score_count is null or m.card_score_count = coalesce(cs.card_score_count, 0::bigint) as card_count_consistent,
    m.set_score_count is null or m.set_score_count = coalesce(ss.set_score_count, 0::bigint) as set_count_consistent,
    cur.model_run_id is not null as is_current,
    m.status = 'validated'::text
        and m.validation_passed
        and coalesce(src.bad_source_count, 0::bigint) = 0
        and cardinality(m.source_run_ids) = coalesce(src.linked_source_count, 0::bigint)
        and coalesce(cs.card_score_count, 0::bigint) > 0
        and coalesce(ss.set_score_count, 0::bigint) > 0
        and (m.card_score_count is null or m.card_score_count = coalesce(cs.card_score_count, 0::bigint))
        and (m.set_score_count is null or m.set_score_count = coalesce(ss.set_score_count, 0::bigint)) as ready_to_promote,
    m.validation_json,
    m.diagnostics_json,
    m.started_at,
    m.completed_at,
    m.published_at
from public.pokemon_collector_appeal_model_runs m
left join lateral (
    select
        count(*) as linked_source_count,
        count(*) filter (where coalesce(h.usable_for_model, false) = false) as bad_source_count
    from public.pokemon_collector_appeal_model_run_sources l
    left join public.pokemon_collector_source_run_health_v h on h.source_run_id = l.source_run_id
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
left join public.pokemon_collector_appeal_current cur
    on cur.model_run_id = m.id and cur.scope = 'pokemon'::text;

revoke all on public.pokemon_collector_source_run_health_v from public, anon, authenticated, service_role;
revoke all on public.pokemon_collector_source_latest_valid_v from public, anon, authenticated, service_role;
revoke all on public.pokemon_collector_appeal_model_run_health_v from public, anon, authenticated, service_role;
grant select on public.pokemon_collector_source_run_health_v to service_role;
grant select on public.pokemon_collector_source_latest_valid_v to service_role;
grant select on public.pokemon_collector_appeal_model_run_health_v to service_role;

revoke all on function public.is_pokemon_collector_source_refresh_due(text, interval) from public, anon, authenticated;
revoke all on function public.validate_pokemon_collector_appeal_model_run(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.promote_pokemon_collector_appeal_model_run(uuid) from public, anon, authenticated;
grant execute on function public.is_pokemon_collector_source_refresh_due(text, interval) to service_role;
grant execute on function public.validate_pokemon_collector_appeal_model_run(uuid, jsonb) to service_role;
grant execute on function public.promote_pokemon_collector_appeal_model_run(uuid) to service_role;

comment on view public.pokemon_collector_source_run_health_v is
'Collector source-run integrity surface. usable_for_model requires terminal successful/partial status plus usable evidence and declared-count reconciliation when normalized evidence is present; raw-only reference captures require a non-empty raw payload.';
comment on function public.is_pokemon_collector_source_refresh_due(text, interval) is
'Returns true when no recent usable collector source run exists. Failed, empty, or count-inconsistent source runs do not suppress refresh.';