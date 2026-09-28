-- Edition-stable Raw parent market.
-- Replaces the public Raw parent source with persistent Set-market identities:
-- standard roots remain one market; vintage roots are represented only by
-- explicit first_edition / unlimited / shadowless scopes. Generic vintage
-- "standard" baskets are never admitted.
BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_raw_edition_stable_daily_history_v1 (
  market_date date PRIMARY KEY,
  basket_value numeric NOT NULL CHECK (basket_value >= 0),
  normalized_index_value numeric NOT NULL CHECK (normalized_index_value > 0),
  daily_return numeric NOT NULL,
  previous_market_date date,
  market_count integer NOT NULL CHECK (market_count > 0),
  root_count integer NOT NULL CHECK (root_count > 0),
  card_count integer NOT NULL CHECK (card_count >= 0),
  cohort_fingerprint text NOT NULL,
  source_generation_fingerprint text NOT NULL,
  constituents_json jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(constituents_json) = 'array'),
  diagnostics_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(diagnostics_json) = 'object'),
  contract_version text NOT NULL DEFAULT 'pokemon-raw-edition-stable-v1'
    CHECK (contract_version = 'pokemon-raw-edition-stable-v1'),
  methodology_version text NOT NULL DEFAULT 'edition_stable_market_identity_chain_v1'
    CHECK (methodology_version = 'edition_stable_market_identity_chain_v1'),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.pokemon_market_raw_edition_stable_daily_history_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_raw_edition_stable_daily_history_v1
  FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_raw_edition_stable_daily_history_v1 TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_raw_edition_stable_history_v1(
  p_through_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
SET statement_timeout = '30s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_rows integer;
  v_current public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
BEGIN
  IF p_through_date IS NULL THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_THROUGH_DATE_REQUIRED';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-raw-edition-stable-v1:' || p_through_date::text, 0)
  ) THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_REFRESH_ALREADY_RUNNING' USING ERRCODE='55P03';
  END IF;

  DROP TABLE IF EXISTS pg_temp._raw_es_source;
  CREATE TEMP TABLE _raw_es_source ON COMMIT DROP AS
  WITH edition_roots AS (
    SELECT r.set_id
    FROM public.pokemon_edition_split_root_sets_v2 r
  ),
  standard_source AS (
    SELECT
      h.set_id,
      'standard'::text AS market_scope,
      'set:' || h.set_id::text AS market_key,
      h.snapshot_date AS market_date,
      h.set_value::numeric AS set_value,
      coalesce(h.included_card_count,h.priced_card_count,0)::integer AS card_count,
      h.source::text AS source,
      h.updated_at
    FROM public.pokemon_set_value_daily_history h
    JOIN public.pokemon_market_root_authority a
      ON a.set_id=h.set_id
     AND a.activated_market_date<=h.snapshot_date
     AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>h.snapshot_date)
    JOIN public.pokemon_market_date_quality q
      ON q.tcg='pokemon'
     AND q.market_date=h.snapshot_date
     AND q.status IN ('READY','LEGACY_VERIFIED')
    WHERE h.value_scope='standard'
      AND h.snapshot_date>=date '2026-04-23'
      AND h.snapshot_date<=p_through_date
      AND h.set_value>0
      AND coalesce(h.included_card_count,h.priced_card_count,0)>0
      AND NOT EXISTS (
        SELECT 1 FROM edition_roots e WHERE e.set_id=h.set_id
      )
  ),
  scoped_source AS (
    SELECT
      h.set_id,
      h.market_scope,
      'set:' || h.set_id::text || ':' || h.market_scope AS market_key,
      h.market_date,
      h.set_value::numeric,
      h.priced_card_count::integer AS card_count,
      h.source::text,
      h.updated_at
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    JOIN public.pokemon_market_scoped_history_market_certification_v1 c
      ON c.set_id=h.set_id
     AND c.market_scope=h.market_scope
     AND c.history_publishable
    JOIN public.pokemon_market_date_quality q
      ON q.tcg='pokemon'
     AND q.market_date=h.market_date
     AND q.status IN ('READY','LEGACY_VERIFIED')
    WHERE h.market_scope IN ('first_edition','unlimited','shadowless')
      AND h.certified_on_date
      AND h.market_date>=date '2026-04-23'
      AND h.market_date<=p_through_date
      AND h.set_value>0
      AND h.priced_card_count>0
  )
  SELECT * FROM standard_source
  UNION ALL
  SELECT * FROM scoped_source;

  CREATE UNIQUE INDEX ON _raw_es_source(market_key,market_date);
  CREATE INDEX ON _raw_es_source(market_date,market_key);
  ANALYZE _raw_es_source;

  IF EXISTS (
    SELECT 1
    FROM _raw_es_source s
    JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=s.set_id
    WHERE s.market_scope='standard'
  ) THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_GENERIC_VINTAGE_FORBIDDEN';
  END IF;

  DROP TABLE IF EXISTS pg_temp._raw_es_daily;
  CREATE TEMP TABLE _raw_es_daily ON COMMIT DROP AS
  WITH days AS (
    SELECT
      d.market_date,
      lag(d.market_date) OVER (ORDER BY d.market_date) AS previous_market_date
    FROM (SELECT DISTINCT market_date FROM _raw_es_source) d
  ),
  aggregated AS (
    SELECT
      d.market_date,
      d.previous_market_date,
      count(s.market_key)::integer AS market_count,
      count(DISTINCT s.set_id)::integer AS root_count,
      sum(s.card_count)::integer AS card_count,
      sum(s.set_value)::numeric AS basket_value,
      coalesce(sum(s.set_value) FILTER (WHERE p.market_key IS NOT NULL),0)::numeric AS current_common,
      coalesce(sum(p.set_value) FILTER (WHERE p.market_key IS NOT NULL),0)::numeric AS previous_common,
      count(*) FILTER (WHERE p.market_key IS NOT NULL)::integer AS common_market_count,
      pg_catalog.md5(pg_catalog.string_agg(
        s.market_key, '|' ORDER BY s.market_key
      )) AS cohort_fingerprint,
      pg_catalog.md5(pg_catalog.string_agg(
        s.market_key || ':' ||
        pg_catalog.round(s.set_value,2)::text || ':' ||
        s.card_count::text || ':' ||
        coalesce(s.source,'') || ':' ||
        coalesce(s.updated_at::text,''),
        '|' ORDER BY s.market_key
      )) AS source_generation_fingerprint,
      jsonb_agg(
        jsonb_build_object(
          'marketKey',s.market_key,
          'setId',s.set_id,
          'marketScope',s.market_scope,
          'setValue',s.set_value,
          'includedCardCount',s.card_count,
          'source',s.source,
          'sourceUpdatedAt',s.updated_at
        )
        ORDER BY s.market_key
      ) AS constituents_json
    FROM days d
    JOIN _raw_es_source s ON s.market_date=d.market_date
    LEFT JOIN _raw_es_source p
      ON p.market_key=s.market_key
     AND p.market_date=d.previous_market_date
    GROUP BY d.market_date,d.previous_market_date
  )
  SELECT
    a.*,
    CASE
      WHEN a.previous_market_date IS NULL THEN 0::numeric
      WHEN a.previous_common>0 THEN a.current_common/a.previous_common-1
      ELSE 0::numeric
    END AS daily_return
  FROM aggregated a;

  INSERT INTO public.pokemon_market_raw_edition_stable_daily_history_v1(
    market_date,basket_value,normalized_index_value,daily_return,previous_market_date,
    market_count,root_count,card_count,cohort_fingerprint,source_generation_fingerprint,
    constituents_json,diagnostics_json,updated_at
  )
  SELECT
    d.market_date,
    d.basket_value,
    100 * pg_catalog.exp(
      sum(pg_catalog.ln(1+d.daily_return))
      OVER (ORDER BY d.market_date ROWS UNBOUNDED PRECEDING)
    ),
    d.daily_return,
    d.previous_market_date,
    d.market_count,
    d.root_count,
    d.card_count,
    d.cohort_fingerprint,
    d.source_generation_fingerprint,
    d.constituents_json,
    jsonb_build_object(
      'editionStable',true,
      'indexConstituentKind','set_market_identity',
      'legacyGenericVintageExcluded',true,
      'vintageScopesSeparate',true,
      'commonMarketCount',d.common_market_count
    ),
    clock_timestamp()
  FROM _raw_es_daily d
  ON CONFLICT(market_date) DO UPDATE
  SET basket_value=excluded.basket_value,
      normalized_index_value=excluded.normalized_index_value,
      daily_return=excluded.daily_return,
      previous_market_date=excluded.previous_market_date,
      market_count=excluded.market_count,
      root_count=excluded.root_count,
      card_count=excluded.card_count,
      cohort_fingerprint=excluded.cohort_fingerprint,
      source_generation_fingerprint=excluded.source_generation_fingerprint,
      constituents_json=excluded.constituents_json,
      diagnostics_json=excluded.diagnostics_json,
      contract_version=excluded.contract_version,
      methodology_version=excluded.methodology_version,
      updated_at=excluded.updated_at;
  GET DIAGNOSTICS v_rows=ROW_COUNT;

  SELECT * INTO v_current
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1
  WHERE market_date=p_through_date;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'RAW_EDITION_STABLE_CURRENT_DATE_MISSING: %',p_through_date;
  END IF;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',v_current.market_date,
    'marketCount',v_current.market_count,
    'rootCount',v_current.root_count,
    'cardCount',v_current.card_count,
    'basketValue',v_current.basket_value,
    'indexValue',v_current.normalized_index_value,
    'rowsUpserted',v_rows,
    'methodologyVersion',v_current.methodology_version
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_market_raw_edition_stable_history_v1(date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_market_raw_edition_stable_history_v1(date)
  TO service_role;

-- Backfill the compact authority from accepted historical observations.
SELECT public.refresh_pokemon_market_raw_edition_stable_history_v1(
  (SELECT max(q.market_date)
   FROM public.pokemon_market_date_quality q
   WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED'))
);

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
      x->>'marketKey' AS market_key
    FROM jsonb_array_elements(v_current.constituents_json) x
    WHERE x->>'marketScope' IN ('first_edition','unlimited','shadowless')
  ),
  scoped_leaves AS (
    SELECT
      c.instrument_id,
      c.set_id,
      c.market_price,
      c.price_as_of,
      c.item || jsonb_build_object('sourceMarketKey',c.market_key) AS item
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    JOIN scoped_market_keys k ON k.market_key=c.market_key
    WHERE c.generation_id=p_generation_id
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

CREATE OR REPLACE FUNCTION public.assert_pokemon_market_explorer_surface_coherent_v2(
  p_generation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '10s'
AS $function$
DECLARE
  g public.pokemon_market_explorer_surface_generations_v2%rowtype;
  v_raw public.pokemon_market_raw_edition_stable_daily_history_v1%rowtype;
  v_base_date date;
  v_bad integer;
  v_quicks integer;
  v_leaf_count integer;
  v_leaf_value numeric;
  v_dir_value numeric;
  v_dir_index numeric;
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
  FROM public.pokemon_market_explorer_prepared_directory_generations_v1 d
  WHERE d.generation_id=g.base_prepared_generation_id;
  IF v_base_date IS DISTINCT FROM g.comparison_as_of THEN
    RAISE EXCEPTION 'SURFACE_BASE_PREPARED_WATERMARK_MISMATCH';
  END IF;

  SELECT * INTO v_raw
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1
  WHERE market_date=g.comparison_as_of;
  IF NOT FOUND THEN RAISE EXCEPTION 'SURFACE_RAW_EDITION_STABLE_WATERMARK_MISSING'; END IF;

  SELECT d.current_tracked_value,d.current_index_value
  INTO v_dir_value,v_dir_index
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id AND d.market_key='raw';
  IF NOT FOUND
     OR round(v_dir_value,2)<>round(v_raw.basket_value,2)
     OR abs(v_dir_index-v_raw.normalized_index_value)>0.00000001
  THEN
    RAISE EXCEPTION 'SURFACE_RAW_EDITION_STABLE_DIRECTORY_MISMATCH';
  END IF;

  SELECT count(*)::integer,coalesce(sum(c.market_price),0)::numeric
  INTO v_leaf_count,v_leaf_value
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  WHERE c.generation_id=p_generation_id AND c.market_key='raw';

  IF v_leaf_count<>v_raw.card_count
     OR round(v_leaf_value,2)<>round(v_raw.basket_value,2)
  THEN
    RAISE EXCEPTION 'SURFACE_RAW_EDITION_STABLE_COMPOSITION_MISMATCH';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=c.set_id
    WHERE c.generation_id=p_generation_id
      AND c.market_key='raw'
      AND coalesce(c.item->>'marketScope','standard')='standard'
  ) THEN
    RAISE EXCEPTION 'SURFACE_RAW_GENERIC_VINTAGE_LEAF_FORBIDDEN';
  END IF;

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
    'rawEditionStableMarkets',v_raw.market_count,
    'rawEditionStableRoots',v_raw.root_count,
    'rawLeafCount',v_leaf_count,
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
