-- Market Explorer V2 coherent-generation build, validation, and guarded promotion.
-- Requires all source authorities to support one comparison date.

begin;

create or replace function public.preflight_pokemon_market_explorer_surface_v2(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '10s'
as $function$
declare
  v_base_rows integer;
  v_bad_base integer;
  v_bad_card_coverage integer;
  v_raw_set_count integer;
  v_frozen_roots integer;
  v_frozen_cards integer;
  v_frozen_value numeric;
  v_raw_cards integer;
  v_raw_value numeric;
begin
  if p_base_generation_id is null or p_market_date is null
     or nullif(p_raw_methodology_version,'') is null then
    raise exception 'SURFACE_PREFLIGHT_ARGUMENTS_REQUIRED';
  end if;

  if not exists (
    select 1 from public.pokemon_market_date_quality q
    where q.tcg='pokemon' and q.market_date=p_market_date
      and q.status in ('READY','LEGACY_VERIFIED')
  ) then
    raise exception 'EXPLORER_COMPARISON_DATE_NOT_ACCEPTED';
  end if;

  if not exists (
    select 1 from public.pokemon_market_explorer_prepared_serving_v1 s
    where s.singleton and s.generation_id=p_base_generation_id
  ) then
    raise exception 'BASE_PREPARED_GENERATION_NOT_SERVING';
  end if;

  select count(*)::integer,
         count(*) filter(where d.comparison_as_of is distinct from p_market_date)::integer
  into v_base_rows,v_bad_base
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.generation_id=p_base_generation_id;

  if v_base_rows=0 or v_bad_base>0 then
    raise exception 'BASE_PREPARED_GENERATION_NOT_COHERENT: rows %, mismatched %',
      v_base_rows,v_bad_base;
  end if;

  select count(*)::integer
  into v_bad_card_coverage
  from public.pokemon_market_explorer_card_daily_coverage_v2_shadow c
  where c.computed_through is null or c.computed_through<p_market_date;

  if v_bad_card_coverage>0
     or (select max(d.market_date) from public.pokemon_market_explorer_card_daily_states_v2_shadow d)<p_market_date
  then
    raise exception 'CARD_DAILY_AUTHORITY_NOT_CURRENT: stale coverage %',v_bad_card_coverage;
  end if;

  if (select max(d.market_date) from public.pokemon_market_explorer_sealed_daily_v1 d)<p_market_date
     or (select max(m.latest_market_date) from public.pokemon_market_explorer_sealed_current_metadata_v1 m)<p_market_date
  then
    raise exception 'SEALED_AUTHORITY_NOT_CURRENT';
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    where c.singleton and c.certified_through>=p_market_date
  ) then
    raise exception 'RARITY_AUTHORITY_NOT_CERTIFIED';
  end if;

  select h.set_count,h.card_count,h.basket_value
  into v_raw_set_count,v_raw_cards,v_raw_value
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon' and h.index_key='raw'
    and h.market_date=p_market_date
    and h.methodology_version=p_raw_methodology_version
  order by h.updated_at desc
  limit 1;

  if not found then
    raise exception 'RAW_INDEX_ROW_NOT_FOUND';
  end if;

  with raw as materialized (
    select h.constituents_json
    from public.pokemon_market_index_daily_history h
    where h.tcg='pokemon' and h.index_key='raw'
      and h.market_date=p_market_date
      and h.methodology_version=p_raw_methodology_version
    order by h.updated_at desc limit 1
  ),
  roots as materialized (
    select
      (x->>'setId')::uuid root_set_id,
      (x->>'setValue')::numeric expected_value,
      (x->>'includedCardCount')::integer expected_count
    from raw cross join lateral jsonb_array_elements(raw.constituents_json) x
  ),
  valid as materialized (
    select r.root_set_id,p.constituent_count,p.constituent_value
    from roots r
    join public.pokemon_market_set_value_constituent_publications_v1 p
      on p.root_set_id=r.root_set_id
     and p.market_date=p_market_date
     and p.methodology_version=p_raw_methodology_version
     and p.status='READY'
     and p.expected_card_count=r.expected_count
     and round(p.expected_set_value,2)=round(r.expected_value,2)
     and p.constituent_count=r.expected_count
     and round(p.constituent_value,2)=round(r.expected_value,2)
  )
  select count(*)::integer,coalesce(sum(constituent_count),0)::integer,
         coalesce(sum(constituent_value),0)
  into v_frozen_roots,v_frozen_cards,v_frozen_value
  from valid;

  if v_frozen_roots<>v_raw_set_count
     or v_frozen_cards<>v_raw_cards
     or round(v_frozen_value,2)<>round(v_raw_value,2)
  then
    raise exception
      'RAW_FROZEN_ROSTERS_INCOMPLETE: roots %/% cards %/% value %/%',
      v_frozen_roots,v_raw_set_count,v_frozen_cards,v_raw_cards,
      round(v_frozen_value,2),round(v_raw_value,2);
  end if;

  return jsonb_build_object(
    'status','READY',
    'comparisonAsOf',p_market_date,
    'baseGenerationId',p_base_generation_id,
    'baseDirectoryRows',v_base_rows,
    'cardCoverageStaleRows',v_bad_card_coverage,
    'rawFrozenRoots',v_frozen_roots,
    'rawCardCount',v_raw_cards,
    'rawBasketValue',v_raw_value
  );
