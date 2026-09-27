BEGIN;

-- V2 must seed from the immutable V1 serving generation, not the ephemeral
-- prepared workspace that is emptied/rotated after guarded publication.

create or replace function public.seed_pokemon_market_explorer_surface_from_prepared_v1(
  p_generation_id uuid,
  p_base_generation_id uuid
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '90s'
as $function$
declare
  v_dir integer;
  v_hist integer;
  v_const integer := 0;
begin
  if not exists (
    select 1
    from public.pokemon_market_explorer_prepared_serving_v1 s
    where s.singleton is true and s.generation_id=p_base_generation_id
  ) then
    raise exception 'BASE_PREPARED_GENERATION_NOT_SERVING';
  end if;

  insert into public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    set_id,era_id,market_scope,taxonomy_key,source_as_of,
    current_tracked_value,current_index_value,history_available,
    history_start_date,history_end_date,history_point_count,
    constituent_count,composition_kind,availability,definition_version,
    return_7d_pct,return_30d_pct,return_90d_pct,return_1y_pct,
    current_drawdown_pct,max_drawdown_pct,screen_group,screen_eligible,
    metadata,generated_at
  )
  select
    p_generation_id,d.market_key,d.asset,
    case d.market_type
      when 'set' then 'set'
      when 'era' then 'era'
      when 'curated' then 'quick'
      when 'prepared_rarity' then 'rarity'
      else 'type'
    end,
    d.label,
    coalesce(nullif(d.metadata->>'baseSetName',''),d.label),
    d.source_kind,d.set_id,d.era_id,
    nullif(d.metadata->>'marketScope',''),
    coalesce(
      nullif(d.metadata->>'rarityKey',''),
      nullif(d.metadata->>'segmentKey',''),
      nullif(d.metadata->>'segmentId',''),
      nullif(d.metadata->>'filterRarityKey','')
    ),
    d.source_as_of,
    d.comparison_value,d.comparison_index_value,d.history_available,
    d.history_start_date,d.history_end_date,d.history_point_count,
    0,
    case when d.asset='cards' then 'index_and_composition' else 'index' end,
    'available',
    coalesce(nullif(d.metadata->>'definitionVersion',''),d.prepared_series_key),
    d.return_7d_pct,d.return_30d_pct,d.return_90d_pct,d.return_1y_pct,
    d.current_drawdown_pct,d.max_drawdown_pct,d.screen_group,d.screen_eligible,
    d.metadata || jsonb_build_object(
      'basePreparedGenerationId',p_base_generation_id,
      'legacyMarketType',d.market_type,
      'copiedWithoutMathChange',true
    ),
    clock_timestamp()
  from public.pokemon_market_explorer_prepared_serving_directory_v1 d
  where d.generation_id=p_base_generation_id
    and not (d.asset='sealed' and d.market_type='prepared_format');
  get diagnostics v_dir=row_count;

  insert into public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  select p_generation_id,h.market_key,h.market_date,h.index_value,h.tracked_value,null,h.chain_segment_id
  from public.pokemon_market_explorer_prepared_serving_history_v1 h
  join public.pokemon_market_explorer_surface_directory_v2 d
    on d.generation_id=p_generation_id and d.market_key=h.market_key
  where h.generation_id=p_base_generation_id;
  get diagnostics v_hist=row_count;

  if pg_catalog.to_regclass('public.pokemon_market_explorer_prepared_constituent_totals_v1') is not null
     and pg_catalog.to_regclass('public.pokemon_market_explorer_prepared_constituents_v1') is not null then

    execute $copy_totals$
      insert into public.pokemon_market_explorer_surface_constituent_totals_v2(
        generation_id,market_key,asset,total_count,availability,availability_reason
      )
      select $1,t.market_key,t.asset,t.total_count,t.availability,t.availability_reason
      from public.pokemon_market_explorer_prepared_constituent_totals_v1 t
      join public.pokemon_market_explorer_surface_directory_v2 d
        on d.generation_id=$1 and d.market_key=t.market_key
      where t.generation_id=$2
      on conflict (generation_id,market_key) do nothing
    $copy_totals$ using p_generation_id,p_base_generation_id;

    execute $copy_rows$
      insert into public.pokemon_market_explorer_surface_constituents_v2(
        generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
      )
      select
        $1,p.market_key,p.rank,p.instrument_id,p.asset,
        coalesce(cm.set_id,nullif(p.item->>'setId','')::uuid),
        p.market_price,p.price_as_of,
        case when p.asset='cards' then
          p.item || jsonb_build_object(
            'rank',p.rank,
            'asset','cards',
            'instrumentId',p.instrument_id,
            'cardVariantId',cm.card_variant_id,
            'canonicalCardId',cm.canonical_card_id,
            'setId',cm.set_id,
            'setName',s.name,
            'name',cm.card_name,
            'cardName',cm.card_name,
            'cardNumber',cm.card_number,
            'rarity',cm.rarity,
            'edition',cm.edition,
            'printingType',cm.printing_type,
            'specialType',cm.special_type,
            'marketPrice',p.market_price,
            'priceAsOf',p.price_as_of,
            'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,cm.image_url),
            'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
            'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url)
          )
        else p.item end
      from public.pokemon_market_explorer_prepared_constituents_v1 p
      join public.pokemon_market_explorer_surface_directory_v2 d
        on d.generation_id=$1 and d.market_key=p.market_key
      left join public.pokemon_market_explorer_card_current_metadata cm
        on p.asset='cards' and p.instrument_id=cm.card_variant_id::text
      left join public.card_variants cv on cv.id=cm.card_variant_id
      left join public.pokemon_canonical_cards cc on cc.id=cm.canonical_card_id
      left join public.sets s on s.id=cm.set_id
      where p.generation_id=$2
    $copy_rows$ using p_generation_id,p_base_generation_id;
    get diagnostics v_const=row_count;

    update public.pokemon_market_explorer_surface_directory_v2 d
    set constituent_count=t.total_count,
        availability=t.availability,
        unavailable_reason=t.availability_reason
    from public.pokemon_market_explorer_surface_constituent_totals_v2 t
    where d.generation_id=p_generation_id
      and t.generation_id=d.generation_id and t.market_key=d.market_key;
  end if;

  return jsonb_build_object(
    'directoryRows',v_dir,'historyRows',v_hist,'constituentRows',v_const
  );
