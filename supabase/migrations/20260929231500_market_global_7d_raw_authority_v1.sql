BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_raw_card_movers_v1(
  p_market_date date,
  p_limit integer DEFAULT 30
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
  v_target_date date;
  v_min_baseline_date date;
  v_nm_condition_id uuid;
  v_raw_count integer:=0;
  v_root_count integer:=0;
  v_market_count integer:=0;
  v_scoped_count integer:=0;
  v_baseline_count integer:=0;
  v_candidate_count integer:=0;
  v_scoped_candidate_count integer:=0;
  v_published_count integer:=0;
  v_movements jsonb:='[]'::jsonb;
BEGIN
  IF p_market_date IS NULL THEN
    RAISE EXCEPTION 'RAW_CARD_MOVERS_MARKET_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>100 THEN
    RAISE EXCEPTION 'RAW_CARD_MOVERS_LIMIT_MUST_BE_1_TO_100';
  END IF;

  SELECT s.generation_id,g.market_date
  INTO v_generation_id,v_serving_date
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  JOIN public.pokemon_market_explorer_surface_generations_v2 g
    ON g.generation_id=s.generation_id
  WHERE s.singleton=1;

  IF v_generation_id IS NULL OR v_serving_date IS DISTINCT FROM p_market_date THEN
    RAISE EXCEPTION 'RAW_CARD_MOVERS_SURFACE_NOT_CURRENT: serving % target %',
      coalesce(v_serving_date::text,'null'),p_market_date::text;
  END IF;

  SELECT id INTO v_nm_condition_id
  FROM public.conditions
  WHERE name='Near Mint' AND abbreviation='NM'
  ORDER BY id
  LIMIT 1;

  IF v_nm_condition_id IS NULL THEN
    RAISE EXCEPTION 'RAW_CARD_MOVERS_NEAR_MINT_CONDITION_MISSING';
  END IF;

  v_target_date:=p_market_date-6;
  v_min_baseline_date:=p_market_date-10;

  DROP TABLE IF EXISTS pg_temp._raw_mover_universe;
  CREATE TEMP TABLE _raw_mover_universe ON COMMIT DROP AS
  SELECT
    c.instrument_id::uuid AS card_variant_id,
    c.set_id,
    c.market_price::numeric AS current_price,
    nullif(c.item->>'sourceDate','')::date AS current_source_date,
    coalesce(nullif(c.item->>'marketScope',''),'standard') AS market_scope,
    c.item
  FROM public.pokemon_market_explorer_surface_constituents_v2 c
  WHERE c.generation_id=v_generation_id
    AND c.market_key='raw'
    AND c.asset='cards'
    AND c.market_price>0;

  CREATE UNIQUE INDEX ON _raw_mover_universe(card_variant_id);
  ANALYZE _raw_mover_universe;

  SELECT
    count(*)::integer,
    count(*) FILTER (WHERE market_scope<>'standard')::integer
  INTO v_raw_count,v_scoped_count
  FROM _raw_mover_universe;

  SELECT h.root_count,h.market_count
  INTO v_root_count,v_market_count
  FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
  WHERE h.market_date=p_market_date;

  IF v_raw_count=0 OR v_root_count IS NULL OR v_market_count IS NULL THEN
    RAISE EXCEPTION 'RAW_CARD_MOVERS_RAW_AUTHORITY_MISSING';
  END IF;

  DROP TABLE IF EXISTS pg_temp._raw_mover_baselines;
  CREATE TEMP TABLE _raw_mover_baselines ON COMMIT DROP AS
  SELECT DISTINCT ON (o.card_variant_id)
    o.card_variant_id,
    coalesce(o.captured_date,o.captured_at::date) AS baseline_date,
    o.market_price::numeric AS baseline_price
  FROM public.card_variant_price_observations o
  JOIN _raw_mover_universe r
    ON r.card_variant_id=o.card_variant_id
  WHERE o.condition_id=v_nm_condition_id
    AND lower(o.source)='tcgplayer'
    AND o.market_price>0
    AND coalesce(o.captured_date,o.captured_at::date) BETWEEN v_min_baseline_date AND v_target_date
  ORDER BY
    o.card_variant_id,
    coalesce(o.captured_date,o.captured_at::date) DESC,
    o.created_at DESC,
    o.id DESC;

  CREATE UNIQUE INDEX ON _raw_mover_baselines(card_variant_id);
  ANALYZE _raw_mover_baselines;

  SELECT count(*)::integer INTO v_baseline_count
  FROM _raw_mover_baselines;

  DROP TABLE IF EXISTS pg_temp._raw_mover_candidates;
  CREATE TEMP TABLE _raw_mover_candidates ON COMMIT DROP AS
  SELECT
    r.card_variant_id,
    r.set_id,
    r.market_scope,
    r.item,
    r.current_price,
    r.current_source_date,
    b.baseline_date,
    b.baseline_price,
    round(r.current_price-b.baseline_price,2) AS change_amount,
    round(((r.current_price-b.baseline_price)/b.baseline_price*100)::numeric,2) AS change_percent,
    round((
      pg_catalog.abs(r.current_price-b.baseline_price)*0.72
      + least(pg_catalog.abs((r.current_price-b.baseline_price)/b.baseline_price*100),100)
        * r.current_price * 0.0028
    )::numeric,4) AS movement_score
  FROM _raw_mover_universe r
  JOIN _raw_mover_baselines b USING(card_variant_id)
  WHERE r.current_price>=1
    AND r.current_source_date IS NOT NULL
    AND r.current_source_date<=p_market_date
    AND b.baseline_price>0
    AND (p_market_date-b.baseline_date) BETWEEN 3 AND 10
    AND pg_catalog.abs(r.current_price-b.baseline_price)>=0.25
    AND pg_catalog.abs((r.current_price-b.baseline_price)/b.baseline_price*100)<=300;

  CREATE INDEX ON _raw_mover_candidates(movement_score DESC,card_variant_id);
  ANALYZE _raw_mover_candidates;

  SELECT
    count(*)::integer,
    count(*) FILTER (WHERE market_scope<>'standard')::integer
  INTO v_candidate_count,v_scoped_candidate_count
  FROM _raw_mover_candidates;

  WITH ranked AS (
    SELECT
      c.*,
      s.name AS fallback_set_name,
      row_number() OVER (
        ORDER BY c.movement_score DESC,
                 pg_catalog.abs(c.change_amount) DESC,
                 pg_catalog.abs(c.change_percent) DESC,
                 c.card_variant_id
      ) AS mover_rank
    FROM _raw_mover_candidates c
    LEFT JOIN public.sets s ON s.id=c.set_id
  ),
  published AS (
    SELECT * FROM ranked
    WHERE mover_rank<=p_limit
    ORDER BY mover_rank
  )
  SELECT
    coalesce(jsonb_agg(
      jsonb_build_object(
        'rank',p.mover_rank,
        'canonicalCardId',p.item->>'canonicalCardId',
        'cardVariantId',p.card_variant_id,
        'conditionId',v_nm_condition_id,
        'setId',p.set_id,
        'setName',coalesce(nullif(p.item->>'setName',''),p.fallback_set_name),
        'marketScope',p.market_scope,
        'edition',p.item->>'edition',
        'name',p.item->>'cardName',
        'cardName',p.item->>'cardName',
        'rarity',p.item->>'rarity',
        'cardNumber',p.item->>'cardNumber',
        'setNumber',p.item->>'cardNumber',
        'imageUrl',coalesce(
          nullif(p.item->>'imageUrl',''),
          nullif(p.item->>'imageSmallUrl',''),
          nullif(p.item->>'imageLargeUrl','')
        ),
        'imageSmallUrl',p.item->>'imageSmallUrl',
        'imageLargeUrl',p.item->>'imageLargeUrl',
        'printingType',p.item->>'printingType',
        'marketPrice',round(p.current_price,2),
        'currentPrice',round(p.current_price,2),
        'startingPrice',round(p.baseline_price,2),
        'changeAmount',p.change_amount,
        'changePercent',p.change_percent,
        'change7dAmount',p.change_amount,
        'change7dPercent',p.change_percent,
        'movementScore',
          CASE
            WHEN p.change_amount>0 THEN p.movement_score
            WHEN p.change_amount<0 THEN -p.movement_score
            ELSE 0
          END,
        'movementLabel',
          CASE
            WHEN p.change_amount>0 THEN 'heating_up'
            WHEN p.change_amount<0 THEN 'cooling_off'
            ELSE 'flat'
          END,
        'moverEligible',true,
        'window','7D',
        'windowDays',7,
        'windowConvention','inclusive_calendar_dates_v1',
        'targetStartDate',v_target_date,
        'startDate',p.baseline_date,
        'endDate',p_market_date,
        'fullWindowCoverage',true,
        'isPartialWindow',false,
        'windowCoverageDays',(p_market_date-p.baseline_date),
        'requestedWindowDays',7,
        'enoughHistory',true,
        'reliable',true,
        'reliability','reliable',
        'startSourceDate',p.baseline_date,
        'endSourceDate',p.current_source_date,
        'startCarriedForward',(p.baseline_date<v_target_date),
        'endCarriedForward',(p.current_source_date<p_market_date),
        'source','TCGPlayer',
        'provider','TCGPlayer',
        'priceUpdatedAt',p.current_source_date,
        'sourceMarketKey',p.item->>'sourceMarketKey'
      )
      ORDER BY p.mover_rank
    ),'[]'::jsonb),
    count(*)::integer
  INTO v_movements,v_published_count
  FROM published p;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'generationId',v_generation_id,
    'window','7D',
    'windowDays',7,
    'targetStartDate',v_target_date,
    'movementContractVersion','pokemon_card_movement_v1',
    'windowConvention','inclusive_calendar_dates_v1',
    'universeContractVersion','serving_raw_exact_variant_v1',
    'rankingMethodology','market_movement_score_v1',
    'priceBasis','serving_raw_current_plus_exact_nm_tcgplayer_observation_baseline_v1',
    'rawConstituentCount',v_raw_count,
    'rawRootCount',v_root_count,
    'rawMarketCount',v_market_count,
    'scopedConstituentCount',v_scoped_count,
    'baselineCoveredCount',v_baseline_count,
    'eligibleCandidateCount',v_candidate_count,
    'scopedCandidateCount',v_scoped_candidate_count,
    'publishedCount',v_published_count,
    'movements',v_movements
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_raw_card_movers_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_raw_card_movers_v1(date,integer)
  TO service_role;

COMMIT;