end;
$function$;

revoke all on function public.preflight_pokemon_market_explorer_surface_v2(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.preflight_pokemon_market_explorer_surface_v2(uuid,date,text)
to service_role;

create or replace function public.build_pokemon_market_explorer_surface_candidate_v2(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '300s'
set lock_timeout = '2s'
as $function$
declare
  v_generation uuid:=gen_random_uuid();
  v_preflight jsonb;
  v_seed jsonb;
  v_raw jsonb;
  v_rarity jsonb;
  v_sealed jsonb;
  v_quicks jsonb;
  v_metrics jsonb;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  v_preflight:=public.preflight_pokemon_market_explorer_surface_v2(
    p_base_generation_id,p_market_date,p_raw_methodology_version
  );

  insert into public.pokemon_market_explorer_surface_generations_v2(
    generation_id,base_prepared_generation_id,market_date,comparison_as_of,
    raw_methodology_version,state,diagnostics
  ) values (
    v_generation,p_base_generation_id,p_market_date,p_market_date,
    p_raw_methodology_version,'BUILDING',
    jsonb_build_object('preflight',v_preflight)
  );

  v_seed:=public.seed_pokemon_market_explorer_surface_from_prepared_v1(
    v_generation,p_base_generation_id
  );

  -- Normalized sealed and rarity authorities are preflighted as current.
  perform public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();
  perform public.refresh_pokemon_market_explorer_sealed_type_registry_v1();
  perform public.refresh_pokemon_market_explorer_rarity_registry_v1(p_market_date);

  v_raw:=public.stage_pokemon_market_explorer_raw_surface_v2(
    v_generation,p_market_date,p_raw_methodology_version
  );
  v_rarity:=public.stage_pokemon_market_explorer_rarity_candidates_v2(
    v_generation,p_market_date
  );
  v_sealed:=public.stage_pokemon_market_explorer_sealed_lattice_v2(
    v_generation,p_market_date
  );
  v_quicks:=public.stage_pokemon_market_explorer_sealed_quicks_v1(
    v_generation,p_market_date
  );
  v_metrics:=public.finalize_pokemon_market_explorer_surface_metrics_v2(
    v_generation,p_market_date
  );

  update public.pokemon_market_explorer_surface_directory_v2 d
  set comparison_as_of=p_market_date,
      metadata=d.metadata||jsonb_build_object('comparisonAsOf',p_market_date)
  where d.generation_id=v_generation;

  update public.pokemon_market_explorer_surface_generations_v2
  set state='BUILT',
      built_at=clock_timestamp(),
      diagnostics=diagnostics||jsonb_build_object(
        'seed',v_seed,'raw',v_raw,'rarity',v_rarity,
        'sealed',v_sealed,'sealedQuicks',v_quicks,'metrics',v_metrics
      )
  where generation_id=v_generation;

  return jsonb_build_object(
    'generationId',v_generation,'state','BUILT',
    'comparisonAsOf',p_market_date,
    'seed',v_seed,'raw',v_raw,'rarity',v_rarity,
    'sealed',v_sealed,'sealedQuicks',v_quicks,'metrics',v_metrics
  );
exception when others then
  raise;
end;
$function$;

revoke all on function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
from public,anon,authenticated;
grant execute on function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
to service_role;

create or replace function public.validate_pokemon_market_explorer_surface_candidate_v2(
  p_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '60s'
set lock_timeout = '2s'
as $function$
declare
  v_state text;
  v_market_date date;
  v_comparison date;
  v_base uuid;
  v_raw_method text;
  v_issues jsonb:='[]'::jsonb;
  v_n integer;
  v_preflight jsonb;
begin
  select state,market_date,comparison_as_of,base_prepared_generation_id,raw_methodology_version
  into v_state,v_market_date,v_comparison,v_base,v_raw_method
  from public.pokemon_market_explorer_surface_generations_v2
  where generation_id=p_generation_id
  for update;

  if not found or v_state not in ('BUILT','VALIDATED','REJECTED') then
    raise exception 'SURFACE_GENERATION_NOT_BUILT';
  end if;

  if v_comparison is distinct from v_market_date then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','GENERATION_COMPARISON_WATERMARK_MISMATCH')
    );
  end if;

  begin
    v_preflight:=public.preflight_pokemon_market_explorer_surface_v2(
      v_base,v_market_date,v_raw_method
    );
  exception when others then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SOURCE_PREFLIGHT_FAILED','error',left(sqlerrm,500))
    );
  end;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id
    and d.comparison_as_of is distinct from v_market_date;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','DIRECTORY_COMPARISON_WATERMARK_MISMATCH','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id
    and d.availability='available'
    and d.history_available
    and (
      d.history_end_date is distinct from v_market_date
      or not exists (
        select 1
        from public.pokemon_market_explorer_surface_history_v2 h
        where h.generation_id=d.generation_id
          and h.market_key=d.market_key
          and h.market_date=v_market_date
      )
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','HISTORY_NOT_CURRENT','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituent_totals_v2 t
  left join lateral (
    select count(*)::integer n,max(rank)::integer mx,
           count(distinct instrument_id)::integer instruments
    from public.pokemon_market_explorer_surface_constituents_v2 c
    where c.generation_id=t.generation_id and c.market_key=t.market_key
  ) x on true
  where t.generation_id=p_generation_id
    and (
      (t.availability='available'
       and (x.n<>t.total_count or x.mx<>t.total_count or x.instruments<>t.total_count))
      or (t.availability='empty' and x.n<>0)
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','CONSTITUENT_PAGING_INVARIANT','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_directory_v2 d
  where d.generation_id=p_generation_id
    and d.composition_kind in ('composition','index_and_composition')
    and not exists (
      select 1
      from public.pokemon_market_explorer_surface_constituent_totals_v2 t
      where t.generation_id=d.generation_id and t.market_key=d.market_key
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','MISSING_CONSTITUENT_TOTAL','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_raw_composition_runs_v1 r
  where r.generation_id=p_generation_id and r.status<>'READY';
  if v_n>0 or not exists (
    select 1 from public.pokemon_market_explorer_raw_composition_runs_v1
    where generation_id=p_generation_id and status='READY'
  ) then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','RAW_COMPOSITION_NOT_RECONCILED')
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituents_v2 c
  join public.pokemon_market_explorer_card_current_metadata m
    on c.asset='cards' and c.instrument_id=m.card_variant_id::text
  left join public.card_variants cv on cv.id=m.card_variant_id
  left join public.pokemon_canonical_cards cc on cc.id=m.canonical_card_id
  where c.generation_id=p_generation_id
    and coalesce(
      cv.image_small_url,cc.image_small_url,
      cv.image_large_url,cc.image_large_url,m.image_url
    ) is not null
    and nullif(c.item->>'imageUrl','') is null;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','CARD_IMAGE_DROPPED','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituents_v2 c
  where c.generation_id=p_generation_id
    and (
      c.market_key='sealedMarket'
      or c.market_key like 'sealed-quick:%'
    )
    and coalesce((c.item->>'isBulkContainer')::boolean,false);
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_CONSUMER_MARKET_CONTAINS_BULK','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from (
    values
      ('sealed-quick:obtainable'),
      ('sealed-quick:intermediate'),
      ('sealed-quick:premium'),
      ('sealed-quick:new-releases'),
      ('sealed-quick:established'),
      ('sealed-quick:global-top10')
  ) q(market_key)
  where not exists (
    select 1
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id
      and d.market_key=q.market_key
      and d.asset='sealed'
      and d.scope_kind='quick'
      and d.comparison_as_of=v_market_date
  );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_QUICK_MARKETS_MISSING','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_constituents_v2 c
  where c.generation_id=p_generation_id
    and c.market_key='sealed-quick:global-top10'
    and c.price_as_of=v_market_date;
  if v_n<>10 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_GLOBAL_TOP10_COUNT','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from (
    values
      ('raw'),
      ('sealedMarket'),
      ('sealed-type:elite_trainer_box'),
      ('sealed-type:booster_bundle'),
      ('sealed-type:case'),
      ('sealed-type:display'),
      ('rarity:rareHoloGx')
  ) req(market_key)
  where not exists (
    select 1
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id
      and d.market_key=req.market_key
      and d.comparison_as_of=v_market_date
  );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','REQUIRED_MARKETS_MISSING','count',v_n)
    );
  end if;

  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id
      and d.asset='sealed' and d.scope_kind='set'
      and d.comparison_as_of=v_market_date
  ) then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','SEALED_SET_MISSING'));
  end if;
  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id
      and d.asset='sealed' and d.scope_kind='era'
      and d.comparison_as_of=v_market_date
  ) then
    v_issues:=v_issues||jsonb_build_array(jsonb_build_object('code','SEALED_ERA_MISSING'));
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_aliases_v2 a
  where a.generation_id=p_generation_id
    and not exists (
      select 1
      from public.pokemon_market_explorer_surface_directory_v2 d
      where d.generation_id=a.generation_id and d.market_key=a.market_key
    );
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','BROKEN_ALIAS_TARGET','count',v_n)
    );
  end if;

  select count(*)::integer into v_n
  from public.pokemon_market_explorer_surface_history_v2 h
  where h.generation_id=p_generation_id and h.market_date>v_market_date;
  if v_n>0 then
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','FUTURE_LOOKAHEAD','count',v_n)
    );
  end if;

  update public.pokemon_market_explorer_surface_generations_v2
  set state=case when jsonb_array_length(v_issues)=0 then 'VALIDATED' else 'REJECTED' end,
      validated_at=clock_timestamp(),
      diagnostics=diagnostics||jsonb_build_object(
        'validationIssues',v_issues,
        'validationPreflight',v_preflight
      )
  where generation_id=p_generation_id;

  return jsonb_build_object(
    'generationId',p_generation_id,
    'state',case when jsonb_array_length(v_issues)=0 then 'VALIDATED' else 'REJECTED' end,
    'comparisonAsOf',v_market_date,
    'issues',v_issues,
    'directoryRows',(
      select count(*) from public.pokemon_market_explorer_surface_directory_v2
      where generation_id=p_generation_id
    ),
    'historyRows',(
      select count(*) from public.pokemon_market_explorer_surface_history_v2
      where generation_id=p_generation_id
    ),
    'constituentRows',(
      select count(*) from public.pokemon_market_explorer_surface_constituents_v2
      where generation_id=p_generation_id
    )
  );
