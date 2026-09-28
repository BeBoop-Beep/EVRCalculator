
BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_raw_history_backup_20260928
(LIKE public.pokemon_market_raw_edition_stable_daily_history_v1 INCLUDING ALL);

ALTER TABLE public.pokemon_market_raw_history_backup_20260928 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_raw_history_backup_20260928 FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pokemon_market_raw_history_backup_20260928 TO service_role;

INSERT INTO public.pokemon_market_raw_history_backup_20260928
SELECT *
FROM public.pokemon_market_raw_edition_stable_daily_history_v1
ON CONFLICT (market_date) DO NOTHING;

CREATE OR REPLACE FUNCTION public.repair_pokemon_market_root_standard_date_v1(
  p_market_date date,
  p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'pg_catalog','pg_temp'
SET statement_timeout = '45s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  r record;
  v_processed integer := 0;
  v_root_rows integer := 0;
  v_legacy_rows integer := 0;
  v_remaining integer := 0;
BEGIN
  IF p_market_date IS NULL THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_MARKET_DATE_REQUIRED';
  END IF;
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 25 THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_LIMIT_MUST_BE_1_TO_25';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon'
      AND q.market_date=p_market_date
      AND q.status IN ('READY','LEGACY_VERIFIED')
  ) THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_DATE_NOT_ACCEPTED: %', p_market_date;
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-root-standard-history-repair:'||p_market_date::text,0)
  ) THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_REPAIR_ALREADY_RUNNING' USING ERRCODE='55P03';
  END IF;

  FOR r IN
    SELECT a.set_id
    FROM public.pokemon_market_root_authority a
    JOIN public.sets s ON s.id=a.set_id
    WHERE a.activated_market_date<=p_market_date
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
      AND s.parent_opening_set_id IS NULL
      AND coalesce(s.catalog_only,false)=false
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=a.set_id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
        WHERE h.set_id=a.set_id
          AND h.market_scope='standard'
          AND h.market_date=p_market_date
      )
    ORDER BY a.set_id
    LIMIT p_limit
  LOOP
    WITH rebuilt AS MATERIALIZED (
      SELECT *
      FROM public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shad(
        r.set_id,p_market_date,p_market_date
      )
    ),
    upsert_root AS (
      INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
        set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
        coverage_pct,certified_on_date,source,updated_at
      )
      SELECT
        x.set_id,'standard',x.market_date,x.set_value,x.expected_card_count,x.priced_card_count,
        x.coverage_pct,x.certified_on_date,
        'canonical_price_events_v2_root_standard_fast_repair_v1',
        clock_timestamp()
      FROM rebuilt x
      WHERE x.set_value>0 AND x.priced_card_count>0
      ON CONFLICT(set_id,market_scope,market_date) DO UPDATE
      SET set_value=excluded.set_value,
          expected_card_count=excluded.expected_card_count,
          priced_card_count=excluded.priced_card_count,
          coverage_pct=excluded.coverage_pct,
          certified_on_date=excluded.certified_on_date,
          source=excluded.source,
          updated_at=excluded.updated_at
      RETURNING *
    )
    INSERT INTO public.pokemon_set_value_daily_history(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,updated_at
    )
    SELECT
      x.set_id,x.market_date,'standard',x.set_value,x.priced_card_count,x.expected_card_count,
      x.expected_card_count,x.expected_card_count,x.priced_card_count,x.coverage_pct,
      'canonical_price_events_v2_root_standard_fast_repair_v1',
      clock_timestamp()
    FROM upsert_root x
    ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE
    SET set_value=excluded.set_value,
        priced_card_count=excluded.priced_card_count,
        total_card_count=excluded.total_card_count,
        canonical_card_count=excluded.canonical_card_count,
        linked_card_count=excluded.linked_card_count,
        included_card_count=excluded.included_card_count,
        coverage_pct=excluded.coverage_pct,
        source=excluded.source,
        updated_at=excluded.updated_at;

    GET DIAGNOSTICS v_legacy_rows = ROW_COUNT;
    v_root_rows := v_root_rows + v_legacy_rows;
    v_processed := v_processed + 1;
  END LOOP;

  SELECT count(*)::integer INTO v_remaining
  FROM public.pokemon_market_root_authority a
  JOIN public.sets s ON s.id=a.set_id
  WHERE a.activated_market_date<=p_market_date
    AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>p_market_date)
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only,false)=false
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=a.set_id
    )
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.set_id=a.set_id AND h.market_scope='standard' AND h.market_date=p_market_date
    );

  RETURN jsonb_build_object(
    'marketDate',p_market_date,
    'rootsProcessed',v_processed,
    'rowsWritten',v_root_rows,
    'rootsRemaining',v_remaining,
    'status',CASE WHEN v_remaining=0 THEN 'COMPLETE' ELSE 'PARTIAL' END
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.repair_pokemon_market_root_standard_date_v1(date,integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.repair_pokemon_market_root_standard_date_v1(date,integer)
  TO service_role;

CREATE OR REPLACE FUNCTION public.reconcile_pokemon_market_standard_history_batch_v1(
  p_limit integer DEFAULT 20
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'pg_catalog','pg_temp'
SET statement_timeout = '45s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  r record;
  v_processed integer := 0;
  v_rows integer := 0;
  v_total_rows integer := 0;
  v_remaining integer := 0;
BEGIN
  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 25 THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_LIMIT_MUST_BE_1_TO_25';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-standard-history-reconcile-v1',0)
  ) THEN
    RAISE EXCEPTION 'STANDARD_HISTORY_RECONCILE_ALREADY_RUNNING' USING ERRCODE='55P03';
  END IF;

  FOR r IN
    SELECT DISTINCT v.set_id
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
    JOIN public.pokemon_market_root_authority a
      ON a.set_id=v.set_id
     AND a.activated_market_date<=v.market_date
     AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>v.market_date)
    WHERE v.market_scope='standard'
      AND v.market_date>=date '2026-04-23'
      AND EXISTS (
        SELECT 1 FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=v.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=v.set_id
      )
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_set_value_daily_history h
        WHERE h.set_id=v.set_id
          AND h.snapshot_date=v.market_date
          AND h.value_scope='standard'
          AND (
            round(coalesce(h.set_value,0),2) IS DISTINCT FROM round(coalesce(v.set_value,0),2)
            OR coalesce(h.included_card_count,h.priced_card_count,0) IS DISTINCT FROM v.priced_card_count
            OR coalesce(h.total_card_count,0) IS DISTINCT FROM v.expected_card_count
          )
      )
    ORDER BY v.set_id
    LIMIT p_limit
  LOOP
    INSERT INTO public.pokemon_set_value_daily_history(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,updated_at
    )
    SELECT
      v.set_id,v.market_date,'standard',v.set_value,v.priced_card_count,v.expected_card_count,
      v.expected_card_count,v.expected_card_count,v.priced_card_count,v.coverage_pct,
      'canonical_root_standard_history_v2_reconciled_v1',
      clock_timestamp()
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
    WHERE v.set_id=r.set_id
      AND v.market_scope='standard'
      AND v.market_date>=date '2026-04-23'
      AND EXISTS (
        SELECT 1 FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=v.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
    ON CONFLICT(set_id,snapshot_date,value_scope) DO UPDATE
    SET set_value=excluded.set_value,
        priced_card_count=excluded.priced_card_count,
        total_card_count=excluded.total_card_count,
        canonical_card_count=excluded.canonical_card_count,
        linked_card_count=excluded.linked_card_count,
        included_card_count=excluded.included_card_count,
        coverage_pct=excluded.coverage_pct,
        source=excluded.source,
        updated_at=excluded.updated_at
    WHERE round(coalesce(pokemon_set_value_daily_history.set_value,0),2)
            IS DISTINCT FROM round(coalesce(excluded.set_value,0),2)
       OR coalesce(pokemon_set_value_daily_history.included_card_count,
                   pokemon_set_value_daily_history.priced_card_count,0)
            IS DISTINCT FROM excluded.included_card_count
       OR coalesce(pokemon_set_value_daily_history.total_card_count,0)
            IS DISTINCT FROM excluded.total_card_count;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    v_total_rows := v_total_rows + v_rows;
    v_processed := v_processed + 1;
  END LOOP;

  SELECT count(DISTINCT v.set_id)::integer INTO v_remaining
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow v
  JOIN public.pokemon_market_root_authority a
    ON a.set_id=v.set_id
   AND a.activated_market_date<=v.market_date
   AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>v.market_date)
  WHERE v.market_scope='standard'
    AND v.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1 FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=v.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=v.set_id
    )
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_set_value_daily_history h
      WHERE h.set_id=v.set_id
        AND h.snapshot_date=v.market_date
        AND h.value_scope='standard'
        AND (
          round(coalesce(h.set_value,0),2) IS DISTINCT FROM round(coalesce(v.set_value,0),2)
          OR coalesce(h.included_card_count,h.priced_card_count,0) IS DISTINCT FROM v.priced_card_count
          OR coalesce(h.total_card_count,0) IS DISTINCT FROM v.expected_card_count
        )
    );

  RETURN jsonb_build_object(
    'rootsProcessed',v_processed,
    'rowsUpdated',v_total_rows,
    'rootsRemaining',v_remaining,
    'status',CASE WHEN v_remaining=0 THEN 'COMPLETE' ELSE 'PARTIAL' END
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.reconcile_pokemon_market_standard_history_batch_v1(integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_pokemon_market_standard_history_batch_v1(integer)
  TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_raw_edition_stable_history_v1(
  p_through_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'pg_catalog','pg_temp'
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
      h.market_date,
      h.set_value::numeric AS set_value,
      h.priced_card_count::integer AS card_count,
      h.source::text AS source,
      h.updated_at
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    JOIN public.pokemon_market_root_authority a
      ON a.set_id=h.set_id
     AND a.activated_market_date<=h.market_date
     AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>h.market_date)
    WHERE h.market_scope='standard'
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=h.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
      AND h.market_date>=date '2026-04-23'
      AND h.market_date<=p_through_date
      AND h.set_value>0
      AND h.priced_card_count>0
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
    WHERE h.market_scope IN ('first_edition','unlimited','shadowless')
      AND EXISTS (
        SELECT 1
        FROM public.pokemon_market_date_quality q
        WHERE q.tcg='pokemon'
          AND q.market_date=h.market_date
          AND q.status IN ('READY','LEGACY_VERIFIED')
      )
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
      'standardHistoryAuthority','pokemon_market_root_set_value_daily_history_v2_shadow',
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

COMMIT;
