-- A prepared generation must be enumerable by its pinned D3 source before
-- its pointer can be promoted. The sealed source watermark comes from product
-- history; the D3 roster comes from the compact public market snapshot.
-- Reject a candidate when those two authority dates diverge.
do $$
declare
  v_sql text;
  v_old text := '  if v_sealed_source_asof is null then' || chr(10) ||
    '    raise exception ''prepared sealed-family history unavailable'';' || chr(10) ||
    '  end if;';
  v_new text := v_old || chr(10) || chr(10) ||
    '  if not exists (' || chr(10) ||
    '    select 1 from public.pokemon_explore_set_value_snapshot_latest s' || chr(10) ||
    '    where s.tcg=''pokemon'' and s.scope=''market''' || chr(10) ||
    '      and s.market_date=v_sealed_source_asof' || chr(10) ||
    '      and s.updated_at <= v_generated_at' || chr(10) ||
    '      and not exists (' || chr(10) ||
    '        select 1 from unnest(array[''boosterBox'',''eliteTrainerBox'',''pokemonCenterEliteTrainerBox'',''boosterBundle'',''packs'']) segment_key' || chr(10) ||
    '        where coalesce(s.payload_json #>> array[''marketOverview'',''sealedSegments'',''segments'',segment_key,''currentConstituents'',''isComplete''],''false'') <> ''true''' || chr(10) ||
    '           or coalesce(jsonb_array_length(s.payload_json #> array[''marketOverview'',''sealedSegments'',''segments'',segment_key,''currentConstituents'',''topConstituents'']),-1)' || chr(10) ||
    '              <> coalesce((s.payload_json #>> array[''marketOverview'',''sealedSegments'',''segments'',segment_key,''currentConstituents'',''totalCount''])::integer,-1)' || chr(10) ||
    '      )' || chr(10) ||
    '  ) then' || chr(10) ||
    '    raise exception ''PREPARED_SEALED_D3_SOURCE_MISMATCH: sealed history as-of % has no complete matching D3 snapshot'',v_sealed_source_asof;' || chr(10) ||
    '  end if;';
begin
  select pg_get_functiondef('public.refresh_pokemon_market_explorer_prepared_directory_v1()'::regprocedure)
    into v_sql;
  if position(v_old in v_sql)=0 or position('PREPARED_SEALED_D3_SOURCE_MISMATCH' in v_sql)>0 then
    raise exception 'prepared refresh definition changed; refusing unsafe sealed source guard';
  end if;
  execute replace(v_sql,v_old,v_new);
end;
$$;
