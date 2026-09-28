-- Keep explicit vintage Set markets current from the bounded edition-history
-- v2 authority even when the legacy prepared publisher is stale or times out.
BEGIN;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_scoped_set_overlays_v2(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='60s'
SET lock_timeout='2s'
AS $function$
DECLARE
  v_markets integer;
  v_leaves integer;
  v_history integer;
  v_bad integer;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'SCOPED_SET_OVERLAY_ARGUMENTS_REQUIRED';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_generations_v2 g
    WHERE g.generation_id=p_generation_id
      AND g.market_date=p_market_date
      AND g.comparison_as_of=p_market_date
  ) THEN
    RAISE EXCEPTION 'SCOPED_SET_OVERLAY_GENERATION_WATERMARK_MISMATCH';
  END IF;

  DROP TABLE IF EXISTS pg_temp._mx_scoped_current;
  CREATE TEMP TABLE _mx_scoped_current ON COMMIT DROP AS
  SELECT
    d.market_key,
    d.set_id,
    d.market_scope,
    h.set_value,
    h.expected_card_count,
    h.priced_card_count,
    coalesce(cert.history_publishable,false) AS history_publishable,
    cert.certification_status AS history_certification_status,
    cert.certification_reason AS history_certification_reason
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow h
    ON h.set_id=d.set_id
   AND h.market_scope=d.market_scope
   AND h.market_date=p_market_date
   AND h.certified_on_date
  LEFT JOIN public.pokemon_market_scoped_history_market_certification_v1 cert
    ON cert.set_id=d.set_id
   AND cert.market_scope=d.market_scope
  WHERE d.generation_id=p_generation_id
    AND d.asset='cards'
    AND d.scope_kind='set'
    AND d.market_scope IN ('first_edition','unlimited','shadowless');

  SELECT count(*)::integer INTO v_markets FROM _mx_scoped_current;
  IF v_markets=0 THEN
    RETURN jsonb_build_object(
      'status','NO_CERTIFIED_SCOPES',
      'marketDate',p_market_date,
      'marketCount',0,
      'constituentCount',0,
      'historyRows',0
    );
  END IF;

  CREATE UNIQUE INDEX ON _mx_scoped_current(market_key);
  ANALYZE _mx_scoped_current;

  DROP TABLE IF EXISTS pg_temp._mx_scoped_leaves;
  CREATE TEMP TABLE _mx_scoped_leaves ON COMMIT DROP AS
  SELECT
    c.market_key,
    c.set_id AS root_set_id,
    c.market_scope,
    x.canonical_card_id,
    x.member_set_id,
    x.card_variant_id,
    x.market_price,
    x.observed_date,
    cc.name AS card_name,
    coalesce(cc.number,cc.printed_number) AS card_number,
    cc.rarity,
    coalesce(cv.printing_type,m.printing_type) AS printing_type,
    coalesce(cv.special_type,m.special_type) AS special_type,
    root.name AS root_set_name,
    coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url) AS image_url,
    coalesce(cv.image_small_url,cc.image_small_url) AS image_small_url,
    coalesce(cv.image_large_url,cc.image_large_url) AS image_large_url
  FROM _mx_scoped_current c
  CROSS JOIN LATERAL public.get_pokemon_edition_history_card_prices_as_of_v2(
    c.set_id,p_market_date,false
  ) x
  JOIN public.pokemon_canonical_cards cc ON cc.id=x.canonical_card_id
  LEFT JOIN public.card_variants cv ON cv.id=x.card_variant_id
  LEFT JOIN public.pokemon_market_explorer_card_current_metadata m
    ON m.card_variant_id=x.card_variant_id
  LEFT JOIN public.sets root ON root.id=c.set_id
  WHERE x.market_scope=c.market_scope
    AND x.card_variant_id IS NOT NULL
    AND x.market_price IS NOT NULL
    AND x.market_price>0;

  CREATE INDEX ON _mx_scoped_leaves(market_key,market_price DESC,card_variant_id);
  ANALYZE _mx_scoped_leaves;

  WITH rollup AS (
    SELECT
      market_key,
      count(*)::integer AS leaf_count,
      count(DISTINCT canonical_card_id)::integer AS canonical_count,
      count(DISTINCT card_variant_id)::integer AS variant_count,
      round(sum(market_price),2) AS leaf_value
    FROM _mx_scoped_leaves
    GROUP BY market_key
  )
  SELECT count(*)::integer INTO v_bad
  FROM _mx_scoped_current c
  LEFT JOIN rollup r USING(market_key)
  WHERE r.market_key IS NULL
     OR r.leaf_count<>c.priced_card_count
     OR r.canonical_count<>c.priced_card_count
     OR r.variant_count<>c.priced_card_count
     OR r.leaf_value<>round(c.set_value,2);

  IF v_bad>0 THEN
    RAISE EXCEPTION 'SCOPED_SET_OVERLAY_CURRENT_RECONCILIATION_FAILED: %',v_bad;
  END IF;

  DELETE FROM public.pokemon_market_explorer_surface_constituents_v2 x
  USING _mx_scoped_current c
  WHERE x.generation_id=p_generation_id
    AND x.market_key=c.market_key;

  DELETE FROM public.pokemon_market_explorer_surface_constituent_totals_v2 x
  USING _mx_scoped_current c
  WHERE x.generation_id=p_generation_id
    AND x.market_key=c.market_key;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  )
  SELECT
    p_generation_id,c.market_key,'cards',c.priced_card_count,'available',null
  FROM _mx_scoped_current c;

  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  SELECT
    p_generation_id,
    r.market_key,
    r.rank,
    r.card_variant_id::text,
    'cards',
    r.root_set_id,
    r.market_price,
    r.observed_date,
    jsonb_build_object(
      'rank',r.rank,
      'asset','cards',
      'instrumentId',r.card_variant_id,
      'cardVariantId',r.card_variant_id,
      'canonicalCardId',r.canonical_card_id,
      'setId',r.root_set_id,
      'memberSetId',r.member_set_id,
      'setName',r.root_set_name,
      'name',r.card_name,
      'cardName',r.card_name,
      'cardNumber',r.card_number,
      'rarity',r.rarity,
      'edition',case r.market_scope
        when 'first_edition' then '1st-edition'
        else r.market_scope
      end,
      'marketScope',r.market_scope,
      'printingType',r.printing_type,
      'specialType',r.special_type,
      'marketPrice',r.market_price,
      'priceAsOf',r.observed_date,
      'asOf',r.observed_date,
      'sourceDate',r.observed_date,
      'imageUrl',r.image_url,
      'imageSmallUrl',r.image_small_url,
      'imageLargeUrl',r.image_large_url,
      'identitySource','edition_history_card_prices_as_of_v2'
    )
  FROM (
    SELECT
      l.*,
      row_number() OVER (
        PARTITION BY l.market_key
        ORDER BY l.market_price DESC,l.card_variant_id
      )::integer AS rank
    FROM _mx_scoped_leaves l
  ) r;
  GET DIAGNOSTICS v_leaves=ROW_COUNT;

  DELETE FROM public.pokemon_market_explorer_surface_history_v2 x
  USING _mx_scoped_current c
  WHERE x.generation_id=p_generation_id
    AND x.market_key=c.market_key;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  WITH history_source AS (
    SELECT
      c.market_key,
      h.market_date,
      h.set_value,
      h.priced_card_count,
      first_value(h.set_value) OVER (
        PARTITION BY c.market_key
        ORDER BY h.market_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
      ) AS base_value
    FROM _mx_scoped_current c
    JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow h
      ON h.set_id=c.set_id
     AND h.market_scope=c.market_scope
     AND h.market_date<=p_market_date
     AND h.certified_on_date
    WHERE c.history_publishable
  )
  SELECT
    p_generation_id,
    h.market_key,
    h.market_date,
    100*h.set_value/nullif(h.base_value,0),
    h.set_value,
    h.priced_card_count,
    0
  FROM history_source h
  WHERE h.base_value>0
  ORDER BY h.market_key,h.market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  WITH stats AS (
    SELECT
      c.market_key,
      c.history_publishable,
      min(h.market_date) AS history_start_date,
      max(h.market_date) AS history_end_date,
      count(h.market_date)::integer AS history_point_count,
      max(h.index_value) FILTER (WHERE h.market_date=p_market_date) AS current_index_value
    FROM _mx_scoped_current c
    LEFT JOIN public.pokemon_market_explorer_surface_history_v2 h
      ON h.generation_id=p_generation_id
     AND h.market_key=c.market_key
    GROUP BY c.market_key,c.history_publishable
  )
  UPDATE public.pokemon_market_explorer_surface_directory_v2 d
  SET source_kind='edition_history_asof_v2',
      source_as_of=p_market_date,
      current_tracked_value=c.set_value,
      current_index_value=CASE
        WHEN s.history_publishable THEN s.current_index_value
        ELSE null
      END,
      history_available=(s.history_publishable AND s.history_point_count>0),
      history_start_date=CASE WHEN s.history_publishable THEN s.history_start_date ELSE null END,
      history_end_date=CASE WHEN s.history_publishable THEN s.history_end_date ELSE null END,
      history_point_count=CASE WHEN s.history_publishable THEN s.history_point_count ELSE 0 END,
      constituent_count=c.priced_card_count,
      composition_kind='index_and_composition',
      availability='available',
      unavailable_reason=null,
      return_7d_pct=CASE WHEN s.history_publishable THEN d.return_7d_pct ELSE null END,
      return_30d_pct=CASE WHEN s.history_publishable THEN d.return_30d_pct ELSE null END,
      return_90d_pct=CASE WHEN s.history_publishable THEN d.return_90d_pct ELSE null END,
      return_1y_pct=CASE WHEN s.history_publishable THEN d.return_1y_pct ELSE null END,
      current_drawdown_pct=CASE WHEN s.history_publishable THEN d.current_drawdown_pct ELSE null END,
      max_drawdown_pct=CASE WHEN s.history_publishable THEN d.max_drawdown_pct ELSE null END,
      metadata=coalesce(d.metadata,'{}'::jsonb)||jsonb_strip_nulls(jsonb_build_object(
        'certificationStatus','CERTIFIED',
        'editionAuthority','edition_history_card_prices_as_of_v2',
        'currentScopedValueCertified',true,
        'historyCertificationStatus',c.history_certification_status,
        'historyCertificationReason',c.history_certification_reason
      )),
      generated_at=clock_timestamp()
  FROM _mx_scoped_current c
  JOIN stats s USING(market_key)
  WHERE d.generation_id=p_generation_id
    AND d.market_key=c.market_key;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'marketCount',v_markets,
    'constituentCount',v_leaves,
    'historyRows',v_history,
    'historyPublishableMarkets',(
      SELECT count(*) FROM _mx_scoped_current WHERE history_publishable
    ),
    'historyWithheldMarkets',(
      SELECT count(*) FROM _mx_scoped_current WHERE NOT history_publishable
    )
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_scoped_set_overlays_v2(uuid,date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_scoped_set_overlays_v2(uuid,date)
TO service_role;


CREATE OR REPLACE FUNCTION public.build_pokemon_market_explorer_surface_candidate_v2(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
SET statement_timeout TO '300s'
AS $function$
DECLARE
  v_generation uuid:=gen_random_uuid();
  v_min_sealed date;
  v_max_sealed date;
  v_seed jsonb;
  v_scoped jsonb;
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
  FROM public.pokemon_market_explorer_prepared_directory_generations_v1 d
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

  v_scoped:=public.stage_pokemon_market_explorer_scoped_set_overlays_v2(
    v_generation,p_market_date
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
        'seed',v_seed,'scoped',v_scoped,'raw',v_raw,'rarity',v_rarity,
        'sealed',v_sealed,'sealedQuick',v_quick,'metrics',v_metrics
      )
  WHERE generation_id=v_generation;

  RETURN jsonb_build_object(
    'generationId',v_generation,'state','BUILT',
    'marketDate',p_market_date,'comparisonAsOf',p_market_date,
    'seed',v_seed,'scoped',v_scoped,'raw',v_raw,'rarity',v_rarity,
    'sealed',v_sealed,'sealedQuick',v_quick,'metrics',v_metrics
  );
END;
$function$;


COMMIT;
