
BEGIN;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_explorer_rarity_registry_v1(
  p_market_date date DEFAULT NULL::date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
SET statement_timeout = '10s'
SET lock_timeout = '2s'
SET jit = 'off'
AS $function$
DECLARE
  v_market_date date;
  v_rows integer;
BEGIN
  SELECT coalesce(p_market_date,max(c.market_date))
  INTO v_market_date
  FROM public.pokemon_market_explorer_rarity_daily_coverage_v1 c;

  IF v_market_date IS NULL THEN
    RAISE EXCEPTION 'RARITY_AUDIT_NO_MATERIALIZED_MARKET_DATE';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    WHERE c.market_date=v_market_date
  ) THEN
    RAISE EXCEPTION 'RARITY_AUDIT_MARKET_DATE_NOT_MATERIALIZED';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_rarity_coverage_certification_v1 x
    WHERE x.singleton
      AND x.certified_through>=v_market_date
  ) THEN
    RAISE EXCEPTION 'RARITY_COVERAGE_NOT_CERTIFIED';
  END IF;

  WITH current_stats AS MATERIALIZED (
    SELECT
      c.rarity_key,
      c.priced_card_count AS card_count,
      c.represented_set_count AS set_count,
      c.image_count
    FROM public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    WHERE c.market_date=v_market_date
  ),
  history_stats AS MATERIALIZED (
    SELECT
      c.rarity_key,
      min(c.market_date) AS history_start,
      max(c.market_date) AS history_end,
      count(DISTINCT c.market_date)::integer AS history_points
    FROM public.pokemon_market_explorer_rarity_daily_coverage_v1 c
    WHERE c.market_date<=v_market_date
    GROUP BY c.rarity_key
  ),
  prepared AS (
    SELECT
      coalesce(
        nullif(d.metadata->>'rarityKey',''),
        nullif(d.metadata->>'segmentKey',''),
        nullif(d.metadata->>'segmentId',''),
        nullif(d.metadata->>'filterRarityKey','')
      ) AS rarity_key,
      min(d.market_key) AS market_key
    FROM public.pokemon_market_explorer_prepared_directory_v1 d
    WHERE d.asset='cards'
      AND d.market_type='prepared_rarity'
    GROUP BY coalesce(
      nullif(d.metadata->>'rarityKey',''),
      nullif(d.metadata->>'segmentKey',''),
      nullif(d.metadata->>'segmentId',''),
      nullif(d.metadata->>'filterRarityKey','')
    )
  )
  UPDATE public.pokemon_market_explorer_rarity_registry_v1 r
  SET
    current_market_date=v_market_date,
    current_priced_card_count=coalesce(c.card_count,0),
    represented_set_count=coalesce(c.set_count,0),
    image_count=coalesce(c.image_count,0),
    history_start_date=h.history_start,
    history_end_date=h.history_end,
    history_point_count=coalesce(h.history_points,0),
    prepared_market_key=p.market_key,
    eligibility_state=CASE
      WHEN coalesce(c.card_count,0)<=0 THEN 'UNAVAILABLE'
      WHEN coalesce(h.history_points,0)<2 OR h.history_end IS DISTINCT FROM v_market_date
        THEN 'INSUFFICIENT_HISTORY'
      WHEN p.market_key IS NOT NULL THEN 'PREPARED'
      ELSE 'CUSTOM_BUILD_AVAILABLE'
    END,
    reason=CASE
      WHEN coalesce(c.card_count,0)<=0
        THEN 'No current positively priced canonical constituents'
      WHEN coalesce(h.history_points,0)<2
        THEN 'Fewer than two materialized accepted history dates'
      WHEN h.history_end IS DISTINCT FROM v_market_date
        THEN 'Materialized history does not reach the audited market date'
      WHEN p.market_key IS NOT NULL
        THEN CASE
          WHEN coalesce(c.card_count,0)>=25 AND coalesce(c.set_count,0)>=3
            THEN 'Maintained prepared market is published; broad-market analytical gate passes'
          ELSE 'Maintained prepared market is published; selectable despite being below the 25-card / 3-set broad-market analytical gate'
        END
      WHEN coalesce(c.card_count,0)>0
        THEN CASE
          WHEN coalesce(c.card_count,0)>=25 AND coalesce(c.set_count,0)>=3
            THEN 'Executable single-axis rarity market; broad-market analytical gate passes'
          ELSE format(
            'Executable single-axis rarity market; below 25-card / 3-set broad-market analytical gate (%s cards, %s sets)',
            coalesce(c.card_count,0),coalesce(c.set_count,0)
          )
        END
      ELSE 'No current positively priced canonical constituents'
    END,
    audited_at=clock_timestamp()
  FROM current_stats c
  FULL JOIN history_stats h USING (rarity_key)
  FULL JOIN prepared p USING (rarity_key)
  WHERE r.rarity_key=coalesce(c.rarity_key,h.rarity_key,p.rarity_key);

  GET DIAGNOSTICS v_rows=ROW_COUNT;

  UPDATE public.pokemon_market_explorer_rarity_registry_v1 r
  SET current_market_date=v_market_date,
      current_priced_card_count=0,
      represented_set_count=0,
      image_count=0,
      history_start_date=null,
      history_end_date=null,
      history_point_count=0,
      prepared_market_key=null,
      eligibility_state='UNAVAILABLE',
      reason='No current positively priced canonical constituents',
      audited_at=clock_timestamp()
  WHERE NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_rarity_daily_coverage_v1 c
      WHERE c.market_date=v_market_date
        AND c.rarity_key=r.rarity_key
    );

  RETURN jsonb_build_object(
    'marketDate',v_market_date,
    'taxonomyVersion','pokemon-card-rarity-filter-taxonomy-v1',
    'registryRows',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1),
    'updated',v_rows,
    'prepared',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1 WHERE eligibility_state='PREPARED'),
    'preparedCandidates',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1 WHERE eligibility_state='CUSTOM_BUILD_AVAILABLE'),
    'insufficientCohort',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1 WHERE eligibility_state='INSUFFICIENT_COHORT'),
    'insufficientHistory',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1 WHERE eligibility_state='INSUFFICIENT_HISTORY'),
    'unavailable',(SELECT count(*) FROM public.pokemon_market_explorer_rarity_registry_v1 WHERE eligibility_state='UNAVAILABLE')
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.normalize_pokemon_market_explorer_rarity_surface_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $function$
DECLARE
  r public.pokemon_market_explorer_rarity_registry_v1%rowtype;
  v_key text;
  v_broad boolean;
