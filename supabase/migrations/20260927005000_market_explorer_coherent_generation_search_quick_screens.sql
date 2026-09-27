BEGIN;

-- Market Explorer correction pass:
-- one certified comparison watermark, asset-aware leaf search,
-- six consumer Sealed Quick Markets, and generation-pinned screens.

ALTER TABLE public.pokemon_market_explorer_surface_generations_v2
  ADD COLUMN IF NOT EXISTS comparison_as_of date;

ALTER TABLE public.pokemon_market_explorer_surface_directory_v2
  ADD COLUMN IF NOT EXISTS comparison_as_of date;

CREATE INDEX IF NOT EXISTS pokemon_market_explorer_surface_directory_v2_watermark_idx
  ON public.pokemon_market_explorer_surface_directory_v2(
    generation_id,comparison_as_of,asset,scope_kind,market_key
  );

-- ---------------------------------------------------------------------------
-- A. Latest date the complete Explorer stack can truthfully support.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_promotable_date_v1()
RETURNS date
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '5s'
AS $function$
WITH prepared AS MATERIALIZED (
  SELECT max(d.comparison_as_of) AS comparison_as_of
  FROM public.pokemon_market_explorer_prepared_directory_v1 d
  JOIN public.pokemon_market_explorer_prepared_serving_v1 s
    ON s.singleton AND s.generation_id=d.generation_id
),
raw_rows AS MATERIALIZED (
  SELECT h.*
  FROM public.pokemon_market_index_daily_history h
  WHERE h.tcg='pokemon'
    AND h.index_key='raw'
),
eligible AS (
  SELECT q.market_date
  FROM public.pokemon_market_date_quality q
  JOIN prepared b ON b.comparison_as_of=q.market_date
  JOIN raw_rows r ON r.market_date=q.market_date
  WHERE q.tcg='pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_card_daily_states_v2_shadow c
      WHERE c.market_date=q.market_date
        AND c.market_price>0
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_sealed_daily_v1 s
      WHERE s.market_date=q.market_date
        AND s.market_price>0
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_sealed_current_metadata_v1 sm
      WHERE sm.latest_market_date>=q.market_date
        AND sm.latest_market_price>0
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_rarity_coverage_certification_v1 rc
      WHERE rc.singleton
        AND rc.certified_through>=q.market_date
    )
    AND NOT EXISTS (
      SELECT 1
      FROM pg_catalog.jsonb_array_elements(r.constituents_json) x
      WHERE NOT EXISTS (
        SELECT 1
        FROM public.pokemon_market_set_value_constituent_publications_v1 p
        WHERE p.root_set_id=(x->>'setId')::uuid
          AND p.market_date=q.market_date
          AND p.methodology_version=r.methodology_version
          AND p.status='READY'
          AND p.constituent_count=(x->>'includedCardCount')::integer
          AND round(p.constituent_value,2)=round((x->>'setValue')::numeric,2)
      )
    )
)
SELECT max(market_date) FROM eligible
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_promotable_date_v1()
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_promotable_date_v1()
TO service_role;

-- ---------------------------------------------------------------------------
-- B. Search eligibility uses each asset's materialized authority date.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text DEFAULT 'all',
  p_limit integer DEFAULT 20
)
RETURNS TABLE(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  product_family text,
  variant_label text,
  match_kind text,
  relevance_score integer,
  name_similarity real
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '1s'
SET work_mem = '16MB'
AS $function$
WITH asset_dates AS MATERIALIZED (
  SELECT
    (SELECT max(d.market_date)
     FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
     WHERE d.market_price>0) AS cards_date,
    (SELECT max(m.latest_market_date)
     FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
     WHERE m.latest_market_price>0) AS sealed_date
),
base AS MATERIALIZED (
  SELECT *
  FROM public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(
    p_query,p_asset,50
  )
),
eligible AS (
  SELECT b.*
  FROM base b
  CROSS JOIN asset_dates a
  WHERE (
    b.asset='cards'
    AND a.cards_date IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
      WHERE d.card_variant_id=b.instrument_id
        AND d.market_date=a.cards_date
        AND d.market_price>0
    )
  ) OR (
    b.asset='sealed'
    AND a.sealed_date IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
      WHERE nullif(m.sealed_product_id,'')::uuid=b.instrument_id
        AND m.latest_market_date=a.sealed_date
        AND m.latest_market_price>0
    )
  )
)
SELECT
  e.asset,e.instrument_id,e.name,e.set_id,e.set_name,e.image_url,
  e.card_number,e.rarity,e.edition,e.printing_type,e.special_type,
  e.product_family,e.variant_label,e.match_kind,e.relevance_score,
  e.name_similarity
