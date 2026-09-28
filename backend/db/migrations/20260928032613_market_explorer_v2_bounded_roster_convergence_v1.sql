begin;

CREATE OR REPLACE FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '300s'
 SET lock_timeout TO '2s'
AS $function$
declare
  v_base uuid;
  v_v1_status text;
  v_target date;
  v_v1_directory_rows integer;
  v_prepared_min date;
  v_prepared_max date;
  v_prepared_rows integer;
  v_latest_raw date;
  v_latest_card date;
  v_latest_sealed date;
  v_latest_sealed_meta date;
  v_raw public.pokemon_market_index_daily_history%rowtype;
  v_expected_roots integer;
  v_ready_roots integer;
  v_serving uuid;
  v_previous uuid;
  v_existing uuid;
  v_generation uuid;
  v_build jsonb;
  v_validation jsonb;
  v_assertion jsonb;
  v_promotion jsonb;
  v_directory_rows integer;
  v_freeze jsonb;
begin
  if not pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  ) then
    return jsonb_build_object(
      'status','blocked',
      'errorClass','publication_already_running'
    );
  end if;

  select s.generation_id,g.status,g.comparison_as_of,g.directory_rows
  into v_base,v_v1_status,v_target,v_v1_directory_rows
  from public.pokemon_market_explorer_prepared_serving_v1 s
  join public.pokemon_market_explorer_prepared_generations_v1 g
    on g.generation_id=s.generation_id
  where s.singleton
  limit 1;

  if v_base is null or v_target is null or v_v1_status is distinct from 'serving' then
    raise exception 'CURRENT_V2_BASE_PREPARED_GENERATION_NOT_SERVING';
  end if;

  select min(d.comparison_as_of),max(d.comparison_as_of),count(*)::integer
  into v_prepared_min,v_prepared_max,v_prepared_rows
  from public.pokemon_market_explorer_prepared_directory_generations_v1 d
  where d.generation_id=v_base;

  if v_prepared_min is null
     or v_prepared_min is distinct from v_prepared_max
     or v_prepared_max is distinct from v_target
     or v_prepared_rows is distinct from v_v1_directory_rows then
    raise exception
      'CURRENT_V2_BASE_PREPARED_GENERATION_INCOHERENT: min % max % target % rows % expected %',
      v_prepared_min,v_prepared_max,v_target,v_prepared_rows,v_v1_directory_rows;
  end if;

  select max(h.market_date) into v_latest_raw
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon' and h.index_key='raw';

  if v_latest_raw is distinct from v_target then
    raise exception 'CURRENT_V2_RAW_LATEST_MISMATCH: latest % target %',
      v_latest_raw,v_target;
  end if;

  select h.* into v_raw
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon'
    and h.index_key='raw'
    and h.market_date=v_target
  order by h.updated_at desc
  limit 1;

  if not found or nullif(v_raw.methodology_version,'') is null then
    raise exception 'CURRENT_V2_RAW_METHODOLOGY_MISSING';
  end if;

  select max(d.market_date) into v_latest_card
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d;
  if v_latest_card is distinct from v_target or not exists (
    select 1
    from public.pokemon_market_explorer_card_daily_states_v2_shadow d
    where d.market_date=v_target and d.market_price>0
  ) then
    raise exception 'CURRENT_V2_CARD_DAILY_NOT_CURRENT: latest % target %',
      v_latest_card,v_target;
  end if;

  select max(d.market_date) into v_latest_sealed
  from public.pokemon_market_explorer_sealed_daily_v1 d;
  if v_latest_sealed is distinct from v_target or not exists (
    select 1
    from public.pokemon_market_explorer_sealed_daily_v1 d
    where d.market_date=v_target and d.market_price>0
  ) then
    raise exception 'CURRENT_V2_SEALED_DAILY_NOT_CURRENT: latest % target %',
      v_latest_sealed,v_target;
  end if;

  select max(m.latest_market_date) into v_latest_sealed_meta
  from public.pokemon_market_explorer_sealed_current_metadata_v1 m;
  if v_latest_sealed_meta is distinct from v_target or not exists (
    select 1
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where m.latest_market_date=v_target and m.latest_market_price>0
  ) then
    raise exception 'CURRENT_V2_SEALED_METADATA_NOT_CURRENT: latest % target %',
      v_latest_sealed_meta,v_target;
  end if;

  -- Rarity coverage is a daily derived dependency of the V2 surface. The
  -- original cutover required an operator to refresh/certify it separately,
  -- which left the unattended V1 -> V2 handoff permanently one day behind.
  -- Advance only the current target date here, and only when the durable
  -- certification watermark is stale. The certification function still
  -- fails closed if any accepted historical date is missing.
  if not exists (
    select 1
    from public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    where c.singleton and c.certified_through>=v_target
  ) then
    perform public.refresh_pokemon_market_explorer_rarity_daily_coverage_v1(
      v_target,v_target
    );
    perform public.certify_pokemon_market_explorer_rarity_coverage_v1(v_target);
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    where c.singleton and c.certified_through>=v_target
  ) then
    raise exception 'CURRENT_V2_RARITY_NOT_CERTIFIED';
  end if;

  with roots as (
    select
      (x->>'setId')::uuid root_set_id,
      (x->>'setValue')::numeric expected_value,
      (x->>'includedCardCount')::integer expected_count
    from jsonb_array_elements(v_raw.constituents_json) x
  )
  select
    count(*)::integer,
    count(p.root_set_id) filter (
      where p.status='READY'
        and p.constituent_count=r.expected_count
        and round(p.constituent_value,2)=round(r.expected_value,2)
    )::integer
  into v_expected_roots,v_ready_roots
  from roots r
  left join public.pokemon_market_set_value_constituent_publications_v1 p
    on p.root_set_id=r.root_set_id
   and p.market_date=v_target
   and p.methodology_version=v_raw.methodology_version;

  if v_expected_roots<>v_raw.set_count then
    raise exception 'CURRENT_V2_RAW_ROOT_COUNT_MISMATCH: expected % raw %',
      coalesce(v_expected_roots,0),coalesce(v_raw.set_count,0);
  end if;

  -- Frozen raw Set Value rosters are a derived publication dependency.
  -- Converge them in bounded 20-root chunks so the once-per-minute worker
  -- can make durable progress without one long all-roots transaction.
  if v_ready_roots<>v_expected_roots then
    v_freeze:=public.freeze_pokemon_market_legacy_set_value_rosters_v1(
      v_target,20
    );

    with roots as (
      select
        (x->>'setId')::uuid root_set_id,
        (x->>'setValue')::numeric expected_value,
        (x->>'includedCardCount')::integer expected_count
      from jsonb_array_elements(v_raw.constituents_json) x
    )
    select count(p.root_set_id) filter (
      where p.status='READY'
        and p.constituent_count=r.expected_count
        and round(p.constituent_value,2)=round(r.expected_value,2)
    )::integer
    into v_ready_roots
    from roots r
    left join public.pokemon_market_set_value_constituent_publications_v1 p
      on p.root_set_id=r.root_set_id
     and p.market_date=v_target
     and p.methodology_version=v_raw.methodology_version;

    if v_ready_roots<>v_expected_roots then
      return jsonb_build_object(
        'status','blocked',
        'errorClass','raw_frozen_rosters_converging',
        'marketDate',v_target,
        'comparisonAsOf',v_target,
        'readyRoots',coalesce(v_ready_roots,0),
        'expectedRoots',coalesce(v_expected_roots,0),
        'freezeReceipt',v_freeze
      );
    end if;
  end if;

  select s.generation_id,s.previous_generation_id
  into v_serving,v_previous
  from public.pokemon_market_explorer_surface_serving_v2 s
  join public.pokemon_market_explorer_surface_generations_v2 g
    on g.generation_id=s.generation_id
  where s.singleton=1
    and g.state='VALIDATED'
    and g.base_prepared_generation_id=v_base
    and g.comparison_as_of=v_target
    and g.market_date=v_target
    and g.raw_methodology_version=v_raw.methodology_version
  limit 1;

  if v_serving is not null then
    v_assertion:=public.assert_pokemon_market_explorer_surface_coherent_v2(v_serving);
    select count(*)::integer into v_directory_rows
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=v_serving;
    return jsonb_build_object(
      'status','already_current',
      'generationId',v_serving,
      'previousGenerationId',v_previous,
      'marketDate',v_target,
      'comparisonAsOf',v_target,
      'directoryRows',v_directory_rows,
      'diagnostics',jsonb_build_object(
        'generationState','VALIDATED',
        'rawFrozenRoots',v_ready_roots,
        'assertion',v_assertion
      )
    );
  end if;

  select g.generation_id into v_existing
  from public.pokemon_market_explorer_surface_generations_v2 g
  where g.state='VALIDATED'
    and g.base_prepared_generation_id=v_base
    and g.market_date=v_target
    and g.comparison_as_of=v_target
    and g.raw_methodology_version=v_raw.methodology_version
  order by g.validated_at desc nulls last,g.created_at desc
  limit 1;

  if v_existing is not null then
    v_assertion:=public.assert_pokemon_market_explorer_surface_coherent_v2(v_existing);
    v_promotion:=public.promote_pokemon_market_explorer_surface_v2(v_existing);
    select count(*)::integer into v_directory_rows
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=v_existing;
    return jsonb_build_object(
      'status','promoted_existing_validated',
      'generationId',v_existing,
      'previousGenerationId',v_promotion->>'previousGenerationId',
      'marketDate',v_target,
      'comparisonAsOf',v_target,
      'directoryRows',v_directory_rows,
      'diagnostics',jsonb_build_object(
        'generationState','VALIDATED',
        'rawFrozenRoots',v_ready_roots,
        'assertion',v_assertion
      )
    );
  end if;

  v_build:=public.build_pokemon_market_explorer_surface_candidate_v2(
    v_base,v_target,v_raw.methodology_version
  );
  v_generation:=(v_build->>'generationId')::uuid;
  v_validation:=public.validate_pokemon_market_explorer_surface_candidate_v2(v_generation);

  if coalesce(v_validation->>'state','')<>'VALIDATED' then
    return jsonb_build_object(
      'status','blocked',
      'errorClass','candidate_validation_failed',
      'generationId',v_generation,
      'marketDate',v_target,
      'comparisonAsOf',v_target,
      'diagnostics',jsonb_build_object(
        'rawFrozenRoots',v_ready_roots,
        'validation',v_validation
      )
    );
  end if;

  v_assertion:=public.assert_pokemon_market_explorer_surface_coherent_v2(v_generation);
  v_promotion:=public.promote_pokemon_market_explorer_surface_v2(v_generation);

  select count(*)::integer into v_directory_rows
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=v_generation;

  return jsonb_build_object(
    'status','promoted',
    'generationId',v_generation,
    'previousGenerationId',v_promotion->>'previousGenerationId',
    'marketDate',v_target,
    'comparisonAsOf',v_target,
    'directoryRows',v_directory_rows,
    'diagnostics',jsonb_build_object(
      'generationState','VALIDATED',
      'rawFrozenRoots',v_ready_roots,
      'build',v_build,
      'validation',v_validation,
      'assertion',v_assertion
    )
  );
end;
$function$
;

revoke all on function public.publish_pokemon_market_explorer_surface_current_v2()
from public,anon,authenticated;
grant execute on function public.publish_pokemon_market_explorer_surface_current_v2()
to service_role;

commit;