BEGIN
  IF NEW.asset IS DISTINCT FROM 'cards' OR NEW.scope_kind IS DISTINCT FROM 'rarity' THEN
    RETURN NEW;
  END IF;

  v_key:=coalesce(nullif(NEW.taxonomy_key,''),nullif(NEW.metadata->>'rarityKey',''));
  IF v_key IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT * INTO r
  FROM public.pokemon_market_explorer_rarity_registry_v1 x
  WHERE x.rarity_key=v_key;

  IF NOT FOUND THEN
    RETURN NEW;
  END IF;

  v_broad:=(r.current_priced_card_count>=25 AND r.represented_set_count>=3);
  NEW.screen_eligible:=v_broad;
  NEW.metadata:=coalesce(NEW.metadata,'{}'::jsonb)
    - 'qualityGate'
    || jsonb_build_object(
      'selectionGate','>=1 current positively priced canonical constituent + >=2 accepted history dates reaching current market date',
      'broadMarketGate','25 cards / 3 sets',
      'broadMarketEligible',v_broad,
      'selectionAvailable',r.eligibility_state IN ('PREPARED','CUSTOM_BUILD_AVAILABLE')
    );
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_normalize_pokemon_market_explorer_rarity_surface_v1
  ON public.pokemon_market_explorer_surface_directory_v2;

CREATE TRIGGER trg_normalize_pokemon_market_explorer_rarity_surface_v1
BEFORE INSERT OR UPDATE ON public.pokemon_market_explorer_surface_directory_v2
FOR EACH ROW
EXECUTE FUNCTION public.normalize_pokemon_market_explorer_rarity_surface_v1();

REVOKE ALL ON FUNCTION public.normalize_pokemon_market_explorer_rarity_surface_v1()
  FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_asset_options_v2(p_asset text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = ''
SET statement_timeout = '2s'
AS $function$
DECLARE
  v_asset text:=pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset,'')));
  v_generation uuid;
  v_result jsonb;
