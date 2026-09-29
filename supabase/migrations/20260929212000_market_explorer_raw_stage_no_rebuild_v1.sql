BEGIN;

-- Raw surface staging is a projection step, not an authority rebuild. The
-- canonical edition-stable Raw row for the target date is already required by
-- the current-surface publisher before candidate construction begins. Replaying
-- the entire Raw history again inside stage_pokemon_market_explorer_raw_surface_v2
-- duplicated heavy historical work and was the remaining 120s candidate-build
-- timeout. Consume the persisted target-date authority directly and fail closed
-- if it is absent.

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
  v_current public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
  v_hist integer;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_duplicate_count integer;
BEGIN
  SELECT * INTO v_current
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1
  WHERE market_date=p_market_date;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_CURRENT_DATE_MISSING';
  END IF;

  IF coalesce(v_current.methodology_version,'') <> 'edition_stable_market_identity_chain_v1' THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_METHODOLOGY_UNEXPECTED: %',
      coalesce(v_current.methodology_version,'null');
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
      'legacyFrozenMethodologyVersion',p_methodology_version,
      'authorityRefreshInsideStage',false
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

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'historyRows',v_hist,
    'compositionLeafCount',v_leaf_count,
    'compositionValue',round(v_leaf_value,2),
    'editionStable',true,
    'authorityRefreshInsideStage',false
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_raw_surface_v2(uuid,date,text)
  TO service_role;

COMMIT;
