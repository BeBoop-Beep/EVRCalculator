BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_mixed_movers_v1(
  p_market_date date,
  p_limit integer DEFAULT 50
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO ''
SET statement_timeout TO '90s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  v_generation_id uuid;
  v_serving_date date;
  v_card_authority jsonb;
  v_card_count integer:=0;
  v_sealed_count integer:=0;
  v_sealed_current_count integer:=0;
  v_sealed_baseline_count integer:=0;
  v_sealed_candidate_count integer:=0;
  v_sealed_transient_excluded integer:=0;
  v_published_cards integer:=0;
  v_published_sealed integer:=0;
  v_movements jsonb:='[]'::jsonb;
BEGIN
  IF p_market_date IS NULL THEN
    RAISE EXCEPTION 'MIXED_MOVERS_MARKET_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>50 THEN
    RAISE EXCEPTION 'MIXED_MOVERS_LIMIT_MUST_BE_1_TO_50';
  END IF;

  SELECT s.generation_id,g.market_date
  INTO v_generation_id,v_serving_date
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  JOIN public.pokemon_market_explorer_surface_generations_v2 g
    ON g.generation_id=s.generation_id
  WHERE s.singleton=1;

  IF v_generation_id IS NULL OR v_serving_date IS DISTINCT FROM p_market_date THEN
    RAISE EXCEPTION 'MIXED_MOVERS_SURFACE_NOT_CURRENT: serving % target %',
      coalesce(v_serving_date::text,'null'),p_market_date::text;
  END IF;

  SELECT public.get_pokemon_market_raw_card_movers_v1(p_market_date,100)
  INTO v_card_authority;

  IF coalesce(v_card_authority->>'status','')<>'READY'
     OR v_card_authority->>'generationId' IS DISTINCT FROM v_generation_id::text
     OR v_card_authority->>'universeContractVersion'<>'serving_raw_exact_variant_v1'
     OR v_card_authority->>'baselineQualityGuardVersion'<>'target_baseline_reversion_guard_v1'
  THEN
    RAISE EXCEPTION 'MIXED_MOVERS_CARD_AUTHORITY_NOT_READY';
  END IF;

  v_card_count:=coalesce((v_card_authority->>'rawConstituentCount')::integer,0);

  DROP TABLE IF EXISTS pg_temp._mixed_card_candidates;
  CREATE TEMP TABLE _mixed_card_candidates ON COMMIT DROP AS
  SELECT
    'cards'::text AS asset,
    coalesce(nullif(m.item->>'cardVariantId',''),nullif(m.item->>'canonicalCardId','')) AS instrument_id,
    pg_catalog.abs(coalesce((m.item->>'movementScore')::numeric,0)) AS movement_score,
    pg_catalog.abs(coalesce((m.item->>'changeAmount')::numeric,0)) AS absolute_change,
    pg_catalog.abs(coalesce((m.item->>'changePercent')::numeric,0)) AS absolute_percent,
    m.item || jsonb_build_object(
      'asset','cards',
      'instrumentId',coalesce(m.item->>'cardVariantId',m.item->>'canonicalCardId')
    ) AS movement
  FROM jsonb_array_elements(v_card_authority->'movements') WITH ORDINALITY m(item,ordinality);

  CREATE INDEX ON _mixed_card_candidates(movement_score DESC,instrument_id);
  ANALYZE _mixed_card_candidates;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_universe;
  CREATE TEMP TABLE _mixed_sealed_universe ON COMMIT DROP AS
  SELECT
    c.instrument_id::uuid AS sealed_product_id,
    c.set_id,
    c.market_price::numeric AS serving_price,
    c.item
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  WHERE c.generation_id=v_generation_id
    AND c.market_key='sealedMarket'
    AND c.asset='sealed'
    AND c.market_price>0;

  CREATE UNIQUE INDEX ON _mixed_sealed_universe(sealed_product_id);
  ANALYZE _mixed_sealed_universe;

  SELECT count(*)::integer INTO v_sealed_count
  FROM _mixed_sealed_universe;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_endpoint;
  CREATE TEMP TABLE _mixed_sealed_endpoint ON COMMIT DROP AS
  SELECT DISTINCT ON (o.sealed_product_id)
    o.sealed_product_id,
    o.captured_at::date AS end_date,
    o.market_price::numeric AS end_price
  FROM public.sealed_product_price_observations o
  JOIN _mixed_sealed_universe u USING(sealed_product_id)
  WHERE lower(o.source)='tcgplayer'
    AND upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    AND o.market_price>0
    AND o.captured_at>=p_market_date::timestamptz
    AND o.captured_at<(p_market_date+1)::timestamptz
  ORDER BY o.sealed_product_id,o.captured_at DESC,o.id DESC;

  CREATE UNIQUE INDEX ON _mixed_sealed_endpoint(sealed_product_id);
  ANALYZE _mixed_sealed_endpoint;

  SELECT count(*)::integer INTO v_sealed_current_count
  FROM _mixed_sealed_endpoint;

  IF EXISTS (
    SELECT 1
    FROM _mixed_sealed_endpoint e
    JOIN _mixed_sealed_universe u USING(sealed_product_id)
    WHERE e.end_price IS DISTINCT FROM u.serving_price
  ) THEN
    RAISE EXCEPTION 'MIXED_MOVERS_SEALED_ENDPOINT_SURFACE_MISMATCH';
  END IF;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_baseline;
  CREATE TEMP TABLE _mixed_sealed_baseline ON COMMIT DROP AS
  SELECT DISTINCT ON (o.sealed_product_id)
    o.sealed_product_id,
    o.captured_at::date AS baseline_date,
    o.market_price::numeric AS baseline_price
  FROM public.sealed_product_price_observations o
  JOIN _mixed_sealed_universe u USING(sealed_product_id)
  WHERE lower(o.source)='tcgplayer'
    AND upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    AND o.market_price>0
    AND o.captured_at::date BETWEEN p_market_date-10 AND p_market_date-6
  ORDER BY o.sealed_product_id,o.captured_at DESC,o.id DESC;

  CREATE UNIQUE INDEX ON _mixed_sealed_baseline(sealed_product_id);
  ANALYZE _mixed_sealed_baseline;

  SELECT count(*)::integer INTO v_sealed_baseline_count
  FROM _mixed_sealed_baseline;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_scored;
  CREATE TEMP TABLE _mixed_sealed_scored ON COMMIT DROP AS
  SELECT
    u.sealed_product_id,
    u.set_id,
    u.item,
    b.baseline_date,
    b.baseline_price,
    e.end_date,
    e.end_price,
    round(e.end_price-b.baseline_price,2) AS change_amount,
    round(((e.end_price-b.baseline_price)/b.baseline_price*100)::numeric,2) AS change_percent,
    round((
      pg_catalog.abs(e.end_price-b.baseline_price)*0.72
      + least(
          pg_catalog.abs((e.end_price-b.baseline_price)/b.baseline_price*100),
          100
        )*e.end_price*0.0028
    )::numeric,4) AS movement_score
  FROM _mixed_sealed_universe u
  JOIN _mixed_sealed_endpoint e USING(sealed_product_id)
  JOIN _mixed_sealed_baseline b USING(sealed_product_id)
  WHERE e.end_price>=1
    AND pg_catalog.abs(e.end_price-b.baseline_price)>=0.25
    AND pg_catalog.abs((e.end_price-b.baseline_price)/b.baseline_price*100)<=300
    AND (p_market_date-b.baseline_date) BETWEEN 3 AND 10;

  CREATE INDEX ON _mixed_sealed_scored(movement_score DESC,sealed_product_id);
  ANALYZE _mixed_sealed_scored;

  SELECT count(*)::integer INTO v_sealed_candidate_count
  FROM _mixed_sealed_scored;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_quality;
  CREATE TEMP TABLE _mixed_sealed_quality ON COMMIT DROP AS
  SELECT
    s.*,
    pre.pre_price,
    EXISTS (
      SELECT 1
      FROM public.sealed_product_price_observations o
      WHERE o.sealed_product_id=s.sealed_product_id
        AND lower(o.source)='tcgplayer'
        AND upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
        AND o.market_price>0
        AND o.captured_at::date>s.baseline_date
        AND o.captured_at::date<=least(p_market_date,s.baseline_date+3)
        AND pre.pre_price IS NOT NULL
        AND pg_catalog.abs(o.market_price-pre.pre_price)/pre.pre_price<=0.10
    ) AS reverted_to_prebaseline
  FROM _mixed_sealed_scored s
  LEFT JOIN LATERAL (
    SELECT o.market_price::numeric AS pre_price
    FROM public.sealed_product_price_observations o
    WHERE o.sealed_product_id=s.sealed_product_id
      AND lower(o.source)='tcgplayer'
      AND upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
      AND o.market_price>0
      AND o.captured_at::date<s.baseline_date
      AND o.captured_at::date>=s.baseline_date-3
    ORDER BY o.captured_at DESC,o.id DESC
    LIMIT 1
  ) pre ON true;

  SELECT count(*)::integer INTO v_sealed_transient_excluded
  FROM _mixed_sealed_quality q
  WHERE q.pre_price IS NOT NULL
    AND pg_catalog.abs(q.baseline_price-q.pre_price)/q.pre_price>=0.15
    AND q.reverted_to_prebaseline;

  DROP TABLE IF EXISTS pg_temp._mixed_sealed_candidates;
  CREATE TEMP TABLE _mixed_sealed_candidates ON COMMIT DROP AS
  SELECT
    'sealed'::text AS asset,
    q.sealed_product_id::text AS instrument_id,
    q.movement_score,
    pg_catalog.abs(q.change_amount) AS absolute_change,
    pg_catalog.abs(q.change_percent) AS absolute_percent,
    jsonb_build_object(
      'asset','sealed',
      'instrumentId',q.sealed_product_id,
      'sealedProductId',q.sealed_product_id,
      'id',q.sealed_product_id,
      'setId',q.set_id,
      'setName',q.item->>'setName',
      'name',q.item->>'productName',
      'productName',q.item->>'productName',
      'productFamily',q.item->>'productFamily',
      'productFamilyLabel',q.item->>'productFamilyLabel',
      'variantLabel',q.item->>'variantLabel',
      'imageUrl',q.item->>'imageUrl',
      'imageSmallUrl',q.item->>'imageSmallUrl',
      'imageLargeUrl',q.item->>'imageLargeUrl',
      'marketPrice',round(q.end_price,2),
      'currentPrice',round(q.end_price,2),
      'startingPrice',round(q.baseline_price,2),
      'changeAmount',q.change_amount,
      'changePercent',q.change_percent,
      'change7dAmount',q.change_amount,
      'change7dPercent',q.change_percent,
      'movementScore',
        CASE
          WHEN q.change_amount>0 THEN q.movement_score
          WHEN q.change_amount<0 THEN -q.movement_score
          ELSE 0
        END,
      'movementLabel',
        CASE
          WHEN q.change_amount>0 THEN 'heating_up'
          WHEN q.change_amount<0 THEN 'cooling_off'
          ELSE 'flat'
        END,
      'moverEligible',true,
      'window','7D',
      'windowDays',7,
      'windowConvention','inclusive_calendar_dates_v1',
      'targetStartDate',p_market_date-6,
      'startDate',q.baseline_date,
      'endDate',p_market_date,
      'fullWindowCoverage',true,
      'isPartialWindow',false,
      'windowCoverageDays',(p_market_date-q.baseline_date),
      'requestedWindowDays',7,
      'enoughHistory',true,
      'reliable',true,
      'reliability','reliable',
      'startSourceDate',q.baseline_date,
      'endSourceDate',q.end_date,
      'startCarriedForward',(q.baseline_date<p_market_date-6),
      'endCarriedForward',false,
      'source','TCGPlayer',
      'provider','TCGPlayer',
      'priceUpdatedAt',q.end_date,
      'sourceMarketKey','sealedMarket'
    ) AS movement
  FROM _mixed_sealed_quality q
  WHERE NOT (
    q.pre_price IS NOT NULL
    AND pg_catalog.abs(q.baseline_price-q.pre_price)/q.pre_price>=0.15
    AND q.reverted_to_prebaseline
  );

  CREATE INDEX ON _mixed_sealed_candidates(movement_score DESC,instrument_id);
  ANALYZE _mixed_sealed_candidates;

  WITH combined AS (
    SELECT * FROM _mixed_card_candidates
    UNION ALL
    SELECT * FROM _mixed_sealed_candidates
  ),
  ranked AS (
    SELECT
      c.*,
      row_number() OVER (
        ORDER BY
          c.movement_score DESC,
          c.absolute_change DESC,
          c.absolute_percent DESC,
          c.asset,
          c.instrument_id
      )::integer AS mixed_rank
    FROM combined c
  ),
  published AS (
    SELECT *
    FROM ranked
    WHERE mixed_rank<=p_limit
    ORDER BY mixed_rank
  )
  SELECT
    coalesce(jsonb_agg(
      jsonb_set(
        p.movement,
        '{rank}',
        to_jsonb(p.mixed_rank),
        true
      )
      ORDER BY p.mixed_rank
    ),'[]'::jsonb),
    count(*) FILTER (WHERE p.asset='cards')::integer,
    count(*) FILTER (WHERE p.asset='sealed')::integer
  INTO v_movements,v_published_cards,v_published_sealed
  FROM published p;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'generationId',v_generation_id,
    'window','7D',
    'windowDays',7,
    'targetStartDate',p_market_date-6,
    'movementContractVersion','pokemon_card_movement_v1',
    'windowConvention','inclusive_calendar_dates_v1',
    'universeContractVersion','serving_cards_and_sealed_exact_instruments_v1',
    'rankingMethodology','market_movement_score_v1',
    'baselineQualityGuardVersion','target_baseline_reversion_guard_v1',
    'cardUniverseContractVersion',v_card_authority->>'universeContractVersion',
    'cardConstituentCount',v_card_count,
    'cardCandidateCount',coalesce((v_card_authority->>'eligibleCandidateCount')::integer,0),
    'cardTransientExcludedCount',coalesce((v_card_authority->>'baselineTransientExcludedCount')::integer,0),
    'sealedConstituentCount',v_sealed_count,
    'sealedCurrentEndpointCount',v_sealed_current_count,
    'sealedBaselineCoveredCount',v_sealed_baseline_count,
    'sealedCandidateCount',v_sealed_candidate_count,
    'sealedTransientExcludedCount',v_sealed_transient_excluded,
    'publishedCount',v_published_cards+v_published_sealed,
    'publishedCardCount',v_published_cards,
    'publishedSealedCount',v_published_sealed,
    'movements',v_movements
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_mixed_movers_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_mixed_movers_v1(date,integer)
  TO service_role;

COMMIT;
