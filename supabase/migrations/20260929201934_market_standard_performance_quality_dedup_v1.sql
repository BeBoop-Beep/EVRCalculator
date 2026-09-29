BEGIN;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_standard_performance_adjustments_v1(
  p_through_date date,
  p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '60s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  r record;
  v_processed integer:=0;
  v_remaining integer:=0;
  v_common integer:=0;
  v_comparable integer:=0;
  v_entries integer:=0;
  v_exits integer:=0;
  v_stale integer:=0;
  v_prev_common numeric:=0;
  v_curr_common numeric:=0;
  v_adjusted numeric:=0;
  v_classification text;
BEGIN
  IF p_through_date IS NULL THEN
    RAISE EXCEPTION 'STANDARD_PERFORMANCE_THROUGH_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>100 THEN
    RAISE EXCEPTION 'STANDARD_PERFORMANCE_LIMIT_MUST_BE_1_TO_100';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-standard-performance-adjustments-v1',0)
  ) THEN
    RETURN jsonb_build_object(
      'status','already_running',
      'throughDate',p_through_date,
      'processed',0
    );
  END IF;

  FOR r IN
    WITH accepted AS (
      SELECT
        h.set_id,
        h.market_date,
        h.set_value,
        h.priced_card_count,
        lag(h.market_date) OVER (
          PARTITION BY h.set_id ORDER BY h.market_date
        ) AS previous_market_date,
        lag(h.set_value) OVER (
          PARTITION BY h.set_id ORDER BY h.market_date
        ) AS previous_set_value,
        lag(h.priced_card_count) OVER (
          PARTITION BY h.set_id ORDER BY h.market_date
        ) AS previous_priced_card_count
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.market_scope='standard'
        AND h.market_date>=date '2026-04-23'
        AND h.market_date<=p_through_date
        AND EXISTS (
          SELECT 1
          FROM public.pokemon_market_date_quality q
          WHERE q.tcg='pokemon'
            AND q.market_date=h.market_date
            AND q.status IN ('READY','LEGACY_VERIFIED')
        )
        AND NOT EXISTS (
          SELECT 1
          FROM public.pokemon_edition_split_root_sets_v2 e
          WHERE e.set_id=h.set_id
        )
    ),
    candidates AS (
      SELECT
        a.*,
        (a.set_value/nullif(a.previous_set_value,0)-1)::numeric AS raw_return
      FROM accepted a
      WHERE a.previous_set_value>0
        AND (
          pg_catalog.abs(a.set_value/nullif(a.previous_set_value,0)-1)>=0.05
          OR a.priced_card_count IS DISTINCT FROM a.previous_priced_card_count
        )
    )
    SELECT c.*
    FROM candidates c
    WHERE NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_standard_performance_adjustments_v1 x
      WHERE x.set_id=c.set_id
        AND x.market_date=c.market_date
        AND x.previous_market_date=c.previous_market_date
    )
    ORDER BY c.market_date,c.set_id
    LIMIT p_limit
  LOOP
    WITH previous_prices AS MATERIALIZED (
      SELECT *
      FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
        r.set_id,r.previous_market_date
      )
    ),
    current_prices AS MATERIALIZED (
      SELECT *
      FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
        r.set_id,r.market_date
      )
    ),
    merged AS (
      SELECT
        coalesce(p.canonical_card_id,c.canonical_card_id) AS canonical_card_id,
        p.market_price AS previous_price,
        c.market_price AS current_price,
        p.observed_date AS previous_observed_date,
        c.observed_date AS current_observed_date,
        (
          p.canonical_card_id IS NOT NULL
          AND c.canonical_card_id IS NOT NULL
        ) AS is_common,
        (
          p.canonical_card_id IS NOT NULL
          AND c.canonical_card_id IS NOT NULL
          AND c.observed_date IS NOT NULL
          AND p.observed_date IS NOT NULL
          AND c.observed_date>p.observed_date
          AND (r.previous_market_date-p.observed_date)>30
        ) AS stale_to_fresh_reprice
      FROM previous_prices p
      FULL JOIN current_prices c USING(canonical_card_id)
    )
    SELECT
      count(*) FILTER (WHERE is_common)::integer,
      count(*) FILTER (
        WHERE is_common AND NOT stale_to_fresh_reprice
      )::integer,
      count(*) FILTER (
        WHERE previous_price IS NULL AND current_price IS NOT NULL
      )::integer,
      count(*) FILTER (
        WHERE previous_price IS NOT NULL AND current_price IS NULL
      )::integer,
      count(*) FILTER (WHERE stale_to_fresh_reprice)::integer,
      coalesce(sum(previous_price) FILTER (
        WHERE is_common AND NOT stale_to_fresh_reprice
      ),0)::numeric,
      coalesce(sum(current_price) FILTER (
        WHERE is_common AND NOT stale_to_fresh_reprice
      ),0)::numeric
    INTO
      v_common,v_comparable,v_entries,v_exits,v_stale,
      v_prev_common,v_curr_common
    FROM merged;

    IF v_comparable>0 AND v_prev_common>0 AND v_curr_common>0 THEN
      v_adjusted:=v_curr_common/v_prev_common-1;
    ELSE
      v_adjusted:=0;
    END IF;

    v_classification:=CASE
      WHEN v_comparable=0 OR v_prev_common<=0 OR v_curr_common<=0
        THEN 'NO_COMPARABLE_COHORT'
      WHEN (v_entries>0 OR v_exits>0) AND v_stale>0
        THEN 'MIXED_STRUCTURAL'
      WHEN v_entries>0 OR v_exits>0
        THEN 'COHORT_CHANGE'
      WHEN v_stale>0
        THEN 'STALE_TO_FRESH_REPRICE'
      ELSE 'FRESH_PRICE_MOVE'
    END;

    INSERT INTO public.pokemon_market_standard_performance_adjustments_v1(
      set_id,previous_market_date,market_date,raw_return,adjusted_return,
      classification,common_card_count,comparable_card_count,
      entry_count,exit_count,stale_reprice_excluded_count,
      evidence,methodology_version,updated_at
    ) VALUES (
      r.set_id,r.previous_market_date,r.market_date,r.raw_return,v_adjusted,
      v_classification,v_common,v_comparable,
      v_entries,v_exits,v_stale,
      jsonb_build_object(
        'rawReturnPct',round(r.raw_return*100,6),
        'adjustedReturnPct',round(v_adjusted*100,6),
        'previousSetValue',round(r.previous_set_value,2),
        'currentSetValue',round(r.set_value,2),
        'previousPricedCardCount',r.previous_priced_card_count,
        'currentPricedCardCount',r.priced_card_count,
        'commonCardCount',v_common,
        'comparableCardCount',v_comparable,
        'entryCount',v_entries,
        'exitCount',v_exits,
        'staleRepriceExcludedCount',v_stale,
        'previousComparableValue',round(v_prev_common,2),
        'currentComparableValue',round(v_curr_common,2),
        'largeMoveThresholdPct',5,
        'staleRepriceGapDays',30
      ),
      'standard_common_cohort_stale_reprice_v1',
      pg_catalog.clock_timestamp()
    )
    ON CONFLICT(set_id,market_date) DO UPDATE
    SET previous_market_date=excluded.previous_market_date,
        raw_return=excluded.raw_return,
        adjusted_return=excluded.adjusted_return,
        classification=excluded.classification,
        common_card_count=excluded.common_card_count,
        comparable_card_count=excluded.comparable_card_count,
        entry_count=excluded.entry_count,
        exit_count=excluded.exit_count,
        stale_reprice_excluded_count=excluded.stale_reprice_excluded_count,
        evidence=excluded.evidence,
        methodology_version=excluded.methodology_version,
        updated_at=excluded.updated_at;

    v_processed:=v_processed+1;
  END LOOP;

  WITH accepted AS (
    SELECT
      h.set_id,
      h.market_date,
      h.set_value,
      h.priced_card_count,
      lag(h.market_date) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_market_date,
      lag(h.set_value) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_set_value,
      lag(h.priced_card_count) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_priced_card_count
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_scope='standard'
      AND h.market_date>=date '2026-04-23'
      AND h.market_date<=p_through_date
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=h.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
        WHERE e.set_id=h.set_id
      )
  ),
  candidates AS (
    SELECT a.*
    FROM accepted a
    WHERE a.previous_set_value>0
      AND (
        pg_catalog.abs(a.set_value/nullif(a.previous_set_value,0)-1)>=0.05
        OR a.priced_card_count IS DISTINCT FROM a.previous_priced_card_count
      )
  )
  SELECT count(*)::integer INTO v_remaining
  FROM candidates c
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_standard_performance_adjustments_v1 x
    WHERE x.set_id=c.set_id
      AND x.market_date=c.market_date
      AND x.previous_market_date=c.previous_market_date
  );

  RETURN jsonb_build_object(
    'status',CASE WHEN v_remaining=0 THEN 'complete' ELSE 'partial' END,
    'throughDate',p_through_date,
    'processed',v_processed,
    'remaining',v_remaining,
    'methodologyVersion','standard_common_cohort_stale_reprice_v1'
  );
