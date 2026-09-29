-- Publish exact-edition current Set Value snapshots even when a bounded number
-- of card prices are unresolved. The published dollar value is explicitly the
-- subtotal of known exact-edition prices; unresolved cards remain in the roster
-- with marketPrice = NULL. Historical price performance remains fail-closed
-- unless the current basket is complete and separately history-certified.
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
  v_roster_rows integer;
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
    h.coverage_pct,
    coalesce(h.certified_on_date,false) AS current_complete,
    (
      coalesce(h.certified_on_date,false)
      AND coalesce(cert.history_publishable,false)
    ) AS history_publishable,
    CASE
      WHEN coalesce(h.certified_on_date,false)
        THEN cert.certification_status
      ELSE 'withheld_incomplete_current'
    END AS history_certification_status,
    CASE
      WHEN coalesce(h.certified_on_date,false)
        THEN cert.certification_reason
      ELSE 'Current exact-edition basket has unresolved card prices; current value is the known-card subtotal and price-performance history is withheld.'
    END AS history_certification_reason
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow h
    ON h.set_id=d.set_id
   AND h.market_scope=d.market_scope
   AND h.market_date=p_market_date
   AND h.set_value>0
   AND h.priced_card_count>0
   AND h.expected_card_count>0
   AND h.priced_card_count<=h.expected_card_count
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
      'status','NO_PRICED_SCOPES',
      'marketDate',p_market_date,
      'marketCount',0,
      'constituentCount',0,
      'historyRows',0
    );
  END IF;

  CREATE UNIQUE INDEX ON _mx_scoped_current(market_key);
  ANALYZE _mx_scoped_current;

  -- Keep the full exact-edition identity roster. Unknown prices are NULL, never
  -- substituted from another edition or from a generic Holofoil observation.
  DROP TABLE IF EXISTS pg_temp._mx_scoped_roster;
  CREATE TEMP TABLE _mx_scoped_roster ON COMMIT DROP AS
  SELECT
    c.market_key,
    c.set_id AS root_set_id,
    c.market_scope,
    x.canonical_card_id,
    x.member_set_id,
    x.card_variant_id,
    CASE WHEN x.market_price>0 THEN x.market_price ELSE null END AS market_price,
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
    AND x.card_variant_id IS NOT NULL;

  CREATE INDEX ON _mx_scoped_roster(
    market_key,market_price DESC NULLS LAST,card_variant_id
  );
  ANALYZE _mx_scoped_roster;

  -- Reconcile BOTH dimensions independently:
  --   identity coverage -> expected_card_count
  --   priced subtotal   -> priced_card_count + set_value
  WITH rollup AS (
    SELECT
      market_key,
      count(*)::integer AS roster_count,
      count(*) FILTER (WHERE market_price IS NOT NULL)::integer AS priced_count,
      count(DISTINCT canonical_card_id)::integer AS canonical_count,
      count(DISTINCT card_variant_id)::integer AS variant_count,
      round(coalesce(sum(market_price),0),2) AS known_value
    FROM _mx_scoped_roster
    GROUP BY market_key
  )
  SELECT count(*)::integer INTO v_bad
  FROM _mx_scoped_current c
  LEFT JOIN rollup r USING(market_key)
  WHERE r.market_key IS NULL
     OR r.roster_count<>c.expected_card_count
     OR r.canonical_count<>c.expected_card_count
     OR r.variant_count<>c.expected_card_count
     OR r.priced_count<>c.priced_card_count
     OR r.known_value<>round(c.set_value,2);

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
    p_generation_id,c.market_key,'cards',c.expected_card_count,'available',null
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
      'priceStatus',case when r.market_price is null then 'unknown' else 'known' end,
      'priceSourceStatus',case
        when r.market_price is null then 'no_qualified_exact_edition_price'
        else 'exact_edition_observation'
      end,
      'valueIncludedInTrackedSubtotal',(r.market_price is not null),
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
        ORDER BY l.market_price DESC NULLS LAST,l.card_variant_id
      )::integer AS rank
    FROM _mx_scoped_roster l
  ) r;
  GET DIAGNOSTICS v_roster_rows=ROW_COUNT;

  DELETE FROM public.pokemon_market_explorer_surface_history_v2 x
  USING _mx_scoped_current c
  WHERE x.generation_id=p_generation_id
    AND x.market_key=c.market_key;

  -- Price-performance history remains stricter than the current snapshot. It
  -- requires a complete current basket AND the existing independent history
  -- certification. This prevents changing missingness from masquerading as a
  -- market return.
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
      constituent_count=c.expected_card_count,
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
        'certificationStatus',case
          when c.current_complete then 'CERTIFIED'
          else 'PARTIAL_KNOWN_VALUE'
        end,
        'editionAuthority','edition_history_card_prices_as_of_v2',
        'currentScopedValueCertified',c.current_complete,
        'currentValueStatus',case
          when c.current_complete then 'complete'
          else 'partial_known_only'
        end,
        'currentValueDefinition','sum_known_exact_edition_card_prices',
        'expectedCardCount',c.expected_card_count,
        'pricedCardCount',c.priced_card_count,
        'unknownCardCount',c.expected_card_count-c.priced_card_count,
        'coveragePct',c.coverage_pct,
        'unknownPricesExcludedFromTrackedValue',not c.current_complete,
        'genericOrCrossEditionFallbackUsed',false,
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
    'constituentCount',v_roster_rows,
    'historyRows',v_history,
    'currentCompleteMarkets',(
      SELECT count(*) FROM _mx_scoped_current WHERE current_complete
    ),
    'currentPartialMarkets',(
      SELECT count(*) FROM _mx_scoped_current WHERE NOT current_complete
    ),
    'unknownCardCount',(
      SELECT coalesce(sum(expected_card_count-priced_card_count),0)
      FROM _mx_scoped_current
    ),
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
