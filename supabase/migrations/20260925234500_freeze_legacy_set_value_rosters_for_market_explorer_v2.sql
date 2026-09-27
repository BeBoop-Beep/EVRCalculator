BEGIN;

-- Freeze exact physical leaves for legacy generic Set Value rows used by the
-- Raw Market index. This reproduces the historical canonical-checklist
-- selection contract without rewriting Set Value economics.

CREATE OR REPLACE FUNCTION public.freeze_pokemon_market_legacy_set_value_roster_v1(
  p_root_set_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '20s'
SET lock_timeout = '2s'
SET jit = 'off'
AS $function$
DECLARE
  v_near_mint uuid;
  v_methodology text;
  v_expected_value numeric;
  v_expected_count integer;
  v_history_value numeric;
  v_history_count integer;
  v_history_source text;
  v_count integer;
  v_unique_variants integer;
  v_value numeric;
  v_items jsonb;
  v_lock_key bigint;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_ARGUMENTS_REQUIRED';
  END IF;

  SELECT
    h.methodology_version,
    (x->>'setValue')::numeric,
    (x->>'includedCardCount')::integer
  INTO v_methodology,v_expected_value,v_expected_count
  FROM public.pokemon_market_index_daily_history h
  CROSS JOIN LATERAL jsonb_array_elements(h.constituents_json) x
  WHERE h.tcg='pokemon'
    AND h.index_key='raw'
    AND h.market_date=p_market_date
    AND (x->>'setId')::uuid=p_root_set_id
  ORDER BY h.updated_at DESC
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_RAW_ROOT_NOT_FOUND';
  END IF;

  SELECT s.set_value,s.included_card_count,s.source
  INTO v_history_value,v_history_count,v_history_source
  FROM public.pokemon_set_value_daily_history s
  WHERE s.set_id=p_root_set_id
    AND s.snapshot_date=p_market_date
    AND s.value_scope='standard'
  ORDER BY s.updated_at DESC
  LIMIT 1;

  IF NOT FOUND
     OR v_history_source IS DISTINCT FROM
       'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
  THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_SOURCE_NOT_ELIGIBLE';
  END IF;

  IF round(v_history_value,2)<>round(v_expected_value,2)
     OR v_history_count<>v_expected_count
  THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_RAW_HISTORY_MISMATCH';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_value_constituent_publications_v1 p
    WHERE p.root_set_id=p_root_set_id
      AND p.market_date=p_market_date
      AND p.methodology_version=v_methodology
      AND p.status='READY'
      AND p.constituent_count=v_expected_count
      AND round(p.constituent_value,2)=round(v_expected_value,2)
  ) THEN
    RETURN jsonb_build_object(
      'status','already_frozen',
      'setId',p_root_set_id,
      'marketDate',p_market_date,
      'constituentCount',v_expected_count,
      'constituentValue',v_expected_value
    );
  END IF;

  v_lock_key:=pg_catalog.hashtextextended(
    'legacy-set-value-roster:'||p_root_set_id::text||':'||p_market_date::text,
    0
  );
  IF NOT pg_catalog.pg_try_advisory_xact_lock(v_lock_key) THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_ALREADY_ACTIVE' USING ERRCODE='55P03';
  END IF;

  SELECT id INTO v_near_mint
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1;

  IF v_near_mint IS NULL THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_NEAR_MINT_MISSING';
  END IF;

  WITH canonical_checklist AS MATERIALIZED (
    SELECT
      pcc.id AS canonical_card_id,
      pcc.set_id,
      pcc.pokemon_tcg_api_card_id,
      pcc.name,
      pcc.number,
      pcc.printed_number
    FROM public.pokemon_canonical_cards pcc
    WHERE pcc.set_id=p_root_set_id
  ),
  canonical_card_links AS MATERIALIZED (
    SELECT DISTINCT
      cc.canonical_card_id,
      c.id AS card_id
    FROM canonical_checklist cc
    JOIN public.cards c
      ON c.set_id=cc.set_id
     AND (
       c.pokemon_tcg_api_id=cc.pokemon_tcg_api_card_id
       OR (
         lower(regexp_replace(coalesce(cc.name,''),'[[:space:]]+',' ','g'))=
           lower(regexp_replace(coalesce(c.name,''),'[[:space:]]+',' ','g'))
         AND (
           coalesce(cc.number,'')=coalesce(c.card_number,'')
           OR coalesce(cc.printed_number,'')=coalesce(c.card_number,'')
           OR ltrim(split_part(coalesce(cc.number,''),'/',1),'0')=
              ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
           OR ltrim(split_part(coalesce(cc.printed_number,''),'/',1),'0')=
              ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
         )
       )
     )
  ),
  canonical_variant_links AS MATERIALIZED (
    SELECT DISTINCT
      l.canonical_card_id,
      cv.id AS card_variant_id,
      cv.printing_type
    FROM canonical_card_links l
    JOIN public.card_variants cv ON cv.card_id=l.card_id
    WHERE (cv.special_type IS NULL OR cv.special_type='')
      AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo','non-holo'))
  ),
  priced AS MATERIALIZED (
    SELECT
      v0.canonical_card_id,
      p.card_variant_id,
      p.market_price,
      p.captured_at,
      p.source,
      p.printing_type
    FROM (
      SELECT DISTINCT canonical_card_id
      FROM canonical_variant_links
    ) v0
    JOIN LATERAL (
      SELECT
        o.card_variant_id,
        o.market_price,
        timezone('utc',o.captured_at)::date AS captured_at,
        o.source,
        cvl.printing_type
      FROM canonical_variant_links cvl
      JOIN public.card_variant_price_observations o
        ON o.card_variant_id=cvl.card_variant_id
      WHERE cvl.canonical_card_id=v0.canonical_card_id
        AND o.condition_id=v_near_mint
        AND o.market_price IS NOT NULL
        AND o.market_price>0
        AND o.captured_at IS NOT NULL
        AND o.captured_at < ((p_market_date + interval '1 day') AT TIME ZONE 'UTC')
      ORDER BY o.captured_at DESC NULLS LAST,o.id DESC
      LIMIT 1
    ) p ON true
  )
  SELECT
    count(*)::integer,
    count(DISTINCT card_variant_id)::integer,
    round(sum(market_price),2),
    jsonb_agg(
      jsonb_build_object(
        'canonicalCardId',canonical_card_id,
        'cardVariantId',card_variant_id,
        'setId',p_root_set_id,
        'marketPrice',market_price,
        'capturedAt',captured_at,
        'source',source,
        'printingType',printing_type,
        'priceSelectionReason','legacy_canonical_checklist_latest_nm'
      )
      ORDER BY canonical_card_id
    )
  INTO v_count,v_unique_variants,v_value,v_items
  FROM priced;

  IF v_count<>v_expected_count
     OR v_unique_variants<>v_count
     OR round(v_value,2)<>round(v_expected_value,2)
  THEN
    RAISE EXCEPTION
      'LEGACY_SET_VALUE_ROSTER_RECONCILIATION_FAILED: count %/% unique % value %/%',
      v_count,v_expected_count,v_unique_variants,round(v_value,2),round(v_expected_value,2);
  END IF;

  PERFORM public.replace_pokemon_market_set_value_constituents_v1(
    p_root_set_id,
    p_market_date,
    v_methodology,
    v_expected_value,
    v_expected_count,
    'legacy_canonical_checklist_frozen_v1',
    v_items
  );

  RETURN jsonb_build_object(
    'status','frozen',
    'setId',p_root_set_id,
    'marketDate',p_market_date,
    'methodologyVersion',v_methodology,
    'constituentCount',v_count,
    'constituentValue',v_value
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.freeze_pokemon_market_legacy_set_value_roster_v1(uuid,date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.freeze_pokemon_market_legacy_set_value_roster_v1(uuid,date)
TO service_role;

CREATE OR REPLACE FUNCTION public.freeze_pokemon_market_legacy_set_value_rosters_batch_v1(
  p_market_date date,
  p_limit integer DEFAULT 10
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '90s'
SET lock_timeout = '2s'
SET jit = 'off'
AS $function$
DECLARE
  v_root record;
  v_receipt jsonb;
  v_done integer:=0;
  v_failed integer:=0;
  v_failures jsonb:='[]'::jsonb;
  v_remaining integer;
BEGIN
  IF p_market_date IS NULL OR p_limit IS NULL OR p_limit<1 OR p_limit>10 THEN
    RAISE EXCEPTION 'LEGACY_SET_VALUE_ROSTER_BATCH_ARGUMENTS_INVALID';
  END IF;

  FOR v_root IN
    WITH raw AS (
      SELECT h.methodology_version,h.constituents_json
      FROM public.pokemon_market_index_daily_history h
      WHERE h.tcg='pokemon'
        AND h.index_key='raw'
        AND h.market_date=p_market_date
      ORDER BY h.updated_at DESC
      LIMIT 1
    ),
    roots AS (
      SELECT
        raw.methodology_version,
        (x->>'setId')::uuid AS set_id
      FROM raw
      CROSS JOIN LATERAL jsonb_array_elements(raw.constituents_json) x
    )
    SELECT r.set_id
    FROM roots r
    JOIN public.pokemon_set_value_daily_history h
      ON h.set_id=r.set_id
     AND h.snapshot_date=p_market_date
     AND h.value_scope='standard'
     AND h.source=
       'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
    WHERE NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_set_value_constituent_publications_v1 p
      WHERE p.root_set_id=r.set_id
        AND p.market_date=p_market_date
        AND p.methodology_version=r.methodology_version
        AND p.status='READY'
    )
    ORDER BY r.set_id
    LIMIT p_limit
  LOOP
    BEGIN
      v_receipt:=public.freeze_pokemon_market_legacy_set_value_roster_v1(
        v_root.set_id,p_market_date
      );
      v_done:=v_done+1;
    EXCEPTION WHEN OTHERS THEN
      v_failed:=v_failed+1;
      v_failures:=v_failures||jsonb_build_array(jsonb_build_object(
        'setId',v_root.set_id,
        'sqlstate',sqlstate,
        'error',left(sqlerrm,1000)
      ));
    END;
  END LOOP;

  WITH raw AS (
    SELECT h.methodology_version,h.constituents_json
    FROM public.pokemon_market_index_daily_history h
    WHERE h.tcg='pokemon'
      AND h.index_key='raw'
      AND h.market_date=p_market_date
    ORDER BY h.updated_at DESC
    LIMIT 1
  ),
  roots AS (
    SELECT
      raw.methodology_version,
      (x->>'setId')::uuid AS set_id
    FROM raw
    CROSS JOIN LATERAL jsonb_array_elements(raw.constituents_json) x
  )
  SELECT count(*)::integer
  INTO v_remaining
  FROM roots r
  JOIN public.pokemon_set_value_daily_history h
    ON h.set_id=r.set_id
   AND h.snapshot_date=p_market_date
   AND h.value_scope='standard'
   AND h.source=
     'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_value_constituent_publications_v1 p
    WHERE p.root_set_id=r.set_id
      AND p.market_date=p_market_date
      AND p.methodology_version=r.methodology_version
      AND p.status='READY'
  );

  RETURN jsonb_build_object(
    'marketDate',p_market_date,
    'processed',v_done,
    'failed',v_failed,
    'remaining',v_remaining,
    'failures',v_failures
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.freeze_pokemon_market_legacy_set_value_rosters_batch_v1(date,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.freeze_pokemon_market_legacy_set_value_rosters_batch_v1(date,integer)
TO service_role;

COMMIT;