END;
$function$;

CREATE OR REPLACE VIEW public.pokemon_market_standard_performance_daily_v1
WITH (security_invoker=true)
AS
WITH accepted AS (
  SELECT
    h.set_id,
    h.market_date,
    h.set_value,
    h.expected_card_count,
    h.priced_card_count,
    h.coverage_pct,
    lag(h.market_date) OVER (
      PARTITION BY h.set_id ORDER BY h.market_date
    ) AS previous_market_date,
    lag(h.set_value) OVER (
      PARTITION BY h.set_id ORDER BY h.market_date
    ) AS previous_set_value,
    lag(h.priced_card_count) OVER (
      PARTITION BY h.set_id ORDER BY h.market_date
    ) AS previous_priced_card_count
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.market_scope='standard'
    AND h.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=h.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=h.set_id
    )
),
effective AS (
  SELECT
    a.*,
    coalesce(
      x.adjusted_return,
      CASE
        WHEN a.previous_set_value>0
          THEN a.set_value/a.previous_set_value-1
        ELSE 0
      END
    )::numeric AS daily_return,
    x.classification AS adjustment_classification,
    x.methodology_version AS adjustment_methodology_version
  FROM accepted a
  LEFT JOIN public.pokemon_market_standard_performance_adjustments_v1 x
    ON x.set_id=a.set_id
   AND x.market_date=a.market_date
   AND x.previous_market_date=a.previous_market_date
),
indexed AS (
  SELECT
    e.*,
    (
      100*pg_catalog.exp(
        sum(
          pg_catalog.ln((1+e.daily_return)::numeric)
        ) OVER (
          PARTITION BY e.set_id
          ORDER BY e.market_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )
      )
    )::numeric AS index_value
  FROM effective e
)
SELECT
  set_id,
  market_date,
  set_value AS tracked_value,
  index_value,
  daily_return,
  expected_card_count,
  priced_card_count,
  coverage_pct,
  previous_market_date,
  adjustment_classification,
  coalesce(
    adjustment_methodology_version,
    'standard_common_cohort_stale_reprice_v1'
  ) AS methodology_version
