-- Distinguish the market valuation date from the underlying source
-- observation date for carried-forward scoped vintage prices.
BEGIN;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_raw_surface_v2(
  p_generation_id uuid,
  p_market_date date,
  p_methodology_version text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '120s'
AS $function$
DECLARE
  v_refresh jsonb;
  v_current public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
  v_hist integer;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_duplicate_count integer;
BEGIN
  v_refresh:=public.refresh_pokemon_market_raw_edition_stable_history_v1(p_market_date);

  SELECT * INTO v_current
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1
  WHERE market_date=p_market_date;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_CURRENT_DATE_MISSING';
  END IF;

  DELETE FROM public.pokemon_market_explorer_surface_constituents_v2
   WHERE generation_id=p_generation_id AND market_key='raw';
  DELETE FROM public.pokemon_market_explorer_surface_constituent_totals_v2
   WHERE generation_id=p_generation_id AND market_key='raw';
  DELETE FROM public.pokemon_market_explorer_surface_history_v2
   WHERE generation_id=p_generation_id AND market_key='raw';
  DELETE FROM public.pokemon_market_explorer_surface_directory_v2
   WHERE generation_id=p_generation_id AND market_key='raw';

  DROP TABLE IF EXISTS pg_temp._mx_raw_stable_leaves;
  CREATE TEMP TABLE _mx_raw_stable_leaves ON COMMIT DROP AS
  WITH standard_leaves AS (
    SELECT
      c.card_variant_id::text AS instrument_id,
      c.set_id,
      c.market_price,
      p_market_date AS price_as_of,
      jsonb_build_object(
        'asset','cards',
        'instrumentId',c.card_variant_id,
        'cardVariantId',c.card_variant_id,
        'canonicalCardId',c.canonical_card_id,
        'setId',c.set_id,
        'rootSetId',c.root_set_id,
        'marketScope','standard',
        'name',cc.name,
        'cardName',cc.name,
        'cardNumber',coalesce(cc.number,cc.printed_number),
        'rarity',cc.rarity,
        'edition',m.edition,
        'printingType',coalesce(c.printing_type,m.printing_type),
        'specialType',m.special_type,
        'marketPrice',c.market_price,
        'priceAsOf',p_market_date,
        'sourceDate',c.captured_at,
        'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url),
        'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
        'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url),
        'sourceMarketKey','set:'||c.root_set_id::text
      ) AS item
    FROM public.pokemon_market_set_value_constituents_v1 c
    JOIN public.pokemon_market_set_value_constituent_publications_v1 p
      ON p.root_set_id=c.root_set_id
     AND p.market_date=c.market_date
     AND p.methodology_version=c.methodology_version
     AND p.status='READY'
    JOIN public.pokemon_market_root_authority a
      ON a.set_id=c.root_set_id
     AND a.activated_market_date<=p_market_date
     AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
    JOIN public.pokemon_canonical_cards cc ON cc.id=c.canonical_card_id
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata m
      ON m.card_variant_id=c.card_variant_id
    LEFT JOIN public.card_variants cv ON cv.id=c.card_variant_id
    WHERE c.market_date=p_market_date
      AND c.methodology_version=p_methodology_version
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 r
        WHERE r.set_id=c.root_set_id
      )
  ),
  scoped_market_keys AS (
    SELECT
      (x->>'setId')::uuid AS root_set_id,
      x->>'marketKey' AS market_key,
      x->>'marketScope' AS market_scope
    FROM jsonb_array_elements(v_current.constituents_json) x
    WHERE x->>'marketScope' IN ('first_edition','unlimited','shadowless')
  ),
  scoped_leaves AS (
    SELECT
      x.card_variant_id::text AS instrument_id,
      k.root_set_id AS set_id,
      x.market_price,
      p_market_date AS price_as_of,
      jsonb_build_object(
        'asset','cards',
        'instrumentId',x.card_variant_id,
        'cardVariantId',x.card_variant_id,
        'canonicalCardId',x.canonical_card_id,
        'setId',k.root_set_id,
        'rootSetId',k.root_set_id,
        'memberSetId',x.member_set_id,
        'marketScope',k.market_scope,
        'name',cc.name,
        'cardName',cc.name,
        'cardNumber',coalesce(cc.number,cc.printed_number),
        'rarity',cc.rarity,
        'edition',case k.market_scope
          when 'first_edition' then '1st-edition'
          else k.market_scope
        end,
        'setName',root.name,
        'printingType',coalesce(cv.printing_type,m.printing_type),
        'specialType',coalesce(cv.special_type,m.special_type),
        'marketPrice',x.market_price,
        'priceAsOf',p_market_date,
        'asOf',p_market_date,
        'sourceDate',x.observed_date,
        'imageUrl',coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,m.image_url),
        'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
        'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url),
        'sourceMarketKey',k.market_key,
        'identitySource','edition_history_card_prices_as_of_v2'
      ) AS item
    FROM scoped_market_keys k
    CROSS JOIN LATERAL public.get_pokemon_edition_history_card_prices_as_of_v2(
      k.root_set_id,p_market_date,false
    ) x
    JOIN public.pokemon_canonical_cards cc ON cc.id=x.canonical_card_id
    LEFT JOIN public.card_variants cv ON cv.id=x.card_variant_id
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata m
      ON m.card_variant_id=x.card_variant_id
    LEFT JOIN public.sets root ON root.id=k.root_set_id
    WHERE x.market_scope=k.market_scope
      AND x.card_variant_id IS NOT NULL
      AND x.market_price IS NOT NULL
      AND x.market_price>0
  )
  SELECT * FROM standard_leaves
  UNION ALL
  SELECT * FROM scoped_leaves;

  CREATE INDEX ON _mx_raw_stable_leaves(instrument_id);
  ANALYZE _mx_raw_stable_leaves;

  SELECT count(*)::integer,coalesce(sum(market_price),0)::numeric
  INTO v_leaf_count,v_leaf_value
  FROM _mx_raw_stable_leaves;

  SELECT count(*)::integer INTO v_duplicate_count
  FROM (
    SELECT instrument_id FROM _mx_raw_stable_leaves
    GROUP BY instrument_id HAVING count(*)>1
  ) d;

  IF v_duplicate_count<>0 THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_DUPLICATE_INSTRUMENTS: %',v_duplicate_count;
  END IF;
  IF v_leaf_count<>v_current.card_count THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_LEAF_COUNT_MISMATCH: leaves % expected %',
      v_leaf_count,v_current.card_count;
  END IF;
  IF round(v_leaf_value,2)<>round(v_current.basket_value,2) THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_LEAF_VALUE_MISMATCH: leaves % expected %',
      round(v_leaf_value,2),round(v_current.basket_value,2);
  END IF;

  INSERT INTO public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    source_as_of,current_tracked_value,current_index_value,
    history_available,history_start_date,history_end_date,history_point_count,
    constituent_count,composition_kind,availability,unavailable_reason,
    definition_version,screen_group,screen_eligible,metadata
  )
  SELECT
    p_generation_id,'raw','cards','parent','Raw Card Market','Raw Card Market',
    'pokemon_market_raw_edition_stable_daily_history_v1',
    p_market_date,
    v_current.basket_value,v_current.normalized_index_value,
    true,min(h.market_date),max(h.market_date),count(*)::integer,
    v_leaf_count,'index_and_composition','available',null,
    v_current.methodology_version,'card',false,
    jsonb_build_object(
      'editionStable',true,
      'indexConstituentKind','set_market_identity',
      'compositionConstituentKind','card_variant',
      'indexMethod','market-identity-chain-linked-common-cohort',
      'vintageScopesSeparate',true,
      'legacyGenericVintageExcluded',true,
      'rawIndexMarketCount',v_current.market_count,
      'rawIndexRootCount',v_current.root_count,
      'rawIndexCardCount',v_current.card_count,
      'compositionLeafCount',v_leaf_count,
      'legacyFrozenMethodologyVersion',p_methodology_version
    )
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
  WHERE h.market_date<=p_market_date;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  SELECT
    p_generation_id,'raw',h.market_date,h.normalized_index_value,h.basket_value,h.card_count,0
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
  WHERE h.market_date<=p_market_date
  ORDER BY h.market_date;
  GET DIAGNOSTICS v_hist=ROW_COUNT;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  ) VALUES (
    p_generation_id,'raw','cards',v_leaf_count,'available',null
  );

  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  SELECT
    p_generation_id,'raw',r.rank,r.instrument_id,'cards',r.set_id,r.market_price,r.price_as_of,
    r.item || jsonb_build_object('rank',r.rank,'parentMarketKey','raw')
  FROM (
    SELECT
      row_number() OVER (ORDER BY l.market_price DESC,l.instrument_id)::integer AS rank,
      l.*
    FROM _mx_raw_stable_leaves l
  ) r;

  RETURN v_refresh || jsonb_build_object(
    'historyRows',v_hist,
    'compositionLeafCount',v_leaf_count,
    'compositionValue',round(v_leaf_value,2),
    'editionStable',true
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
  TO service_role;

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
    p_market_date,
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
      'priceAsOf',p_market_date,
      'asOf',p_market_date,
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

COMMIT;
