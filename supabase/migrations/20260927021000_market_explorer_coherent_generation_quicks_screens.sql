BEGIN;

-- Market Explorer coherent-generation correction pass.
-- Additive forward migration: one comparison watermark per immutable V2 generation,
-- asset-date-safe leaf search, six approved Sealed Quick Markets, prepared Top/Worst
-- screens, and fail-closed promotion gates.

ALTER TABLE public.pokemon_market_explorer_surface_generations_v2
  ADD COLUMN IF NOT EXISTS comparison_as_of date;

ALTER TABLE public.pokemon_market_explorer_surface_directory_v2
  ADD COLUMN IF NOT EXISTS comparison_as_of date;

CREATE INDEX IF NOT EXISTS pokemon_market_explorer_surface_directory_v2_generation_comparison_idx
  ON public.pokemon_market_explorer_surface_directory_v2(generation_id,comparison_as_of,asset,scope_kind);

CREATE OR REPLACE FUNCTION public.market_explorer_surface_generation_watermark_trigger_v2()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path=''
AS $function$
BEGIN
  NEW.comparison_as_of := coalesce(NEW.comparison_as_of,NEW.market_date);
  IF NEW.comparison_as_of IS DISTINCT FROM NEW.market_date THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_COMPARISON_DATE_MUST_EQUAL_MARKET_DATE';
  END IF;
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS pokemon_market_explorer_surface_generation_watermark_v2
  ON public.pokemon_market_explorer_surface_generations_v2;
CREATE TRIGGER pokemon_market_explorer_surface_generation_watermark_v2
BEFORE INSERT OR UPDATE OF market_date,comparison_as_of
ON public.pokemon_market_explorer_surface_generations_v2
FOR EACH ROW EXECUTE FUNCTION public.market_explorer_surface_generation_watermark_trigger_v2();

CREATE OR REPLACE FUNCTION public.market_explorer_surface_directory_watermark_trigger_v2()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path=''
AS $function$
DECLARE v_date date;
BEGIN
  SELECT g.comparison_as_of INTO v_date
  FROM public.pokemon_market_explorer_surface_generations_v2 g
  WHERE g.generation_id=NEW.generation_id;
  IF v_date IS NULL THEN
    RAISE EXCEPTION 'SURFACE_DIRECTORY_GENERATION_WATERMARK_MISSING';
  END IF;
  NEW.comparison_as_of := v_date;
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS pokemon_market_explorer_surface_directory_watermark_v2
  ON public.pokemon_market_explorer_surface_directory_v2;
CREATE TRIGGER pokemon_market_explorer_surface_directory_watermark_v2
BEFORE INSERT OR UPDATE OF generation_id,comparison_as_of
ON public.pokemon_market_explorer_surface_directory_v2
FOR EACH ROW EXECUTE FUNCTION public.market_explorer_surface_directory_watermark_trigger_v2();

REVOKE ALL ON FUNCTION public.market_explorer_surface_generation_watermark_trigger_v2()
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.market_explorer_surface_directory_watermark_trigger_v2()
FROM PUBLIC,anon,authenticated;

-- --------------------------------------------------------------------------
-- Asset-date-safe instrument search.
-- Cards resolve against card-daily authority; Sealed resolves against compact
-- normalized sealed current metadata. No global Market Date can outrun an asset.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text DEFAULT 'all',
  p_limit integer DEFAULT 20
)
RETURNS TABLE(
  asset text,instrument_id uuid,name text,set_id uuid,set_name text,image_url text,
  card_number text,rarity text,edition text,printing_type text,special_type text,
  product_family text,variant_label text,match_kind text,relevance_score integer,
  name_similarity real
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='1s'
SET work_mem='16MB'
AS $function$
WITH authority AS MATERIALIZED (
  SELECT
    (SELECT max(d.market_date)
     FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
     WHERE d.market_price>0) AS card_date,
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
  FROM base b CROSS JOIN authority a
  WHERE (
    b.asset='cards'
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
      WHERE d.card_variant_id=b.instrument_id
        AND d.market_date=a.card_date
        AND d.market_price>0
    )
  ) OR (
    b.asset='sealed'
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
      WHERE m.sealed_product_id=b.instrument_id::text
        AND m.latest_market_date=a.sealed_date
        AND m.latest_market_price>0
    )
  )
)
SELECT
  e.asset,e.instrument_id,e.name,e.set_id,e.set_name,e.image_url,
  e.card_number,e.rarity,e.edition,e.printing_type,e.special_type,
  e.product_family,e.variant_label,e.match_kind,e.relevance_score,e.name_similarity