FROM indexed;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO ''
SET statement_timeout TO '120s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  v_refresh jsonb;
  v_missing integer:=0;
  v_markets integer:=0;
  v_history integer:=0;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'STANDARD_SET_PERFORMANCE_ARGUMENTS_REQUIRED';
  END IF;

  v_refresh:=public.refresh_pokemon_market_standard_performance_adjustments_v1(
    p_market_date,100
  );

  WITH accepted AS (
    SELECT
      h.set_id,
      h.market_date,
      h.set_value,
      h.priced_card_count,
      lag(h.market_date) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_market_date,
      lag(h.set_value) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_set_value,
      lag(h.priced_card_count) OVER (
        PARTITION BY h.set_id ORDER BY h.market_date
      ) AS previous_priced_card_count
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_scope='standard'
      AND h.market_date>=date '2026-04-23'
      AND h.market_date<=p_market_date
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=h.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
        WHERE e.set_id=h.set_id
      )
  ),
  candidates AS (
    SELECT a.*
    FROM accepted a
    WHERE a.previous_set_value>0
      AND (
        pg_catalog.abs(a.set_value/nullif(a.previous_set_value,0)-1)>=0.05
        OR a.priced_card_count IS DISTINCT FROM a.previous_priced_card_count
      )
  )
  SELECT count(*)::integer INTO v_missing
  FROM candidates c
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_standard_performance_adjustments_v1 x
    WHERE x.set_id=c.set_id
      AND x.market_date=c.market_date
      AND x.previous_market_date=c.previous_market_date
  );

  IF v_missing>0 THEN
    RAISE EXCEPTION 'STANDARD_SET_PERFORMANCE_ADJUSTMENTS_INCOMPLETE: %',v_missing;
  END IF;

  DROP TABLE IF EXISTS pg_temp._mx_standard_markets;
  CREATE TEMP TABLE _mx_standard_markets ON COMMIT DROP AS
  SELECT DISTINCT d.market_key,d.set_id
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.asset='cards'
    AND d.scope_kind='set'
    AND d.set_id IS NOT NULL
    AND d.market_key='set:'||d.set_id::text
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e
      WHERE e.set_id=d.set_id
    );

  CREATE UNIQUE INDEX ON _mx_standard_markets(market_key);
  ANALYZE _mx_standard_markets;

  SELECT count(*)::integer INTO v_markets FROM _mx_standard_markets;

  DELETE FROM public.pokemon_market_explorer_surface_history_v2 h
  USING _mx_standard_markets m
  WHERE h.generation_id=p_generation_id
    AND h.market_key=m.market_key;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,
    constituent_count,chain_segment_id
  )
  SELECT
    p_generation_id,
    m.market_key,
    h.market_date,
    h.index_value,
    h.tracked_value,
    h.priced_card_count,
    0
  FROM _mx_standard_markets m
  JOIN public.pokemon_market_standard_performance_daily_v1 h
    ON h.set_id=m.set_id
   AND h.market_date<=p_market_date
  ORDER BY m.market_key,h.market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  WITH stats AS (
    SELECT
      m.market_key,
      min(h.market_date) AS history_start_date,
      max(h.market_date) AS history_end_date,
      count(*)::integer AS history_point_count,
      max(h.index_value) FILTER (WHERE h.market_date=p_market_date) AS current_index_value,
      max(h.tracked_value) FILTER (WHERE h.market_date=p_market_date) AS current_tracked_value
    FROM _mx_standard_markets m
    LEFT JOIN public.pokemon_market_standard_performance_daily_v1 h
      ON h.set_id=m.set_id
     AND h.market_date<=p_market_date
    GROUP BY m.market_key
  )
  UPDATE public.pokemon_market_explorer_surface_directory_v2 d
  SET source_kind='root_standard_common_cohort_v1',
      source_as_of=p_market_date,
      current_index_value=s.current_index_value,
      current_tracked_value=coalesce(s.current_tracked_value,d.current_tracked_value),
      history_available=(s.history_point_count>0),
      history_start_date=s.history_start_date,
      history_end_date=s.history_end_date,
      history_point_count=s.history_point_count,
      definition_version='standard_common_cohort_stale_reprice_v1',
      metadata=coalesce(d.metadata,'{}'::jsonb)||jsonb_build_object(
        'performanceMethodology','standard_common_cohort_stale_reprice_v1',
        'cohortEntryExitNeutralized',true,
        'staleToFreshRepriceNeutralized',true,
        'largeMoveReviewThresholdPct',5,
        'staleRepriceGapDays',30
      ),
      generated_at=pg_catalog.clock_timestamp()
  FROM stats s
  WHERE d.generation_id=p_generation_id
    AND d.market_key=s.market_key;

  RETURN jsonb_build_object(
    'status','READY',
    'marketDate',p_market_date,
    'marketCount',v_markets,
    'historyRows',v_history,
    'adjustmentRefresh',v_refresh,
    'methodologyVersion','standard_common_cohort_stale_reprice_v1'
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_market_standard_performance_adjustments_v1(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_market_standard_performance_adjustments_v1(date,integer)
  TO service_role;
REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_standard_set_performance_v1(uuid,date)
  TO service_role;
REVOKE ALL ON public.pokemon_market_standard_performance_daily_v1
  FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.pokemon_market_standard_performance_daily_v1 TO service_role;

COMMIT;
