
BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(
  p_root_set_id uuid,
  p_market_date date
)
RETURNS TABLE(
  root_set_id uuid,
  member_set_id uuid,
  canonical_card_id uuid,
  card_variant_id uuid,
  market_price numeric,
  observed_date date,
  printing_type text,
  special_type text,
  source text
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
SET statement_timeout TO '30s'
AS $function$
WITH root AS (
  SELECT s.id root_set_id
  FROM public.sets s
  WHERE s.id=p_root_set_id
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only,false)=false
),
members AS (
  SELECT r.root_set_id,r.root_set_id member_set_id FROM root r
  UNION ALL
  SELECT r.root_set_id,c.id
  FROM root r
  JOIN public.sets c
    ON c.parent_opening_set_id=r.root_set_id
   AND c.counts_toward_parent_set_value=true
),
near_mint AS (
  SELECT id
  FROM public.conditions
  WHERE name='Near Mint' AND abbreviation='NM'
  ORDER BY id
  LIMIT 1
),
base_cards AS MATERIALIZED (
  SELECT
    m.root_set_id,
    m.member_set_id,
    pcc.id canonical_card_id,
    pcc.pokemon_tcg_api_card_id,
    pcc.name,
    pcc.number,
    pcc.printed_number,
    pcc.rarity
  FROM members m
  JOIN public.pokemon_canonical_cards pcc
    ON pcc.set_id=m.member_set_id
   AND pcc.set_value_eligible=true
),
manual_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    link.legacy_card_id,-1 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_legacy_identity_links link
    ON link.canonical_card_id=pcc.canonical_card_id
),
parent_api_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,0 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.member_set_id
   AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
),
variant_api_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,1 identity_rank
  FROM base_cards pcc
  JOIN public.card_variants mv
    ON mv.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
  JOIN public.cards c
    ON c.id=mv.card_id
   AND c.set_id=pcc.member_set_id
  WHERE NOT EXISTS (
    SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.canonical_card_id
  )
),
name_number_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,2 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.member_set_id
   AND lower(regexp_replace(trim(c.name),'\s+',' ','g'))=
       lower(regexp_replace(trim(pcc.name),'\s+',' ','g'))
   AND regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','')
       IN (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
       )
  WHERE NOT EXISTS (
    SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.canonical_card_id
  )
    AND NOT EXISTS (
      SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.canonical_card_id
    )
),
resolved AS (
  SELECT * FROM manual_identity
  UNION ALL SELECT * FROM parent_api_identity
  UNION ALL SELECT * FROM variant_api_identity
  UNION ALL SELECT * FROM name_number_identity
),
variants AS MATERIALIZED (
  SELECT DISTINCT
    r.root_set_id,r.member_set_id,r.canonical_card_id,r.rarity,r.identity_rank,
    cv.id card_variant_id,cv.printing_type,cv.special_type
  FROM resolved r
  JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
),
event_intervals AS MATERIALIZED (
  SELECT
    e.card_variant_id,
    e.market_price,
    e.effective_date valid_from,
    lead(e.effective_date) OVER (
      PARTITION BY e.card_variant_id ORDER BY e.effective_date
    ) valid_to
  FROM public.card_variant_price_events_v2 e
  JOIN variants v ON v.card_variant_id=e.card_variant_id
  CROSS JOIN near_mint nm
  WHERE e.condition_id=nm.id
    AND e.source='TCGPlayer'
    AND e.currency='USD'
),
candidate AS (
  SELECT
    v.root_set_id,v.member_set_id,v.canonical_card_id,v.rarity,v.identity_rank,
    v.card_variant_id,v.printing_type,v.special_type,ei.market_price,
    obs.latest_observed_date,
    row_number() OVER (
      PARTITION BY v.canonical_card_id
      ORDER BY
        v.identity_rank,
        obs.latest_observed_date DESC NULLS LAST,
        CASE WHEN v.special_type IS NULL THEN 0 ELSE 1 END,
        CASE
          WHEN v.rarity IN ('Common','Uncommon') AND v.printing_type='non-holo' THEN 0
          WHEN v.rarity IN ('Common','Uncommon') AND v.printing_type='holo' THEN 1
          WHEN v.rarity IN ('Common','Uncommon') AND v.printing_type='reverse-holo'
               AND v.special_type IS NULL THEN 2
          WHEN v.printing_type='holo' THEN 0
          WHEN v.printing_type='non-holo' THEN 1
          WHEN v.printing_type='reverse-holo' AND v.special_type IS NULL THEN 2
          ELSE 9
        END,
        v.card_variant_id
    ) rn
  FROM variants v
  JOIN event_intervals ei
    ON ei.card_variant_id=v.card_variant_id
   AND ei.valid_from<=p_market_date
   AND (ei.valid_to IS NULL OR p_market_date<ei.valid_to)
   AND ei.market_price>0
  CROSS JOIN near_mint nm
  LEFT JOIN LATERAL (
    SELECT max(least(r.observed_through,p_market_date)) latest_observed_date
    FROM public.card_variant_price_observation_ranges_v2 r
    WHERE r.card_variant_id=v.card_variant_id
      AND r.condition_id=nm.id
      AND r.source='TCGPlayer'
      AND r.currency='USD'
      AND r.observed_from<=p_market_date
  ) obs ON true
)
SELECT
  c.root_set_id,c.member_set_id,c.canonical_card_id,c.card_variant_id,
  c.market_price,c.latest_observed_date,c.printing_type,c.special_type,
  'canonical_price_events_v2_root_standard_v1'::text
