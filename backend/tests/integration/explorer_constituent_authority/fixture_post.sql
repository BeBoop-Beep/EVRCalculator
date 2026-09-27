-- v2 prod reader is loaded from v2_prod.sql separately.

-- Stub for the 28KB production refresh (contract-faithful: builds a complete candidate
-- generation from the same sources, then promotes via the REAL switch function).
create or replace function public.refresh_pokemon_market_explorer_prepared_directory_v1() returns jsonb
language plpgsql set search_path='' as $$
declare g uuid := gen_random_uuid(); ts timestamptz := clock_timestamp();
  v_sets date; v_asof date; nrows integer; nh integer;
begin
  select market_date into v_sets from public.pokemon_explore_set_value_snapshot_latest where tcg='pokemon' and scope='market';
  v_asof := v_sets;
  insert into public.pokemon_market_explorer_prepared_directory_generations_v1
    (market_key,market_type,label,asset,set_id,era_id,parent_era_id,prepared_series_key,comparison_as_of,source_as_of,
     current_value,history_available,history_point_count,source_kind,source_status,metadata,generation_id,generated_at)
  select 'set:'||s.id, 'set', s.name, 'cards', s.id, null, s.era_id, 'set-cards-market-index:'||s.id, v_asof, v_asof,
     100, true, 1, 'public_set_snapshot', 'ready', '{}'::jsonb, g, ts
  from public.sets s;
  insert into public.pokemon_market_explorer_prepared_directory_generations_v1
    (market_key,market_type,label,asset,era_id,prepared_series_key,comparison_as_of,source_as_of,current_value,
     history_available,history_point_count,source_kind,source_status,metadata,generation_id,generated_at,screen_group,screen_eligible)
  select case when q.normalized_spec->>'kind'='era' then 'era:'||(q.normalized_spec->>'id')
              when q.normalized_spec->>'kind'='rarity' then 'rarity:'||(q.normalized_spec->>'id')
              else 'curated:'||(q.normalized_spec->>'id') end,
     case q.normalized_spec->>'kind' when 'era' then 'era' when 'rarity' then 'prepared_rarity' else 'curated' end,
     q.normalized_spec->>'id','cards',null,q.query_fingerprint,v_asof,(q.series_payload->>'asOf')::date,100,true,1,
     'maintained_query_cache','ready',jsonb_build_object('queryFingerprint',q.query_fingerprint),g,ts,null,false
  from public.pokemon_market_explorer_query_cache q where q.cache_kind='maintained';
  insert into public.pokemon_market_explorer_prepared_directory_generations_v1
    (market_key,market_type,label,asset,prepared_series_key,comparison_as_of,source_as_of,current_value,
     history_available,history_point_count,source_kind,source_status,metadata,generation_id,generated_at)
  select 'sealed-format:'||k,'prepared_format',k,'sealed','sealed-segment:'||k,v_asof,v_asof,100,true,1,
     'prepared_sealed_snapshots','ready',jsonb_build_object('segmentKey',k,'segmentContractVersion','pokemon-sealed-segments-v1'),g,ts
  from unnest(array['boosterBox','eliteTrainerBox','pokemonCenterEliteTrainerBox','boosterBundle','packs']) k;
  insert into public.pokemon_market_explorer_prepared_history_generations_v1 (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
    select market_key, v_asof, 100, 100, 0, g from public.pokemon_market_explorer_prepared_directory_generations_v1 where generation_id=g;
  select count(*) into nrows from public.pokemon_market_explorer_prepared_directory_generations_v1 where generation_id=g;
  select count(*) into nh from public.pokemon_market_explorer_prepared_history_generations_v1 where generation_id=g;
  insert into public.pokemon_market_explorer_prepared_generations_v1
    (generation_id,status,generated_at,comparison_as_of,source_as_of,directory_rows,history_rows,history_markets,directory_fingerprint,history_fingerprint,completed_at)
  values (g,'complete',ts,v_asof,jsonb_build_object('sets',v_sets,'sealed',v_sets),nrows,nh,nh,
    (select md5(coalesce(string_agg(md5(to_jsonb(d)::text),'' order by market_key),'')) from public.pokemon_market_explorer_prepared_directory_generations_v1 d where generation_id=g),
    (select md5(coalesce(string_agg(md5(to_jsonb(h)::text),'' order by market_key,market_date),'')) from public.pokemon_market_explorer_prepared_history_generations_v1 h where generation_id=g),
    clock_timestamp());
  perform public.switch_pokemon_market_explorer_prepared_generation_v1(g,'promote','guarded_refresh');
  return jsonb_build_object('generationId',g,'generatedAt',ts,'comparisonAsOf',v_asof);
end $$;

-- PRODUCTION definitions verbatim (pre-migration state).
CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_explorer_prepared_if_current_v1(p_required_market_date date)
 RETURNS jsonb LANGUAGE plpgsql SET search_path TO ''
AS $function$
declare
  v_result jsonb;
  v_comparison_asof date;
begin
  if p_required_market_date is null then
    raise exception 'required Market Explorer prepared market date must not be null';
  end if;
  v_result := public.refresh_pokemon_market_explorer_prepared_directory_v1();
  v_comparison_asof := nullif(v_result->>'comparisonAsOf','')::date;
  if v_comparison_asof is distinct from p_required_market_date then
    raise exception 'Market Explorer prepared generation not current: comparisonAsOf=% required=%',
      coalesce(v_comparison_asof::text,'null'),p_required_market_date::text;
  end if;
  return v_result;
end;
$function$;

CREATE OR REPLACE FUNCTION public.run_market_explorer_guarded_publisher_v1(p_required_market_date date)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO ''
AS $function$
declare
  v_existing uuid;
  v_result jsonb;
begin
  if p_required_market_date is null then
    raise exception 'required Market Explorer prepared market date must not be null';
  end if;

  select g.generation_id
    into v_existing
  from public.pokemon_market_explorer_prepared_serving_v1 p
  join public.pokemon_market_explorer_prepared_generations_v1 g
    on g.generation_id = p.generation_id
  join public.pokemon_explore_set_value_snapshot_latest s
    on s.tcg = 'pokemon' and s.scope = 'market'
  where g.comparison_as_of = p_required_market_date
    and g.source_as_of->>'sets' = s.market_date::text
    and g.source_as_of->>'sealed' = s.market_date::text
    and s.updated_at <= g.generated_at
    and not exists (
      select 1
      from public.pokemon_market_explorer_query_cache c
      where c.cache_kind = 'maintained'
        and c.last_built_at > g.generated_at
    )
    and not exists (
      select 1
      from public.pokemon_set_market_dashboard_snapshot_latest d
      where d.updated_at > g.generated_at
    )
    and not exists (
      select 1
      from public.pokemon_set_sealed_market_snapshot_latest d
      where d.updated_at > g.generated_at
    )
  limit 1;

  if v_existing is not null then
    return jsonb_build_object(
      'status','already_current',
      'generationId',v_existing,
      'comparisonAsOf',p_required_market_date
    );
  end if;

  v_result := public.refresh_pokemon_market_explorer_prepared_if_current_v1(
    p_required_market_date
  );

  return jsonb_build_object(
    'status','refreshed',
    'result',v_result
  );
end;
$function$;
revoke all on function public.run_market_explorer_guarded_publisher_v1(date) from public, anon, authenticated, service_role;
grant execute on function public.run_market_explorer_guarded_publisher_v1(date) to market_explorer_publisher;
revoke all on function public.refresh_pokemon_market_explorer_prepared_if_current_v1(date) from public, anon, authenticated;
grant execute on function public.refresh_pokemon_market_explorer_prepared_if_current_v1(date) to service_role;