FROM eligible e
ORDER BY
  e.relevance_score DESC,
  CASE WHEN e.match_kind='fuzzy_name' THEN e.name_similarity ELSE 0::real END DESC,
  pg_catalog.lower(e.name),
  pg_catalog.lower(coalesce(e.set_name,'')),
  e.asset,e.instrument_id
LIMIT least(greatest(coalesce(p_limit,20),1),50)
$function$;

REVOKE ALL ON FUNCTION public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
TO service_role;

CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_leaf_instruments_v3(
  p_query text,
  p_asset text DEFAULT 'all',
  p_limit integer DEFAULT 20
)
RETURNS TABLE(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  market_price numeric,
  market_date date,
  card_variant_id uuid,
  canonical_card_id uuid,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  sealed_product_id uuid,
  product_family text,
  variant_label text,
  is_bulk_container boolean,
  match_kind text,
  relevance_score integer
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '1s'
SET work_mem = '16MB'
AS $function$
WITH norm AS MATERIALIZED (
  SELECT public.normalize_pokemon_market_explorer_search_text_v2(coalesce(p_query,'')) q
),
asset_dates AS MATERIALIZED (
  SELECT
    (SELECT max(d.market_date)
     FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
     WHERE d.market_price>0) AS cards_date,
    (SELECT max(m.latest_market_date)
     FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
     WHERE m.latest_market_price>0) AS sealed_date
),
base AS MATERIALIZED (
  SELECT *
  FROM public.search_pokemon_market_explorer_instruments_v2(
    p_query,p_asset,50
  )
),
enriched AS (
  SELECT
    b.asset,
    b.instrument_id,
    b.name,
    b.set_id,
    b.set_name,
    CASE
      WHEN b.asset='cards' THEN
        coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,cm.image_url,b.image_url)
      ELSE coalesce(sm.image_small_url,sm.image_large_url,b.image_url)
    END AS image_url,
    CASE WHEN b.asset='cards' THEN cd.market_price ELSE sm.latest_market_price END AS market_price,
    CASE WHEN b.asset='cards' THEN cd.market_date ELSE sm.latest_market_date END AS market_date,
    CASE WHEN b.asset='cards' THEN cm.card_variant_id END AS card_variant_id,
    CASE WHEN b.asset='cards' THEN cm.canonical_card_id END AS canonical_card_id,
    b.card_number,b.rarity,b.edition,b.printing_type,b.special_type,
    CASE WHEN b.asset='sealed' THEN b.instrument_id END AS sealed_product_id,
    coalesce(sm.product_family,b.product_family) AS product_family,
    coalesce(sm.variant_label,b.variant_label) AS variant_label,
    CASE WHEN b.asset='sealed' THEN coalesce(sm.is_bulk_container,false) ELSE false END AS is_bulk_container,
    CASE
      WHEN b.asset='sealed'
       AND public.normalize_pokemon_market_explorer_search_text_v2(b.name)=(SELECT q FROM norm)
        THEN 'exact_name'
      WHEN b.asset='sealed'
       AND public.normalize_pokemon_market_explorer_search_text_v2(b.name)
           LIKE (SELECT q FROM norm)||'%'
        THEN 'name_prefix'
      WHEN b.asset='sealed'
       AND pg_catalog.strpos(
             ' '||public.normalize_pokemon_market_explorer_search_text_v2(b.name)||' ',
             ' '||(SELECT q FROM norm)||' '
           )>0
        THEN 'contiguous_phrase'
      ELSE b.match_kind
    END AS refined_match_kind,
    CASE
      WHEN b.asset='sealed'
       AND public.normalize_pokemon_market_explorer_search_text_v2(b.name)=(SELECT q FROM norm)
        THEN 120000
      WHEN b.asset='sealed'
       AND public.normalize_pokemon_market_explorer_search_text_v2(b.name)
           LIKE (SELECT q FROM norm)||'%'
        THEN 110000
      WHEN b.asset='sealed'
       AND pg_catalog.strpos(
             ' '||public.normalize_pokemon_market_explorer_search_text_v2(b.name)||' ',
             ' '||(SELECT q FROM norm)||' '
           )>0
        THEN 105000
      ELSE b.relevance_score
    END AS refined_relevance
  FROM base b
  CROSS JOIN asset_dates ad
  LEFT JOIN public.pokemon_market_explorer_card_current_metadata cm
    ON b.asset='cards' AND cm.card_variant_id=b.instrument_id
  LEFT JOIN public.pokemon_market_explorer_card_daily_states_v2_shadow cd
    ON b.asset='cards'
   AND cd.card_variant_id=b.instrument_id
   AND cd.market_date=ad.cards_date
   AND cd.market_price>0
  LEFT JOIN public.card_variants cv ON cv.id=cm.card_variant_id
  LEFT JOIN public.pokemon_canonical_cards cc ON cc.id=cm.canonical_card_id
  LEFT JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 sm
    ON b.asset='sealed'
   AND nullif(sm.sealed_product_id,'')::uuid=b.instrument_id
   AND sm.latest_market_date=ad.sealed_date
   AND sm.latest_market_price>0
)
SELECT
  e.asset,e.instrument_id,e.name,e.set_id,e.set_name,e.image_url,
  e.market_price,e.market_date,e.card_variant_id,e.canonical_card_id,
  e.card_number,e.rarity,e.edition,e.printing_type,e.special_type,
  e.sealed_product_id,e.product_family,e.variant_label,e.is_bulk_container,
  e.refined_match_kind,e.refined_relevance