FROM eligible e
ORDER BY
  e.relevance_score DESC,
  CASE WHEN e.match_kind='fuzzy_name' THEN e.name_similarity ELSE 0::real END DESC,
  pg_catalog.lower(e.name),
  pg_catalog.lower(coalesce(e.set_name,'')),
  e.asset,e.instrument_id
LIMIT least(greatest(coalesce(p_limit,20),1),50);
$function$;

REVOKE ALL ON FUNCTION public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
TO service_role;

CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_leaves_v1(
  p_asset text,
  p_query text,
  p_limit integer DEFAULT 20
)
RETURNS TABLE(
  asset text,
  instrument_id text,
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
  sealed_product_id text,
  product_family text,
  variant_label text,
  is_bulk_container boolean,
  relevance_score integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='1s'
SET work_mem='16MB'
AS $function$
DECLARE
  v_asset text:=lower(trim(coalesce(p_asset,'')));
  v_q text:=public.normalize_pokemon_market_explorer_search_text_v2(p_query);
  v_alt text;
  v_date date;
BEGIN
  IF v_asset NOT IN ('cards','sealed','graded') THEN
    RAISE EXCEPTION 'LEAF_SEARCH_ASSET_INVALID';
  END IF;
  IF v_q IS NULL OR length(v_q)<2 THEN
    RETURN;
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>50 THEN
    RAISE EXCEPTION 'LEAF_SEARCH_LIMIT_INVALID';
  END IF;

  IF v_asset='graded' THEN
    RETURN;
  END IF;

  IF v_asset='cards' THEN
    SELECT max(d.market_date) INTO v_date
    FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
    WHERE d.market_price>0;

    RETURN QUERY
    SELECT
      'cards'::text,
      s.instrument_id::text,
      s.name,
      s.set_id,
      s.set_name,
      s.image_url,
      d.market_price,
      d.market_date,
      s.instrument_id,
      m.canonical_card_id,
      s.card_number,
      s.rarity,
      s.edition,
      s.printing_type,
      s.special_type,
      null::text,
      null::text,
      null::text,
      false,
      s.relevance_score
    FROM public.search_pokemon_market_explorer_instruments_v2(
      p_query,'cards',least(50,greatest(p_limit,20))
    ) s
    JOIN public.pokemon_market_explorer_card_daily_states_v2_shadow d
      ON d.card_variant_id=s.instrument_id
     AND d.market_date=v_date
     AND d.market_price>0
    JOIN public.pokemon_market_explorer_card_current_metadata m
      ON m.card_variant_id=s.instrument_id
    WHERE s.asset='cards'
    ORDER BY s.relevance_score DESC,lower(s.name),s.instrument_id
    LIMIT p_limit;
    RETURN;
  END IF;

  SELECT max(m.latest_market_date) INTO v_date
  FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
  WHERE m.latest_market_price>0;

  v_alt:=CASE
    WHEN v_q ~ '(^| )three( |$)' THEN regexp_replace(v_q,'(^| )three( |$)','\\13\\2','g')
    WHEN v_q ~ '(^| )3( |$)' THEN regexp_replace(v_q,'(^| )3( |$)','\\1three\\2','g')
    ELSE v_q
  END;

  RETURN QUERY
  WITH candidates AS MATERIALIZED (
    SELECT
      m.*,
      public.normalize_pokemon_market_explorer_search_text_v2(m.name) AS nname,
      greatest(
        extensions.similarity(coalesce(m.search_text,''),v_q),
        extensions.similarity(coalesce(m.search_text,''),v_alt)
      ) AS sim
    FROM public.pokemon_market_explorer_sealed_current_metadata_v1 m
    WHERE m.latest_market_date=v_date
      AND m.latest_market_price>0
      AND (
        public.normalize_pokemon_market_explorer_search_text_v2(m.name) IN (v_q,v_alt)
        OR public.normalize_pokemon_market_explorer_search_text_v2(m.name) LIKE v_q||'%'
        OR public.normalize_pokemon_market_explorer_search_text_v2(m.name) LIKE v_alt||'%'
        OR public.normalize_pokemon_market_explorer_search_text_v2(m.name) LIKE '%'||v_q||'%'
        OR public.normalize_pokemon_market_explorer_search_text_v2(m.name) LIKE '%'||v_alt||'%'
        OR pg_catalog.to_tsvector('simple',coalesce(m.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_q)
        OR pg_catalog.to_tsvector('simple',coalesce(m.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_alt)
        OR extensions.similarity(coalesce(m.search_text,''),v_q)>=0.20
        OR extensions.similarity(coalesce(m.search_text,''),v_alt)>=0.20
      )
  ),
  ranked AS (
    SELECT c.*,
      CASE
        WHEN c.nname IN (v_q,v_alt) THEN 1000
        WHEN c.nname LIKE v_q||'%' OR c.nname LIKE v_alt||'%' THEN 950
        WHEN c.nname LIKE '%'||v_q||'%' OR c.nname LIKE '%'||v_alt||'%' THEN 900
        WHEN pg_catalog.to_tsvector('simple',c.nname) @@ pg_catalog.plainto_tsquery('simple',v_q)
          OR pg_catalog.to_tsvector('simple',c.nname) @@ pg_catalog.plainto_tsquery('simple',v_alt) THEN 850
        WHEN pg_catalog.to_tsvector('simple',coalesce(c.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_q)
          OR pg_catalog.to_tsvector('simple',coalesce(c.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_alt) THEN 800
        ELSE 700+least(99,(c.sim*100)::integer)
      END AS score
    FROM candidates c
  )
  SELECT
    'sealed'::text,
    r.sealed_product_id,
    r.name,
    r.set_id,
    r.set_name,
    coalesce(r.image_small_url,r.image_large_url),
    r.latest_market_price,
    r.latest_market_date,
    null::uuid,
    null::uuid,
    null::text,
    null::text,
    null::text,
    null::text,
    null::text,
    r.sealed_product_id,
    r.product_family,
    r.variant_label,
    r.is_bulk_container,
    r.score
  FROM ranked r
  ORDER BY r.score DESC,r.sim DESC,lower(r.name),r.sealed_product_id
  LIMIT p_limit;
END;
$function$;

REVOKE ALL ON FUNCTION public.search_pokemon_market_explorer_leaves_v1(text,text,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.search_pokemon_market_explorer_leaves_v1(text,text,integer)
TO service_role;

-- --------------------------------------------------------------------------
-- Approved Sealed Quick Market identities.
-- Old proposals remain auditable but are rejected/superseded.
-- --------------------------------------------------------------------------
UPDATE public.pokemon_market_explorer_sealed_quick_registry_v1
SET status='REJECTED',
    definition=definition||jsonb_build_object('supersededBy','sealed-quick-contract-v1')
WHERE quick_key NOT IN (
  'sealed-quick:obtainable','sealed-quick:intermediate','sealed-quick:premium',
  'sealed-quick:new-releases','sealed-quick:established','sealed-quick:global-top10'
);

INSERT INTO public.pokemon_market_explorer_sealed_quick_registry_v1(
  quick_key,label,definition,status
) VALUES
('sealed-quick:obtainable','Obtainable',
 '{"kind":"price","minExclusive":null,"maxExclusive":100,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED'),
('sealed-quick:intermediate','Intermediate',
 '{"kind":"price","minInclusive":100,"maxExclusive":500,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED'),
('sealed-quick:premium','Premium',
 '{"kind":"price","minInclusive":500,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED'),
('sealed-quick:new-releases','New Releases',
 '{"kind":"releaseAge","minDaysInclusive":0,"maxDaysInclusive":180,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED'),
('sealed-quick:established','Established',
 '{"kind":"releaseAge","minDaysExclusive":730,"maxDaysInclusive":1825,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED'),
('sealed-quick:global-top10','Global Top 10',
 '{"kind":"rankedPrice","topN":10,"dynamicDailyMembership":true,"excludeBulk":true,"version":"sealed-quick-contract-v1"}','APPROVED')
ON CONFLICT(quick_key) DO UPDATE
SET label=excluded.label,definition=excluded.definition,status='APPROVED';

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v2(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='120s'
SET lock_timeout='2s'
SET work_mem='64MB'
AS $function$
DECLARE
  v_markets integer;
  v_history integer;
  v_constituents integer;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'SEALED_QUICK_STAGE_ARGUMENTS_REQUIRED';
  END IF;

  DROP TABLE IF EXISTS pg_temp._mx_quick_dense;
  CREATE TEMP TABLE _mx_quick_dense ON COMMIT DROP AS
  WITH intervals AS (
    SELECT d.*,
      lead(d.market_date,1,p_market_date+1) over(
        partition by d.sealed_product_id order by d.market_date
      ) next_date
    FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date<=p_market_date
  )
  SELECT
    i.sealed_product_id,
    g.day::date market_date,
    i.market_price,
    i.set_id,
    i.era_id,
    i.product_family,
    coalesce(meta.is_bulk_container,false) is_bulk_container,
    s.release_date
  FROM intervals i
  CROSS JOIN LATERAL generate_series(
    i.market_date,least(p_market_date,i.next_date-1),interval '1 day'
  ) g(day)
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    ON meta.sealed_product_id=i.sealed_product_id
  LEFT JOIN public.sets s ON s.id=i.set_id
  WHERE i.market_price>0;

  CREATE INDEX ON _mx_quick_dense(market_date,sealed_product_id);
  ANALYZE _mx_quick_dense;

  DROP TABLE IF EXISTS pg_temp._mx_quick_members;
  CREATE TEMP TABLE _mx_quick_members ON COMMIT DROP AS
  WITH nonbulk AS MATERIALIZED (
    SELECT * FROM _mx_quick_dense WHERE NOT is_bulk_container
  ),
  ordinary AS (
    SELECT 'sealed-quick:obtainable'::text market_key,d.*
    FROM nonbulk d WHERE d.market_price<100
    UNION ALL
    SELECT 'sealed-quick:intermediate',d.*
    FROM nonbulk d WHERE d.market_price>=100 AND d.market_price<500
    UNION ALL
    SELECT 'sealed-quick:premium',d.*
    FROM nonbulk d WHERE d.market_price>=500
    UNION ALL
    SELECT 'sealed-quick:new-releases',d.*
    FROM nonbulk d
    WHERE d.release_date IS NOT NULL
      AND d.market_date-d.release_date BETWEEN 0 AND 180
    UNION ALL
    SELECT 'sealed-quick:established',d.*
    FROM nonbulk d
    WHERE d.release_date IS NOT NULL
      AND d.market_date-d.release_date>730
      AND d.market_date-d.release_date<=1825
  ),
  top10 AS (
    SELECT 'sealed-quick:global-top10'::text market_key,x.*
    FROM (
      SELECT d.*,
        row_number() over(
          partition by d.market_date
          order by d.market_price desc,d.sealed_product_id
        ) rn
      FROM nonbulk d
    ) x
    WHERE x.rn<=10
  )
  SELECT market_key,sealed_product_id,market_date,market_price,set_id,era_id,product_family
  FROM ordinary
  UNION ALL
  SELECT market_key,sealed_product_id,market_date,market_price,set_id,era_id,product_family
  FROM top10;

  CREATE INDEX ON _mx_quick_members(market_key,market_date,sealed_product_id);
  ANALYZE _mx_quick_members;

  INSERT INTO public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,constituent_count,composition_kind,availability,
    definition_version,screen_group,screen_eligible,metadata
  )
  SELECT
    p_generation_id,r.quick_key,'sealed','quick',r.label,r.label,
    'normalized_sealed_daily_v1',r.quick_key,p_market_date,
    count(m.sealed_product_id)::integer,'index_and_composition',
    case when count(m.sealed_product_id)>0 then 'available' else 'empty' end,
    'sealed-quick-contract-v1','sealed',true,
    r.definition||jsonb_build_object(
      'comparisonAsOf',p_market_date,
      'bulkContainersExcluded',true,
      'membershipIsPointInTime',true
    )
  FROM public.pokemon_market_explorer_sealed_quick_registry_v1 r
  LEFT JOIN _mx_quick_members m
    ON m.market_key=r.quick_key AND m.market_date=p_market_date
  WHERE r.status='APPROVED'
    AND r.quick_key IN (
      'sealed-quick:obtainable','sealed-quick:intermediate','sealed-quick:premium',
      'sealed-quick:new-releases','sealed-quick:established','sealed-quick:global-top10'
    )
  GROUP BY r.quick_key,r.label,r.definition
  ON CONFLICT(generation_id,market_key) DO UPDATE
  SET source_as_of=excluded.source_as_of,
      constituent_count=excluded.constituent_count,
      availability=excluded.availability,
      metadata=excluded.metadata;
  GET DIAGNOSTICS v_markets=ROW_COUNT;

  DROP TABLE IF EXISTS pg_temp._mx_quick_indexed;
  CREATE TEMP TABLE _mx_quick_indexed ON COMMIT DROP AS
  WITH lagged AS (
    SELECT m.*,
      lag(m.market_date) over(
        partition by m.market_key,m.sealed_product_id order by m.market_date
      ) previous_date,
      lag(m.market_price) over(
        partition by m.market_key,m.sealed_product_id order by m.market_date
      ) previous_price
    FROM _mx_quick_members m
  ),
  daily AS (
    SELECT
      market_key,market_date,
      count(*)::integer constituent_count,
      sum(market_price)::numeric basket_value,
      coalesce(sum(market_price) filter(
        where previous_date=market_date-1 and previous_price is not null
      ),0)::numeric current_common,
      coalesce(sum(previous_price) filter(
        where previous_date=market_date-1 and previous_price is not null
      ),0)::numeric previous_common
    FROM lagged
    GROUP BY market_key,market_date
  )
  SELECT d.*,
    100.0*exp(sum(ln(
      case when d.previous_common>0 then d.current_common/d.previous_common else 1.0 end
    )) over(partition by d.market_key order by d.market_date rows unbounded preceding))::numeric
      index_value
  FROM daily d;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  SELECT p_generation_id,market_key,market_date,index_value,basket_value,constituent_count,0
  FROM _mx_quick_indexed
  WHERE market_date<=p_market_date
  ORDER BY market_key,market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  )
  SELECT p_generation_id,r.quick_key,'sealed',
    count(m.sealed_product_id)::integer,
    case when count(m.sealed_product_id)>0 then 'available' else 'empty' end,
    null
  FROM public.pokemon_market_explorer_sealed_quick_registry_v1 r
  LEFT JOIN _mx_quick_members m
    ON m.market_key=r.quick_key AND m.market_date=p_market_date
  WHERE r.status='APPROVED'
    AND r.quick_key LIKE 'sealed-quick:%'
  GROUP BY r.quick_key
  ON CONFLICT(generation_id,market_key) DO UPDATE
  SET total_count=excluded.total_count,availability=excluded.availability,
      availability_reason=excluded.availability_reason;

  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  SELECT
    p_generation_id,m.market_key,
    row_number() over(
      partition by m.market_key order by m.market_price desc,m.sealed_product_id
    )::integer,
    m.sealed_product_id,'sealed',m.set_id,m.market_price,m.market_date,
    jsonb_build_object(
      'asset','sealed','instrumentId',m.sealed_product_id,
      'sealedProductId',m.sealed_product_id,
      'setId',meta.set_id,'setName',meta.set_name,
      'name',meta.name,'productName',meta.name,
      'variantLabel',meta.variant_label,
      'productFamily',meta.product_family,
      'productFamilyLabel',meta.product_family_label,
      'marketPrice',m.market_price,'priceAsOf',m.market_date,
      'imageUrl',coalesce(meta.image_small_url,meta.image_large_url),
      'imageSmallUrl',meta.image_small_url,'imageLargeUrl',meta.image_large_url,
      'isBulkContainer',meta.is_bulk_container
    )
  FROM _mx_quick_members m
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    ON meta.sealed_product_id=m.sealed_product_id
  WHERE m.market_date=p_market_date
  ORDER BY m.market_key,m.market_price desc,m.sealed_product_id;
  GET DIAGNOSTICS v_constituents=ROW_COUNT;

  RETURN jsonb_build_object(
    'markets',v_markets,'historyRows',v_history,'constituentRows',v_constituents
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v2(uuid,date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v2(uuid,date)
TO service_role;

-- Build now requires a base prepared generation already coherent at the target date.
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

  SELECT g.comparison_as_of INTO v_base_date
  FROM public.pokemon_market_explorer_prepared_generations_v1 g
  WHERE g.generation_id=p_base_generation_id AND g.status='complete';

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
    SELECT 1 FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date=p_market_date AND d.market_price>0
  ) THEN
    RAISE EXCEPTION 'SURFACE_SEALED_DAILY_NOT_CURRENT';
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

-- --------------------------------------------------------------------------
-- Coherent-generation assertion used by promotion.
-- --------------------------------------------------------------------------
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

  SELECT comparison_as_of INTO v_base_date
  FROM public.pokemon_market_explorer_prepared_generations_v1
  WHERE generation_id=g.base_prepared_generation_id;
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

CREATE OR REPLACE FUNCTION public.promote_pokemon_market_explorer_surface_v2(
  p_generation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='10s'
AS $function$
DECLARE
  v_old uuid;
  v_receipt jsonb;
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_surface_generations_v2
    WHERE generation_id=p_generation_id AND state='VALIDATED'
  ) THEN
    RAISE EXCEPTION 'ONLY_VALIDATED_SURFACE_GENERATIONS_MAY_BE_PROMOTED';
  END IF;

  v_receipt:=public.assert_pokemon_market_explorer_surface_coherent_v2(p_generation_id);

  SELECT generation_id INTO v_old
  FROM public.pokemon_market_explorer_surface_serving_v2
  WHERE singleton=1
  FOR UPDATE;

  INSERT INTO public.pokemon_market_explorer_surface_serving_v2(
    singleton,generation_id,previous_generation_id,promoted_at
  ) VALUES (1,p_generation_id,v_old,clock_timestamp())
  ON CONFLICT(singleton) DO UPDATE
  SET previous_generation_id=public.pokemon_market_explorer_surface_serving_v2.generation_id,
      generation_id=excluded.generation_id,
      promoted_at=excluded.promoted_at;

  RETURN v_receipt||jsonb_build_object(
    'previousGenerationId',v_old,'promoted',true
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.promote_pokemon_market_explorer_surface_v2(uuid)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.promote_pokemon_market_explorer_surface_v2(uuid)
TO service_role;

-- --------------------------------------------------------------------------
-- Prepared Top/Worst screens: compact directory sort only, never history scan.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_performance_screen_v1(
  p_screen_key text,
  p_asset text,
  p_generation_id uuid,
  p_limit integer DEFAULT 25
)
RETURNS TABLE(
  rank integer,
  screen_key text,
  market_key text,
  label text,
  asset text,
  market_type text,
  metric_7d_pct numeric,
  comparison_as_of date,
  relative_7d_vs_era_pct numeric,
  current_drawdown_pct numeric,
  constituent_count integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path=''
SET statement_timeout='1s'
AS $function$
DECLARE
  v_serving uuid;
  v_asset text:=lower(trim(coalesce(p_asset,'all')));
BEGIN
  IF p_screen_key NOT IN ('top-performers','worst-performers') THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_KEY_INVALID';
  END IF;
  IF v_asset NOT IN ('cards','sealed','all') THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_ASSET_INVALID';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>25 THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_LIMIT_INVALID';
  END IF;

  SELECT s.generation_id INTO v_serving
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  WHERE s.singleton=1;

  IF v_serving IS NULL OR p_generation_id IS DISTINCT FROM v_serving THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_GENERATION_MISMATCH';
  END IF;

  RETURN QUERY
  SELECT
    row_number() over(
      order by
        CASE WHEN p_screen_key='top-performers' THEN d.return_7d_pct END DESC NULLS LAST,
        CASE WHEN p_screen_key='worst-performers' THEN d.return_7d_pct END ASC NULLS LAST,
        d.market_key
    )::integer,
    p_screen_key,
    d.market_key,
    d.label,
    d.asset,
    d.scope_kind,
    d.return_7d_pct,
    d.comparison_as_of,
    null::numeric,
    d.current_drawdown_pct,
    d.constituent_count
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.screen_eligible
    AND d.availability='available'
    AND d.history_available
    AND d.return_7d_pct IS NOT NULL
    AND (v_asset='all' OR d.asset=v_asset)
  ORDER BY
    CASE WHEN p_screen_key='top-performers' THEN d.return_7d_pct END DESC NULLS LAST,
    CASE WHEN p_screen_key='worst-performers' THEN d.return_7d_pct END ASC NULLS LAST,
    d.market_key
  LIMIT p_limit;
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
TO service_role;

COMMIT;