FROM candidate c
WHERE c.rn=1
ORDER BY c.canonical_card_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  TO service_role;

CREATE OR REPLACE FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(
  p_root_set_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '30s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  v_methodology text:='chain_linked_common_cohort_v1';
  v_expected_value numeric;
  v_expected_count integer;
  v_count integer;
  v_unique_variants integer;
  v_unique_canonical integer;
  v_value numeric;
  v_items jsonb;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_ARGUMENTS_REQUIRED';
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=p_root_set_id
  ) THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_VINTAGE_STANDARD_FORBIDDEN';
  END IF;

  SELECT h.set_value,h.priced_card_count
  INTO v_expected_value,v_expected_count
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.set_id=p_root_set_id
    AND h.market_scope='standard'
    AND h.market_date=p_market_date;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_V2_HISTORY_MISSING';
  END IF;

  WITH prices AS MATERIALIZED (
    SELECT *
    FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
      p_root_set_id,p_market_date
    )
  )
  SELECT
    count(*)::integer,
    count(DISTINCT card_variant_id)::integer,
    count(DISTINCT canonical_card_id)::integer,
    round(sum(market_price),2),
    jsonb_agg(
      jsonb_build_object(
        'canonicalCardId',canonical_card_id,
        'cardVariantId',card_variant_id,
        'setId',member_set_id,
        'marketPrice',market_price,
        'capturedAt',observed_date,
        'source',source,
        'printingType',printing_type,
        'specialType',special_type,
        'priceSelectionReason','canonical_price_events_v2_root_standard'
      )
      ORDER BY canonical_card_id
    )
  INTO v_count,v_unique_variants,v_unique_canonical,v_value,v_items
  FROM prices;

  IF v_count<>v_expected_count
     OR v_unique_variants<>v_count
     OR v_unique_canonical<>v_count
     OR round(v_value,2)<>round(v_expected_value,2)
  THEN
    RAISE EXCEPTION
      'ROOT_STANDARD_ROSTER_V2_RECONCILIATION_FAILED: count %/% unique variants % unique canonical % value %/%',
      v_count,v_expected_count,v_unique_variants,v_unique_canonical,
      round(v_value,2),round(v_expected_value,2);
  END IF;

  PERFORM public.replace_pokemon_market_set_value_constituents_v1(
    p_root_set_id,p_market_date,v_methodology,
    v_expected_value,v_expected_count,
    'canonical_price_events_v2_root_standard_frozen_v1',
    v_items
  );

  RETURN jsonb_build_object(
    'status','frozen',
    'source','canonical_price_events_v2_root_standard',
    'setId',p_root_set_id,
    'marketDate',p_market_date,
    'methodologyVersion',v_methodology,
    'constituentCount',v_count,
    'constituentValue',v_value
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)
  TO service_role;