FROM enriched e
WHERE e.market_price>0
ORDER BY e.refined_relevance DESC,
         pg_catalog.lower(e.name),
         pg_catalog.lower(coalesce(e.set_name,'')),
         e.instrument_id
LIMIT least(greatest(coalesce(p_limit,20),1),50)
$function$;

REVOKE ALL ON FUNCTION public.search_pokemon_market_explorer_leaf_instruments_v3(text,text,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.search_pokemon_market_explorer_leaf_instruments_v3(text,text,integer)
TO service_role;

-- ---------------------------------------------------------------------------
-- C. Approved Sealed Quick Market registry.
-- ---------------------------------------------------------------------------

UPDATE public.pokemon_market_explorer_sealed_quick_registry_v1
SET status='REJECTED',updated_at=clock_timestamp()
WHERE status='PROPOSED';

INSERT INTO public.pokemon_market_explorer_sealed_quick_registry_v1(
  quick_key,label,status,definition,research_basis,approved_at,updated_at
)
VALUES
(
  'obtainable','Obtainable','APPROVED',
  '{"dimension":"price","maxExclusive":100,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"product-approved canonical sealed threshold","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
),
(
  'intermediate','Intermediate','APPROVED',
  '{"dimension":"price","minInclusive":100,"maxExclusive":500,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"product-approved canonical sealed threshold","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
),
(
  'premium','Premium','APPROVED',
  '{"dimension":"price","minInclusive":500,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"product-approved canonical sealed threshold","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
),
(
  'new-releases','New Releases','APPROVED',
  '{"dimension":"releaseAgeDays","minInclusive":0,"maxInclusive":180,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"canonical RELEASE_AGE_BOUNDS_DAYS","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
),
(
  'established','Established','APPROVED',
  '{"dimension":"releaseAgeDays","minInclusive":731,"maxInclusive":1825,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"canonical RELEASE_AGE_BOUNDS_DAYS","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
),
(
  'global-top10','Global Top 10','APPROVED',
  '{"dimension":"rank","topN":10,"rankBy":"marketPrice","filterFirst":true,"dateSpecificMembership":true,"bulkContainersExcluded":true}'::jsonb,
  '{"basis":"product-approved dynamic sealed ranking","version":"sealed-quick-v1"}'::jsonb,
  clock_timestamp(),clock_timestamp()
)
ON CONFLICT(quick_key) DO UPDATE
SET label=excluded.label,status='APPROVED',definition=excluded.definition,
    research_basis=excluded.research_basis,approved_at=excluded.approved_at,
    updated_at=excluded.updated_at;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v1(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '90s'
SET lock_timeout = '2s'
SET work_mem = '64MB'
SET jit = 'off'
AS $function$
DECLARE
  v_markets integer;
  v_history integer;
  v_constituents integer;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'SEALED_QUICK_ARGUMENTS_REQUIRED';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_generations_v2 g
    WHERE g.generation_id=p_generation_id
      AND g.market_date=p_market_date
      AND g.state IN ('BUILDING','BUILT')
  ) THEN
    RAISE EXCEPTION 'SEALED_QUICK_GENERATION_NOT_BUILDABLE';
  END IF;

  DELETE FROM public.pokemon_market_explorer_surface_constituents_v2
  WHERE generation_id=p_generation_id AND market_key LIKE 'sealed-quick:%';
  DELETE FROM public.pokemon_market_explorer_surface_constituent_totals_v2
  WHERE generation_id=p_generation_id AND market_key LIKE 'sealed-quick:%';
  DELETE FROM public.pokemon_market_explorer_surface_history_v2
  WHERE generation_id=p_generation_id AND market_key LIKE 'sealed-quick:%';
  DELETE FROM public.pokemon_market_explorer_surface_directory_v2
  WHERE generation_id=p_generation_id AND market_key LIKE 'sealed-quick:%';

  DROP TABLE IF EXISTS pg_temp._mx_sealed_quick_dense;
  CREATE TEMP TABLE _mx_sealed_quick_dense ON COMMIT DROP AS
  WITH intervals AS (
    SELECT d.*,
      lead(d.market_date,1,p_market_date+1) OVER(
        PARTITION BY d.sealed_product_id ORDER BY d.market_date
      ) next_date
    FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date<=p_market_date
      AND d.market_price>0
  )
  SELECT
    i.sealed_product_id,
    g.day::date AS market_date,
    i.market_price,
    i.set_id,
    i.era_id,
    i.product_family,
    s.release_date,
    (g.day::date-s.release_date)::integer AS age_days
  FROM intervals i
  CROSS JOIN LATERAL pg_catalog.generate_series(
    i.market_date,
    least(p_market_date,i.next_date-1),
    interval '1 day'
  ) g(day)
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 m
    ON m.sealed_product_id=i.sealed_product_id
   AND NOT coalesce(m.is_bulk_container,false)
  LEFT JOIN public.sets s ON s.id=i.set_id;

  CREATE INDEX ON _mx_sealed_quick_dense(market_date,sealed_product_id);
  CREATE INDEX ON _mx_sealed_quick_dense(market_date,market_price,sealed_product_id);
  ANALYZE _mx_sealed_quick_dense;

  DROP TABLE IF EXISTS pg_temp._mx_sealed_quick_members;
  CREATE TEMP TABLE _mx_sealed_quick_members ON COMMIT DROP AS
  WITH ranked AS (
    SELECT d.*,
      row_number() OVER(
        PARTITION BY d.market_date
        ORDER BY d.market_price DESC,d.sealed_product_id
      )::integer AS price_rank
    FROM _mx_sealed_quick_dense d
  )
  SELECT 'sealed-quick:obtainable'::text market_key,
         d.sealed_product_id,d.market_date,d.market_price,
         d.set_id,d.era_id,d.product_family
  FROM _mx_sealed_quick_dense d
  WHERE d.market_price<100
  UNION ALL
  SELECT 'sealed-quick:intermediate',d.sealed_product_id,d.market_date,d.market_price,
         d.set_id,d.era_id,d.product_family
  FROM _mx_sealed_quick_dense d
  WHERE d.market_price>=100 AND d.market_price<500
  UNION ALL
  SELECT 'sealed-quick:premium',d.sealed_product_id,d.market_date,d.market_price,
         d.set_id,d.era_id,d.product_family
  FROM _mx_sealed_quick_dense d
  WHERE d.market_price>=500
  UNION ALL
  SELECT 'sealed-quick:new-releases',d.sealed_product_id,d.market_date,d.market_price,
         d.set_id,d.era_id,d.product_family
  FROM _mx_sealed_quick_dense d
  WHERE d.age_days BETWEEN 0 AND 180
  UNION ALL
  SELECT 'sealed-quick:established',d.sealed_product_id,d.market_date,d.market_price,
         d.set_id,d.era_id,d.product_family
  FROM _mx_sealed_quick_dense d
  WHERE d.age_days BETWEEN 731 AND 1825
  UNION ALL
  SELECT 'sealed-quick:global-top10',r.sealed_product_id,r.market_date,r.market_price,
         r.set_id,r.era_id,r.product_family
  FROM ranked r
  WHERE r.price_rank<=10;

  CREATE INDEX ON _mx_sealed_quick_members(market_key,market_date,sealed_product_id);
  ANALYZE _mx_sealed_quick_members;

  INSERT INTO public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,constituent_count,composition_kind,availability,
    definition_version,screen_group,screen_eligible,metadata,comparison_as_of
  )
  SELECT
    p_generation_id,
    'sealed-quick:'||q.quick_key,
    'sealed','quick',q.label,q.label,'normalized_sealed_daily_v1',
    q.quick_key,p_market_date,coalesce(cs.n,0),'index_and_composition',
    CASE WHEN coalesce(cs.n,0)>0 THEN 'available' ELSE 'empty' END,
    'sealed-quick-v1','sealed',true,
    jsonb_build_object(
      'quickKey',q.quick_key,
      'definition',q.definition,
      'bulkContainersExcluded',true,
      'membershipDateSpecific',true
    ),
    p_market_date
  FROM public.pokemon_market_explorer_sealed_quick_registry_v1 q
  LEFT JOIN (
    SELECT market_key,count(*)::integer n
    FROM _mx_sealed_quick_members
    WHERE market_date=p_market_date
    GROUP BY market_key
  ) cs ON cs.market_key='sealed-quick:'||q.quick_key
  WHERE q.status='APPROVED'
  ON CONFLICT(generation_id,market_key) DO UPDATE
  SET constituent_count=excluded.constituent_count,
      availability=excluded.availability,
      metadata=excluded.metadata,
      comparison_as_of=excluded.comparison_as_of;
  GET DIAGNOSTICS v_markets=ROW_COUNT;

  WITH common AS (
    SELECT
      cur.market_key,
      cur.market_date,
      count(*)::integer AS constituent_count,
      sum(cur.market_price)::numeric AS basket_value,
      coalesce(sum(cur.market_price) FILTER(WHERE prev.sealed_product_id IS NOT NULL),0)::numeric AS current_common,
      coalesce(sum(prev.market_price) FILTER(WHERE prev.sealed_product_id IS NOT NULL),0)::numeric AS previous_common
    FROM _mx_sealed_quick_members cur
    LEFT JOIN _mx_sealed_quick_members prev
      ON prev.market_key=cur.market_key
     AND prev.sealed_product_id=cur.sealed_product_id
     AND prev.market_date=cur.market_date-1
    GROUP BY cur.market_key,cur.market_date
  ),
  indexed AS (
    SELECT c.*,
      100.0*exp(sum(ln(
        CASE WHEN c.previous_common>0 THEN c.current_common/c.previous_common ELSE 1.0 END
      )) OVER(
        PARTITION BY c.market_key
        ORDER BY c.market_date
        ROWS UNBOUNDED PRECEDING
      ))::numeric AS index_value
    FROM common c
  )
  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,
    constituent_count,chain_segment_id
  )
  SELECT p_generation_id,market_key,market_date,index_value,basket_value,
         constituent_count,0
  FROM indexed
  WHERE market_date<=p_market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability
  )
  SELECT p_generation_id,m.market_key,'sealed',count(*)::integer,
         CASE WHEN count(*)>0 THEN 'available' ELSE 'empty' END
  FROM _mx_sealed_quick_members m
  WHERE m.market_date=p_market_date
  GROUP BY m.market_key;
  
  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,
    market_price,price_as_of,item
  )
  SELECT
    p_generation_id,
    m.market_key,
    row_number() OVER(
      PARTITION BY m.market_key
      ORDER BY m.market_price DESC,m.sealed_product_id
    )::integer,
    m.sealed_product_id,
    'sealed',
    m.set_id,
    m.market_price,
    p_market_date,
    jsonb_build_object(
      'asset','sealed',
      'instrumentId',m.sealed_product_id,
      'sealedProductId',m.sealed_product_id,
      'setId',meta.set_id,
      'setName',meta.set_name,
      'name',meta.name,
      'productName',meta.name,
      'variantLabel',meta.variant_label,
      'productFamily',meta.product_family,
      'productFamilyLabel',meta.product_family_label,
      'marketPrice',m.market_price,
      'priceAsOf',p_market_date,
      'imageUrl',coalesce(meta.image_small_url,meta.image_large_url),
      'imageSmallUrl',meta.image_small_url,
      'imageLargeUrl',meta.image_large_url,
      'isBulkContainer',false
    )
  FROM _mx_sealed_quick_members m
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    ON meta.sealed_product_id=m.sealed_product_id
  WHERE m.market_date=p_market_date;
  GET DIAGNOSTICS v_constituents=ROW_COUNT;

  RETURN jsonb_build_object(
    'markets',v_markets,
    'historyRows',v_history,
    'constituentRows',v_constituents
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v1(uuid,date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v1(uuid,date)
TO service_role;

-- ---------------------------------------------------------------------------
-- D. Build/validate/promote wrappers enforce one generation watermark.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.build_pokemon_market_explorer_surface_candidate_v3(
  p_base_generation_id uuid,
  p_market_date date,
  p_raw_methodology_version text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '300s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_promotable date;
  v_build jsonb;
  v_quick jsonb;
  v_metrics jsonb;
  v_generation uuid;
BEGIN
  v_promotable:=public.get_pokemon_market_explorer_promotable_date_v1();
  IF v_promotable IS NULL OR p_market_date IS DISTINCT FROM v_promotable THEN
    RAISE EXCEPTION 'EXPLORER_TARGET_NOT_PROMOTABLE: target %, latest complete %',
      coalesce(p_market_date::text,'null'),coalesce(v_promotable::text,'null');
  END IF;

  v_build:=public.build_pokemon_market_explorer_surface_candidate_v2(
    p_base_generation_id,p_market_date,p_raw_methodology_version
  );
  v_generation:=nullif(v_build->>'generationId','')::uuid;
  IF v_generation IS NULL THEN
    RAISE EXCEPTION 'EXPLORER_V2_BUILD_DID_NOT_RETURN_GENERATION';
  END IF;

  UPDATE public.pokemon_market_explorer_surface_generations_v2
  SET comparison_as_of=p_market_date
  WHERE generation_id=v_generation;

  UPDATE public.pokemon_market_explorer_surface_directory_v2
  SET comparison_as_of=p_market_date
  WHERE generation_id=v_generation;

  v_quick:=public.stage_pokemon_market_explorer_sealed_quick_markets_v1(
    v_generation,p_market_date
  );

  v_metrics:=public.finalize_pokemon_market_explorer_surface_metrics_v2(
    v_generation,p_market_date
  );

  UPDATE public.pokemon_market_explorer_surface_directory_v2
  SET comparison_as_of=p_market_date
  WHERE generation_id=v_generation;

  RETURN v_build||jsonb_build_object(
    'comparisonAsOf',p_market_date,
    'sealedQuick',v_quick,
    'finalMetrics',v_metrics
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.build_pokemon_market_explorer_surface_candidate_v3(uuid,date,text)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.build_pokemon_market_explorer_surface_candidate_v3(uuid,date,text)
TO service_role;

CREATE OR REPLACE FUNCTION public.validate_pokemon_market_explorer_surface_candidate_v3(
  p_generation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '60s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_base jsonb;
  v_market_date date;
  v_state text;
  v_issues jsonb:='[]'::jsonb;
  v_n integer;
BEGIN
  v_base:=public.validate_pokemon_market_explorer_surface_candidate_v2(p_generation_id);

  SELECT g.market_date,g.state
  INTO v_market_date,v_state
  FROM public.pokemon_market_explorer_surface_generations_v2 g
  WHERE g.generation_id=p_generation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_NOT_FOUND';
  END IF;

  IF v_state='REJECTED' THEN
    RETURN v_base||jsonb_build_object('comparisonIssues','[]'::jsonb);
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.comparison_as_of IS DISTINCT FROM v_market_date;
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','COMPARISON_WATERMARK_MISMATCH','count',v_n)
    );
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.availability='available'
    AND d.history_available
    AND d.history_end_date IS DISTINCT FROM v_market_date;
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','AVAILABLE_HISTORY_NOT_AT_WATERMARK','count',v_n)
    );
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.market_key LIKE 'sealed-quick:%';
  IF v_n<>6 THEN
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_QUICK_MARKET_COUNT','count',v_n)
    );
  END IF;

  SELECT count(*)::integer INTO v_n
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  WHERE c.generation_id=p_generation_id
    AND c.market_key LIKE 'sealed-quick:%'
    AND coalesce((c.item->>'isBulkContainer')::boolean,false);
  IF v_n>0 THEN
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_QUICK_CONTAINS_BULK','count',v_n)
    );
  END IF;

  IF coalesce((
    SELECT t.total_count
    FROM public.pokemon_market_explorer_surface_constituent_totals_v2 t
    WHERE t.generation_id=p_generation_id
      AND t.market_key='sealed-quick:global-top10'
  ),0)<>10 THEN
    v_issues:=v_issues||jsonb_build_array(
      jsonb_build_object('code','SEALED_GLOBAL_TOP10_NOT_TEN')
    );
  END IF;

  UPDATE public.pokemon_market_explorer_surface_generations_v2
  SET state=CASE
        WHEN jsonb_array_length(v_issues)=0 THEN 'VALIDATED'
        ELSE 'REJECTED'
      END,
      comparison_as_of=v_market_date,
      validated_at=clock_timestamp(),
      diagnostics=diagnostics||jsonb_build_object(
        'comparisonAsOf',v_market_date,
        'comparisonIssues',v_issues
      )
  WHERE generation_id=p_generation_id;

  RETURN jsonb_build_object(
    'generationId',p_generation_id,
    'state',CASE WHEN jsonb_array_length(v_issues)=0 THEN 'VALIDATED' ELSE 'REJECTED' END,
    'comparisonAsOf',v_market_date,
    'baseValidation',v_base,
    'issues',v_issues
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.validate_pokemon_market_explorer_surface_candidate_v3(uuid)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.validate_pokemon_market_explorer_surface_candidate_v3(uuid)
TO service_role;

CREATE OR REPLACE FUNCTION public.promote_pokemon_market_explorer_surface_v3(
  p_generation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '15s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_target date;
  v_promotable date;
  v_state text;
  v_result jsonb;
BEGIN
  SELECT comparison_as_of,state
  INTO v_target,v_state
  FROM public.pokemon_market_explorer_surface_generations_v2
  WHERE generation_id=p_generation_id
  FOR UPDATE;

  IF NOT FOUND OR v_state<>'VALIDATED' THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_NOT_VALIDATED';
  END IF;

  v_promotable:=public.get_pokemon_market_explorer_promotable_date_v1();
  IF v_target IS NULL OR v_target IS DISTINCT FROM v_promotable THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_STALE_AT_PROMOTION: generation %, current %',
      coalesce(v_target::text,'null'),coalesce(v_promotable::text,'null');
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_directory_v2 d
    WHERE d.generation_id=p_generation_id
      AND d.comparison_as_of IS DISTINCT FROM v_target
  ) THEN
    RAISE EXCEPTION 'SURFACE_DIRECTORY_WATERMARK_MISMATCH';
  END IF;

  v_result:=public.promote_pokemon_market_explorer_surface_v2(p_generation_id);
  RETURN v_result||jsonb_build_object('comparisonAsOf',v_target);
END;
$function$;

REVOKE ALL ON FUNCTION public.promote_pokemon_market_explorer_surface_v3(uuid)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.promote_pokemon_market_explorer_surface_v3(uuid)
TO service_role;

-- ---------------------------------------------------------------------------
-- E. Generation-pinned analytical screens.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_surface_screen_v2(
  p_screen_key text,
  p_asset text DEFAULT NULL,
  p_limit integer DEFAULT 25,
  p_generation_id uuid DEFAULT NULL
)
RETURNS TABLE(
  rank integer,
  market_key text,
  label text,
  asset text,
  market_type text,
  metric_value numeric,
  comparison_as_of date,
  generation_id uuid,
  current_drawdown_pct numeric,
  constituent_count integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '2s'
AS $function$
DECLARE
  v_serving uuid;
  v_watermark date;
BEGIN
  IF p_limit IS NULL OR p_limit<1 OR p_limit>25 THEN
    RAISE EXCEPTION 'screen limit must be 1..25';
  END IF;
  IF p_asset IS NOT NULL AND p_asset NOT IN ('cards','sealed') THEN
    RAISE EXCEPTION 'unsupported screen asset';
  END IF;
  IF p_screen_key NOT IN (
    'top-performers','worst-performers',
    'rarity-leaders','sealed-format-leaders',
    'momentum-leaders','largest-drawdowns'
  ) THEN
    RAISE EXCEPTION 'unsupported surface screen';
  END IF;

  SELECT s.generation_id,g.comparison_as_of
  INTO v_serving,v_watermark
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  JOIN public.pokemon_market_explorer_surface_generations_v2 g
    ON g.generation_id=s.generation_id
  WHERE s.singleton=1;

  IF v_serving IS NULL THEN
    RAISE EXCEPTION 'SURFACE_SERVING_GENERATION_MISSING';
  END IF;
  IF p_generation_id IS NOT NULL AND p_generation_id<>v_serving THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_MISMATCH';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_directory_v2 d
    WHERE d.generation_id=v_serving
      AND d.comparison_as_of IS DISTINCT FROM v_watermark
  ) THEN
    RAISE EXCEPTION 'SURFACE_SCREEN_WATERMARK_MISMATCH';
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT d.*,
      CASE
        WHEN p_screen_key IN ('top-performers','worst-performers') THEN d.return_7d_pct
        WHEN p_screen_key IN ('rarity-leaders','sealed-format-leaders','momentum-leaders') THEN d.return_30d_pct
        WHEN p_screen_key='largest-drawdowns' THEN d.current_drawdown_pct
      END AS metric
    FROM public.pokemon_market_explorer_surface_directory_v2 d
    WHERE d.generation_id=v_serving
      AND d.availability='available'
      AND d.history_available
      AND d.comparison_as_of=v_watermark
      AND (p_asset IS NULL OR d.asset=p_asset)
      AND (
        p_screen_key IN ('top-performers','worst-performers')
        OR d.screen_eligible
      )
      AND (
        p_screen_key<>'rarity-leaders'
        OR (d.asset='cards' AND d.scope_kind='rarity')
      )
      AND (
        p_screen_key<>'sealed-format-leaders'
        OR (d.asset='sealed' AND d.scope_kind='type')
      )
  ),
  ranked AS (
    SELECT c.*,
      row_number() OVER(
        ORDER BY
          CASE WHEN p_screen_key IN ('worst-performers','largest-drawdowns')
            THEN c.metric END ASC NULLS LAST,
          CASE WHEN p_screen_key NOT IN ('worst-performers','largest-drawdowns')
            THEN c.metric END DESC NULLS LAST,
          c.market_key
      )::integer AS screen_rank
    FROM candidates c
    WHERE c.metric IS NOT NULL
  )
  SELECT r.screen_rank,r.market_key,r.label,r.asset,r.scope_kind,
         r.metric,r.comparison_as_of,r.generation_id,
         r.current_drawdown_pct,r.constituent_count
  FROM ranked r
  WHERE r.screen_rank<=p_limit
  ORDER BY r.screen_rank;
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_surface_screen_v2(text,text,integer,uuid)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_surface_screen_v2(text,text,integer,uuid)
TO service_role;

COMMIT;