end;
$function$;

revoke all on function public.validate_pokemon_market_explorer_surface_candidate_v2(uuid)
from public,anon,authenticated;
grant execute on function public.validate_pokemon_market_explorer_surface_candidate_v2(uuid)
to service_role;

create or replace function public.promote_pokemon_market_explorer_surface_v2(
  p_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '75s'
set lock_timeout = '2s'
as $function$
declare
  v_old uuid;
  v_validation jsonb;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  v_validation:=public.validate_pokemon_market_explorer_surface_candidate_v2(
    p_generation_id
  );

  if v_validation->>'state'<>'VALIDATED' then
    raise exception 'ONLY_CURRENT_VALIDATED_SURFACE_GENERATIONS_MAY_BE_PROMOTED: %',
      v_validation;
  end if;

  select generation_id into v_old
  from public.pokemon_market_explorer_surface_serving_v2
  where singleton=1
  for update;

  insert into public.pokemon_market_explorer_surface_serving_v2(
    singleton,generation_id,previous_generation_id,promoted_at
  ) values (1,p_generation_id,v_old,clock_timestamp())
  on conflict(singleton) do update
  set previous_generation_id=public.pokemon_market_explorer_surface_serving_v2.generation_id,
      generation_id=excluded.generation_id,
      promoted_at=excluded.promoted_at;

  return jsonb_build_object(
    'generationId',p_generation_id,
    'previousGenerationId',v_old,
    'comparisonAsOf',v_validation->>'comparisonAsOf',
    'validation',v_validation
  );
end;
$function$;

revoke all on function public.promote_pokemon_market_explorer_surface_v2(uuid)
from public,anon,authenticated;
grant execute on function public.promote_pokemon_market_explorer_surface_v2(uuid)
to service_role;

create or replace function public.publish_pokemon_market_explorer_surface_current_v2()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '300s'
set lock_timeout = '2s'
as $function$
declare
  v_base uuid;
  v_min_date date;
  v_max_date date;
  v_target date;
  v_raw_method text;
  v_existing uuid;
  v_build jsonb;
  v_generation uuid;
  v_promotion jsonb;
begin
  select s.generation_id into v_base
  from public.pokemon_market_explorer_prepared_serving_v1 s
  where s.singleton
  limit 1;

  if v_base is null then
    raise exception 'CURRENT_V2_BASE_PREPARED_GENERATION_MISSING';
  end if;

  select min(d.comparison_as_of),max(d.comparison_as_of)
  into v_min_date,v_max_date
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.generation_id=v_base;

  if v_min_date is null or v_min_date is distinct from v_max_date then
    raise exception 'CURRENT_V2_BASE_COMPARISON_DATE_NOT_COHERENT: % / %',
      v_min_date,v_max_date;
  end if;
  v_target:=v_max_date;

  select h.methodology_version into v_raw_method
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon' and h.index_key='raw' and h.market_date=v_target
  order by h.updated_at desc
  limit 1;

  if v_raw_method is null then
    raise exception 'CURRENT_V2_RAW_METHODOLOGY_MISSING';
  end if;

  select s.generation_id into v_existing
  from public.pokemon_market_explorer_surface_serving_v2 s
  join public.pokemon_market_explorer_surface_generations_v2 g
    on g.generation_id=s.generation_id
  where s.singleton=1
    and g.state='VALIDATED'
    and g.comparison_as_of=v_target
  limit 1;

  if v_existing is not null then
    return jsonb_build_object(
      'status','already_current',
      'generationId',v_existing,
      'comparisonAsOf',v_target
    );
  end if;

  v_build:=public.build_pokemon_market_explorer_surface_candidate_v2(
    v_base,v_target,v_raw_method
  );
  v_generation:=(v_build->>'generationId')::uuid;

  v_promotion:=public.promote_pokemon_market_explorer_surface_v2(v_generation);

  return jsonb_build_object(
    'status','promoted',
    'generationId',v_generation,
    'comparisonAsOf',v_target,
    'build',v_build,
    'promotion',v_promotion
  );
end;
$function$;

revoke all on function public.publish_pokemon_market_explorer_surface_current_v2()
from public,anon,authenticated;
grant execute on function public.publish_pokemon_market_explorer_surface_current_v2()
to service_role;

commit;