CREATE OR REPLACE FUNCTION public.freeze_pokemon_market_root_standard_rosters_batch_v2(
  p_market_date date,
  p_limit integer DEFAULT 10
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '90s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  r record;
  v_frozen integer:=0;
  v_failed integer:=0;
  v_failures jsonb:='[]'::jsonb;
  v_remaining integer:=0;
BEGIN
  IF p_limit IS NULL OR p_limit<1 OR p_limit>15 THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_BATCH_LIMIT_MUST_BE_1_TO_15';
  END IF;

  FOR r IN
    WITH raw AS (
      SELECT
        (x->>'setId')::uuid set_id,
        (x->>'setValue')::numeric set_value,
        (x->>'includedCardCount')::integer card_count
      FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
      CROSS JOIN LATERAL jsonb_array_elements(h.constituents_json) x
      WHERE h.market_date=p_market_date
        AND x->>'marketScope'='standard'
    )
    SELECT raw.*
    FROM raw
    JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow v
      ON v.set_id=raw.set_id
     AND v.market_scope='standard'
     AND v.market_date=p_market_date
     AND round(v.set_value,2)=round(raw.set_value,2)
     AND v.priced_card_count=raw.card_count
    LEFT JOIN public.pokemon_market_set_value_constituent_publications_v1 p
      ON p.root_set_id=raw.set_id
     AND p.market_date=p_market_date
     AND p.methodology_version='chain_linked_common_cohort_v1'
     AND p.status='READY'
    WHERE p.root_set_id IS NULL
       OR p.constituent_count<>raw.card_count
       OR round(p.constituent_value,2)<>round(raw.set_value,2)
    ORDER BY raw.set_id
    LIMIT p_limit
  LOOP
    BEGIN
      PERFORM public.freeze_pokemon_market_root_standard_roster_v2(
        r.set_id,p_market_date
      );
      v_frozen:=v_frozen+1;
    EXCEPTION WHEN OTHERS THEN
      v_failed:=v_failed+1;
      v_failures:=v_failures || jsonb_build_array(
        jsonb_build_object('setId',r.set_id,'error',SQLERRM)
      );
    END;
  END LOOP;

  WITH raw AS (
    SELECT
      (x->>'setId')::uuid set_id,
      (x->>'setValue')::numeric set_value,
      (x->>'includedCardCount')::integer card_count
    FROM public.pokemon_market_raw_edition_stable_daily_history_v1 h
    CROSS JOIN LATERAL jsonb_array_elements(h.constituents_json) x
    WHERE h.market_date=p_market_date AND x->>'marketScope'='standard'
  )
  SELECT count(*)::integer INTO v_remaining
  FROM raw
  JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow v
    ON v.set_id=raw.set_id
   AND v.market_scope='standard'
   AND v.market_date=p_market_date
   AND round(v.set_value,2)=round(raw.set_value,2)
   AND v.priced_card_count=raw.card_count
  LEFT JOIN public.pokemon_market_set_value_constituent_publications_v1 p
    ON p.root_set_id=raw.set_id
   AND p.market_date=p_market_date
   AND p.methodology_version='chain_linked_common_cohort_v1'
   AND p.status='READY'
  WHERE p.root_set_id IS NULL
     OR p.constituent_count<>raw.card_count
     OR round(p.constituent_value,2)<>round(raw.set_value,2);

  RETURN jsonb_build_object(
    'marketDate',p_market_date,
    'frozen',v_frozen,
    'failed',v_failed,
    'remaining',v_remaining,
    'failures',v_failures
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.freeze_pokemon_market_root_standard_rosters_batch_v2(date,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.freeze_pokemon_market_root_standard_rosters_batch_v2(date,integer)
  TO service_role;

COMMIT;