BEGIN
  IF v_asset NOT IN ('cards','sealed','graded') THEN
    RAISE EXCEPTION 'ASSET_MUST_BE_CARDS_SEALED_OR_GRADED';
  END IF;

  SELECT generation_id INTO v_generation
  FROM public.pokemon_market_explorer_surface_serving_v2 WHERE singleton=1;

  IF v_asset='cards' THEN
    SELECT jsonb_build_object(
      'asset','cards',
      'rarityTaxonomyVersion','pokemon-card-rarity-filter-taxonomy-v1',
      'rarities',coalesce(jsonb_agg(
        jsonb_build_object(
          'key',r.rarity_key,'label',r.label,
          'preparedMarketAvailable',
            (r.eligibility_state IN ('PREPARED','CUSTOM_BUILD_AVAILABLE') AND (
              r.prepared_market_key IS NOT NULL OR EXISTS (
                SELECT 1 FROM public.pokemon_market_explorer_surface_directory_v2 d
                WHERE d.generation_id=v_generation AND d.asset='cards'
                  AND d.scope_kind='rarity' AND d.taxonomy_key=r.rarity_key
              )
            )),
          'preparedMarketKey',coalesce(
            (SELECT d.market_key
             FROM public.pokemon_market_explorer_surface_directory_v2 d
             WHERE d.generation_id=v_generation AND d.asset='cards'
               AND d.scope_kind='rarity' AND d.taxonomy_key=r.rarity_key
             LIMIT 1),
            r.prepared_market_key
          ),
          'eligibilityState',r.eligibility_state,
          'selectionAvailable',r.eligibility_state IN ('PREPARED','CUSTOM_BUILD_AVAILABLE'),
          'screenEligible',(r.current_priced_card_count>=25 AND r.represented_set_count>=3),
          'reason',r.reason,
          'currentPricedCardCount',r.current_priced_card_count,
          'representedSetCount',r.represented_set_count,
          'historyPointCount',r.history_point_count,'imageCount',r.image_count
        ) ORDER BY r.label
      ),'[]'::jsonb)
    )
    INTO v_result
    FROM public.pokemon_market_explorer_rarity_registry_v1 r;
    RETURN v_result;
  END IF;

  IF v_asset='sealed' THEN
    SELECT jsonb_build_object(
      'asset','sealed',
      'classificationVersion','sealed-product-classification-v5-consumer-retail-taxonomy',
      'totalSealedParentDefinition','Consumer-retail sealed products; only true bulk/container packaging is excluded',
      'types',coalesce(jsonb_agg(
        jsonb_build_object(
          'key',r.product_family,'label',r.display_label,'definition',r.definition,
          'preparedMarketAvailable',EXISTS (
            SELECT 1 FROM public.pokemon_market_explorer_surface_directory_v2 d
            WHERE d.generation_id=v_generation
              AND d.market_key='sealed-type:'||r.product_family
          ),
          'preparedMarketKey',CASE WHEN EXISTS (
            SELECT 1 FROM public.pokemon_market_explorer_surface_directory_v2 d
            WHERE d.generation_id=v_generation
              AND d.market_key='sealed-type:'||r.product_family
          ) THEN 'sealed-type:'||r.product_family ELSE r.prepared_market_key END,
          'eligibilityState',r.eligibility_state,
          'parentMembership',r.parent_membership,'bulkContainer',r.bulk_container,
          'currentProductCount',r.current_product_count,
          'currentPricedCount',r.current_priced_count,
          'representedSetCount',r.represented_set_count,
          'representedEraCount',r.represented_era_count,
          'historyPointCount',r.history_point_count
        ) ORDER BY r.display_label
      ),'[]'::jsonb),
      'quickMarkets',(
        SELECT coalesce(jsonb_agg(jsonb_build_object(
          'key',q.quick_key,'label',q.label,'status',q.status,
          'definition',q.definition,'researchBasis',q.research_basis
        ) ORDER BY q.label),'[]'::jsonb)
        FROM public.pokemon_market_explorer_sealed_quick_registry_v1 q
      )
    )
    INTO v_result
    FROM public.pokemon_market_explorer_sealed_type_registry_v1 r;
    RETURN v_result;
  END IF;

  RETURN jsonb_build_object(
    'asset','graded','availability','INSUFFICIENT_AUTHORITY',
    'reason','Graded production coverage is not yet broad enough to publish markets.'
  );
END;
$function$;

COMMIT;
