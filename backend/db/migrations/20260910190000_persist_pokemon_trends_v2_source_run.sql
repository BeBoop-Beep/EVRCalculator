-- Atomic, idempotent bridge for the completed Pokemon Trends V2 checkpoint.
-- Reuses the generic Collector source-run and entity-observation lifecycle.
create unique index if not exists pokemon_collector_source_runs_pokemon_trends_v2_fingerprint_uidx
    on public.pokemon_collector_source_runs(source_fingerprint)
    where source_name = 'google_trends_pokemon_v2' and source_fingerprint is not null;

create or replace function public.persist_pokemon_trends_v2_source_run(
    p_source_run jsonb,
    p_observations jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_run_id uuid;
    v_existing public.pokemon_collector_source_runs%rowtype;
    v_fingerprint text := p_source_run->>'source_fingerprint';
    v_count integer;
begin
    if p_source_run->>'source_name' <> 'google_trends_pokemon_v2'
       or p_source_run->>'source_kind' <> 'search_interest'
       or p_source_run->>'capture_version' <> 'capture_pokemon_trends_anchor_ladder_v2_r1'
       or p_source_run->>'status' not in ('success','partial_failure')
       or v_fingerprint is null or length(v_fingerprint) <> 64 then
        raise exception 'invalid Pokemon Trends V2 source-run contract';
    end if;
    if jsonb_typeof(p_observations) <> 'array' or jsonb_array_length(p_observations) <> 1025 then
        raise exception 'Pokemon Trends V2 requires exactly 1025 observations';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('google_trends_pokemon_v2:' || v_fingerprint, 0));
    select * into v_existing from public.pokemon_collector_source_runs
    where source_name = 'google_trends_pokemon_v2' and source_fingerprint = v_fingerprint;
    if found then
        if v_existing.status not in ('success','partial_failure') or v_existing.item_count <> 1025 then
            raise exception 'matching capture exists but is not a valid terminal run: %', v_existing.id;
        end if;
        return jsonb_build_object('source_run_id', v_existing.id, 'created', false, 'status', v_existing.status);
    end if;

    insert into public.pokemon_collector_source_runs(
        source_name, source_kind, run_key, capture_version, status, source_url, geo,
        anchor_term, source_fingerprint, raw_payload_json
    ) values (
        p_source_run->>'source_name', p_source_run->>'source_kind', p_source_run->>'run_key',
        p_source_run->>'capture_version', 'running', p_source_run->>'source_url',
        p_source_run->>'geo', p_source_run->>'anchor_term', v_fingerprint,
        coalesce(p_source_run->'raw_payload_json', '{}'::jsonb)
    ) returning id into v_run_id;

    insert into public.pokemon_collector_entity_observations(
        source_run_id, collector_entity_id, dimension_key, raw_entity_name,
        external_entity_key, raw_rank, raw_vote_count, raw_score, raw_value,
        normalized_observation_score, match_status, match_confidence,
        source_detail_url, raw_row_json
    )
    select v_run_id, x.collector_entity_id, x.dimension_key, x.raw_entity_name,
        x.external_entity_key, x.raw_rank, x.raw_vote_count, x.raw_score, x.raw_value,
        x.normalized_observation_score, x.match_status, x.match_confidence,
        x.source_detail_url, x.raw_row_json
    from jsonb_to_recordset(p_observations) as x(
        source_run_id uuid, collector_entity_id uuid, dimension_key text,
        raw_entity_name text, external_entity_key text, raw_rank integer,
        raw_vote_count bigint, raw_score numeric, raw_value numeric,
        normalized_observation_score numeric, match_status text,
        match_confidence numeric, source_detail_url text, raw_row_json jsonb
    );
    get diagnostics v_count = row_count;
    if v_count <> 1025 then raise exception 'observation insert count mismatch: %', v_count; end if;
    if exists (
        select 1 from public.pokemon_collector_entity_observations o
        where o.source_run_id = v_run_id and (
            o.collector_entity_id is null or o.dimension_key <> 'pokemon_search_interest_v2'
            or o.match_status <> 'matched'
            or (o.raw_row_json->>'classification' in ('failed','missing_evidence','insufficient_calibration')
                and o.normalized_observation_score is not null)
        )
    ) then raise exception 'invalid Pokemon Trends V2 observation state'; end if;

    update public.pokemon_collector_source_runs set
        status = p_source_run->>'status',
        completed_at = (p_source_run->>'completed_at')::timestamptz,
        captured_at = (p_source_run->>'captured_at')::timestamptz,
        item_count = v_count,
        diagnostics_json = coalesce(p_source_run->'diagnostics_json', '{}'::jsonb),
        updated_at = timezone('utc', now())
    where id = v_run_id;
    return jsonb_build_object('source_run_id', v_run_id, 'created', true, 'status', p_source_run->>'status');
end;
$$;

revoke all on function public.persist_pokemon_trends_v2_source_run(jsonb, jsonb)
    from public, anon, authenticated;
grant execute on function public.persist_pokemon_trends_v2_source_run(jsonb, jsonb)
    to service_role;

comment on function public.persist_pokemon_trends_v2_source_run(jsonb, jsonb) is
'Atomically persists or idempotently resolves one exact 1025-row Pokemon Trends V2 capture.';