end;
$function$;

revoke all on function public.seed_pokemon_market_explorer_surface_from_prepared_v1(uuid,uuid)
from public,anon,authenticated;
grant execute on function public.seed_pokemon_market_explorer_surface_from_prepared_v1(uuid,uuid)
to service_role;



CREATE OR REPLACE FUNCTION public.build_pokemon_market_explorer_surface_candidate_v2(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='300s'
AS $function$
DECLARE
  v_generation uuid:=gen_random_uuid();
  v_min_sealed date;
  v_max_sealed date;
  v_seed jsonb;
  v_raw jsonb;
  v_rarity jsonb;
  v_sealed jsonb;
  v_quick jsonb;
  v_metrics jsonb;
  v_base_date date;
BEGIN
  IF p_base_generation_id IS NULL OR p_market_date IS NULL OR nullif(p_raw_methodology_version,'') IS NULL THEN
    RAISE EXCEPTION 'SURFACE_CANDIDATE_ARGUMENTS_REQUIRED';
  END IF;

  SELECT CASE
    WHEN count(*)>0 AND count(distinct d.comparison_as_of)=1
      THEN max(d.comparison_as_of)
    ELSE null
  END
  INTO v_base_date
  FROM public.pokemon_market_explorer_prepared_serving_directory_v1 d
  WHERE d.generation_id=p_base_generation_id;

  IF v_base_date IS DISTINCT FROM p_market_date THEN
    RAISE EXCEPTION 'SURFACE_BASE_PREPARED_GENERATION_STALE: base % target %',
      coalesce(v_base_date::text,'null'),p_market_date::text;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
    WHERE d.market_date=p_market_date AND d.market_price>0
  ) THEN
    RAISE EXCEPTION 'SURFACE_CARD_DAILY_NOT_CURRENT';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    WHERE c.singleton AND c.certified_through>=p_market_date
  ) THEN
    RAISE EXCEPTION 'SURFACE_RARITY_COVERAGE_NOT_CERTIFIED';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  INSERT INTO public.pokemon_market_explorer_surface_generations_v2(
    generation_id,base_prepared_generation_id,market_date,comparison_as_of,
    raw_methodology_version,state
  ) VALUES (
    v_generation,p_base_generation_id,p_market_date,p_market_date,
    p_raw_methodology_version,'BUILDING'
  );

  v_seed:=public.seed_pokemon_market_explorer_surface_from_prepared_v1(
    v_generation,p_base_generation_id
  );

  SELECT
    (SELECT min(o.captured_at::date) FROM public.sealed_product_price_observations o),
    (SELECT max(d.market_date) FROM public.pokemon_market_explorer_sealed_daily_v1 d)
  INTO v_min_sealed,v_max_sealed;

  IF v_min_sealed IS NOT NULL AND (v_max_sealed IS NULL OR v_max_sealed<p_market_date) THEN
    PERFORM public.refresh_pokemon_market_explorer_sealed_daily_v1(
      CASE WHEN v_max_sealed IS NULL THEN v_min_sealed ELSE v_max_sealed+1 END,
      p_market_date
    );
  END IF;

  PERFORM public.refresh_pokemon_market_explorer_sealed_current_metadata_v1();
  PERFORM public.refresh_pokemon_market_explorer_sealed_type_registry_v1();

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date=p_market_date AND d.market_price>0
  ) THEN
    RAISE EXCEPTION 'SURFACE_SEALED_DAILY_NOT_CURRENT';
  END IF;

  PERFORM public.refresh_pokemon_market_explorer_rarity_registry_v1(p_market_date);

  v_raw:=public.stage_pokemon_market_explorer_raw_surface_v2(
    v_generation,p_market_date,p_raw_methodology_version
  );
  v_rarity:=public.stage_pokemon_market_explorer_rarity_candidates_v2(
    v_generation,p_market_date
  );
  v_sealed:=public.stage_pokemon_market_explorer_sealed_lattice_v2(
    v_generation,p_market_date
  );
  v_quick:=public.stage_pokemon_market_explorer_sealed_quick_markets_v2(
    v_generation,p_market_date
  );
  v_metrics:=public.finalize_pokemon_market_explorer_surface_metrics_v2(
    v_generation,p_market_date
  );

  UPDATE public.pokemon_market_explorer_surface_generations_v2
  SET state='BUILT',built_at=clock_timestamp(),
      diagnostics=jsonb_build_object(
        'seed',v_seed,'raw',v_raw,'rarity',v_rarity,
        'sealed',v_sealed,'sealedQuick',v_quick,'metrics',v_metrics
      )
  WHERE generation_id=v_generation;

  RETURN jsonb_build_object(
    'generationId',v_generation,'state','BUILT',
    'marketDate',p_market_date,'comparisonAsOf',p_market_date,
    'seed',v_seed,'raw',v_raw,'rarity',v_rarity,
    'sealed',v_sealed,'sealedQuick',v_quick,'metrics',v_metrics
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
TO service_role;



CREATE OR REPLACE FUNCTION public.assert_pokemon_market_explorer_surface_coherent_v2(
  p_generation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='10s'
AS $function$
DECLARE
  g public.pokemon_market_explorer_surface_generations_v2%rowtype;
  v_raw public.pokemon_market_index_daily_history%rowtype;
  v_base_date date;
  v_expected_roots integer;
  v_ready_roots integer;
  v_bad integer;
  v_quicks integer;
BEGIN
  SELECT * INTO g
  FROM public.pokemon_market_explorer_surface_generations_v2
  WHERE generation_id=p_generation_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'SURFACE_GENERATION_NOT_FOUND'; END IF;
  IF g.comparison_as_of IS NULL OR g.comparison_as_of IS DISTINCT FROM g.market_date THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_WATERMARK_INVALID';
  END IF;

  SELECT CASE
    WHEN count(*)>0 AND count(distinct d.comparison_as_of)=1
      THEN max(d.comparison_as_of)
    ELSE null
  END
  INTO v_base_date
  FROM public.pokemon_market_explorer_prepared_serving_directory_v1 d
  WHERE d.generation_id=g.base_prepared_generation_id;
  IF v_base_date IS DISTINCT FROM g.comparison_as_of THEN
    RAISE EXCEPTION 'SURFACE_BASE_PREPARED_WATERMARK_MISMATCH';
  END IF;

  SELECT * INTO v_raw
  FROM public.pokemon_market_index_daily_history h
  WHERE h.tcg='pokemon' AND h.index_key='raw'
    AND h.market_date=g.comparison_as_of
    AND h.methodology_version=g.raw_methodology_version
  ORDER BY h.updated_at DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'SURFACE_RAW_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
    WHERE d.market_date=g.comparison_as_of AND d.market_price>0
  ) THEN RAISE EXCEPTION 'SURFACE_CARD_DAILY_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date=g.comparison_as_of AND d.market_price>0
  ) THEN RAISE EXCEPTION 'SURFACE_SEALED_DAILY_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    WHERE c.singleton AND c.certified_through>=g.comparison_as_of
  ) THEN RAISE EXCEPTION 'SURFACE_RARITY_CERTIFICATION_WATERMARK_MISSING'; END IF;

  WITH roots AS (
    SELECT
      (x->>'setId')::uuid root_set_id,
      (x->>'setValue')::numeric expected_value,
      (x->>'includedCardCount')::integer expected_count
    FROM jsonb_array_elements(v_raw.constituents_json) x
  )
  SELECT count(*)::integer,
         count(p.root_set_id) filter(
           where p.status='READY'
             and p.constituent_count=r.expected_count
             and round(p.constituent_value,2)=round(r.expected_value,2)
         )::integer
  INTO v_expected_roots,v_ready_roots
  FROM roots r
  LEFT JOIN public.pokemon_market_set_value_constituent_publications_v1 p
    ON p.root_set_id=r.root_set_id
   AND p.market_date=g.comparison_as_of
   AND p.methodology_version=g.raw_methodology_version;

  IF v_expected_roots<>v_raw.set_count OR v_ready_roots<>v_expected_roots THEN
    RAISE EXCEPTION 'SURFACE_RAW_FROZEN_ROSTER_INCOMPLETE: ready % expected %',
      coalesce(v_ready_roots,0),coalesce(v_expected_roots,0);
  END IF;

  SELECT count(*)::integer INTO v_bad
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.comparison_as_of IS DISTINCT FROM g.comparison_as_of;
  IF v_bad>0 THEN
    RAISE EXCEPTION 'SURFACE_DIRECTORY_WATERMARK_MISMATCH: %',v_bad;
  END IF;

  SELECT count(*)::integer INTO v_bad
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.availability='available'
    AND d.history_available
    AND d.history_end_date IS DISTINCT FROM g.comparison_as_of;
  IF v_bad>0 THEN
    RAISE EXCEPTION 'SURFACE_AVAILABLE_HISTORY_NOT_CURRENT: %',v_bad;
  END IF;

  SELECT count(*)::integer INTO v_quicks
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.asset='sealed' AND d.scope_kind='quick'
    AND d.market_key IN (
      'sealed-quick:obtainable','sealed-quick:intermediate','sealed-quick:premium',
      'sealed-quick:new-releases','sealed-quick:established','sealed-quick:global-top10'
    );
  IF v_quicks<>6 THEN
    RAISE EXCEPTION 'SURFACE_SEALED_QUICK_SET_INCOMPLETE: %',v_quicks;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    WHERE c.generation_id=p_generation_id
      AND c.market_key LIKE 'sealed-quick:%'
      AND coalesce((c.item->>'isBulkContainer')::boolean,false)
  ) THEN
    RAISE EXCEPTION 'SURFACE_SEALED_QUICK_CONTAINS_BULK';
  END IF;

  RETURN jsonb_build_object(
    'generationId',p_generation_id,
    'comparisonAsOf',g.comparison_as_of,
    'rawFrozenRoots',v_ready_roots,
    'sealedQuickMarkets',v_quicks,
    'status','COHERENT'
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.assert_pokemon_market_explorer_surface_coherent_v2(uuid)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.assert_pokemon_market_explorer_surface_coherent_v2(uuid)
TO service_role;



COMMIT;
