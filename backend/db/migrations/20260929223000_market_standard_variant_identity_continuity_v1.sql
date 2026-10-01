BEGIN;

-- Standard Set Value is defined on a stable physical-print contract. Historical
-- selection must not jump between holo / non-holo / reverse-holo merely because
-- one variant was observed more recently. Freshness is a price-state tiebreak
-- within the preferred physical print, not an identity selector.

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
stable_current_identity AS (
  SELECT
    pcc.root_set_id,
    pcc.member_set_id,
    pcc.canonical_card_id,
    pcc.rarity,
    latest.legacy_card_id,
    -2 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_market_prices_latest latest
    ON latest.canonical_card_id=pcc.canonical_card_id
   AND latest.set_id=pcc.member_set_id
  WHERE latest.legacy_card_id IS NOT NULL
),
manual_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    link.legacy_card_id,-1 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_legacy_identity_links link
    ON link.canonical_card_id=pcc.canonical_card_id
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s
    WHERE s.canonical_card_id=pcc.canonical_card_id
  )
),
parent_api_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,0 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.member_set_id
   AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s
    WHERE s.canonical_card_id=pcc.canonical_card_id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m
      WHERE m.canonical_card_id=pcc.canonical_card_id
    )
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
    SELECT 1 FROM stable_current_identity s
    WHERE s.canonical_card_id=pcc.canonical_card_id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m
      WHERE m.canonical_card_id=pcc.canonical_card_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM parent_api_identity p
      WHERE p.canonical_card_id=pcc.canonical_card_id
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
    SELECT 1 FROM stable_current_identity s
    WHERE s.canonical_card_id=pcc.canonical_card_id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m
      WHERE m.canonical_card_id=pcc.canonical_card_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM parent_api_identity p
      WHERE p.canonical_card_id=pcc.canonical_card_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM variant_api_identity v
      WHERE v.canonical_card_id=pcc.canonical_card_id
    )
),
resolved AS (
  SELECT * FROM stable_current_identity
  UNION ALL SELECT * FROM manual_identity
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
      PARTITION BY e.card_variant_id ORDER BY e.effective_date,e.id
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
        CASE WHEN pref.preferred_card_variant_id=v.card_variant_id THEN 0 ELSE 1 END,
        obs.latest_observed_date DESC NULLS LAST,
        v.card_variant_id
    ) rn
  FROM variants v
  JOIN event_intervals ei
    ON ei.card_variant_id=v.card_variant_id
   AND ei.valid_from<=p_market_date
   AND (ei.valid_to IS NULL OR p_market_date<ei.valid_to)
   AND ei.market_price>0
  CROSS JOIN near_mint nm
  LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
    ON pref.canonical_card_id=v.canonical_card_id
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
  'canonical_price_events_v2_root_standard_print_identity_v3'::text
FROM candidate c
WHERE c.rn=1
ORDER BY c.canonical_card_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  TO service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(
    p_root_set_id uuid,
    p_start_date date,
    p_end_date date
)
RETURNS TABLE(
  set_id uuid,set_name text,market_scope text,market_date date,set_value numeric,
  expected_card_count integer,priced_card_count integer,coverage_pct numeric,
  certified_on_date boolean,source text
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH root AS (
  SELECT s.id root_set_id,s.name root_set_name
  FROM public.sets s
  WHERE s.id=p_root_set_id
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only,false)=false
),
members AS (
  SELECT r.root_set_id,r.root_set_name,r.root_set_id member_set_id FROM root r
  UNION ALL
  SELECT r.root_set_id,r.root_set_name,c.id
  FROM root r
  JOIN public.sets c
    ON c.parent_opening_set_id=r.root_set_id
   AND c.counts_toward_parent_set_value=true
),
near_mint AS (
  SELECT id FROM public.conditions
  WHERE name='Near Mint' AND abbreviation='NM'
  ORDER BY id LIMIT 1
),
base_cards AS MATERIALIZED (
  SELECT m.root_set_id,m.root_set_name,pcc.*
  FROM members m
  JOIN public.pokemon_canonical_cards pcc ON pcc.set_id=m.member_set_id
  WHERE pcc.set_value_eligible=true
),
expected AS (
  SELECT root_set_id,count(*)::integer expected_card_count
  FROM base_cards GROUP BY root_set_id
),
stable_current_identity AS (
  SELECT
    pcc.id canonical_card_id,pcc.set_id,pcc.rarity,
    latest.legacy_card_id,-2 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_market_prices_latest latest
    ON latest.canonical_card_id=pcc.id
   AND latest.set_id=pcc.set_id
  WHERE latest.legacy_card_id IS NOT NULL
),
manual_identity AS (
  SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_legacy_identity_links link
    ON link.canonical_card_id=pcc.id
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s WHERE s.canonical_card_id=pcc.id
  )
),
parent_api_identity AS (
  SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.set_id AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s WHERE s.canonical_card_id=pcc.id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m WHERE m.canonical_card_id=pcc.id
    )
),
variant_api_identity AS (
  SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
  FROM base_cards pcc
  JOIN public.card_variants mv ON mv.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
  JOIN public.cards c ON c.id=mv.card_id AND c.set_id=pcc.set_id
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s WHERE s.canonical_card_id=pcc.id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m WHERE m.canonical_card_id=pcc.id
    )
    AND NOT EXISTS (
      SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id
    )
),
name_number_identity AS (
  SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,2 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.set_id
   AND lower(regexp_replace(trim(c.name),'\s+',' ','g'))=
       lower(regexp_replace(trim(pcc.name),'\s+',' ','g'))
   AND regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','')
       IN (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
       )
  WHERE NOT EXISTS (
    SELECT 1 FROM stable_current_identity s WHERE s.canonical_card_id=pcc.id
  )
    AND NOT EXISTS (
      SELECT 1 FROM manual_identity m WHERE m.canonical_card_id=pcc.id
    )
    AND NOT EXISTS (
      SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id
    )
    AND NOT EXISTS (
      SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.id
    )
),
resolved AS (
  SELECT * FROM stable_current_identity
  UNION ALL SELECT * FROM manual_identity
  UNION ALL SELECT * FROM parent_api_identity
  UNION ALL SELECT * FROM variant_api_identity
  UNION ALL SELECT * FROM name_number_identity
),
variants AS MATERIALIZED (
  SELECT DISTINCT
    r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,
    cv.id card_variant_id,cv.printing_type,cv.special_type
  FROM resolved r
  JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
),
event_intervals AS MATERIALIZED (
  SELECT
    e.card_variant_id,e.market_price,e.effective_date valid_from,
    lead(e.effective_date) OVER (
      PARTITION BY e.card_variant_id ORDER BY e.effective_date,e.id
    ) valid_to
  FROM public.card_variant_price_events_v2 e
  JOIN variants v ON v.card_variant_id=e.card_variant_id
  CROSS JOIN near_mint nm
  WHERE e.condition_id=nm.id
    AND e.source='TCGPlayer'
    AND e.currency='USD'
),
dates AS MATERIALIZED (
  SELECT q.market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg='pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
    AND q.market_date BETWEEN p_start_date AND p_end_date
),
candidate_daily AS (
  SELECT
    d.market_date,v.canonical_card_id,v.set_id,v.rarity,v.identity_rank,
    v.card_variant_id,v.printing_type,v.special_type,ei.market_price,
    obs.latest_observed_date,
    row_number() OVER (
      PARTITION BY d.market_date,v.canonical_card_id
      ORDER BY
        v.identity_rank,
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
        CASE WHEN pref.preferred_card_variant_id=v.card_variant_id THEN 0 ELSE 1 END,
        obs.latest_observed_date DESC NULLS LAST,
        v.card_variant_id
    ) rn
  FROM dates d
  JOIN variants v ON true
  JOIN event_intervals ei
    ON ei.card_variant_id=v.card_variant_id
   AND ei.valid_from<=d.market_date
   AND (ei.valid_to IS NULL OR d.market_date<ei.valid_to)
   AND ei.market_price>0
  CROSS JOIN near_mint nm
  LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
    ON pref.canonical_card_id=v.canonical_card_id
  LEFT JOIN LATERAL (
    SELECT max(least(r.observed_through,d.market_date)) latest_observed_date
    FROM public.card_variant_price_observation_ranges_v2 r
    WHERE r.card_variant_id=v.card_variant_id
      AND r.condition_id=nm.id
      AND r.source='TCGPlayer'
      AND r.currency='USD'
      AND r.observed_from<=d.market_date
  ) obs ON true
),
selected AS (
  SELECT * FROM candidate_daily WHERE rn=1
),
aggregated AS (
  SELECT
    r.root_set_id set_id,
    r.root_set_name set_name,
    'standard'::text market_scope,
    s.market_date,
    round(sum(s.market_price),2) set_value,
    max(e.expected_card_count)::integer expected_card_count,
    count(s.market_price)::integer priced_card_count,
    round(count(s.market_price)::numeric/nullif(max(e.expected_card_count),0)::numeric*100,2) coverage_pct,
    (max(e.expected_card_count)>0 AND count(s.market_price)=max(e.expected_card_count)) certified_on_date,
    'canonical_price_events_v2_root_standard_print_identity_v3'::text source
  FROM root r
  JOIN expected e ON e.root_set_id=r.root_set_id
  JOIN selected s ON true
  GROUP BY r.root_set_id,r.root_set_name,s.market_date
)
SELECT * FROM aggregated ORDER BY market_date;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(uuid,date,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(uuid,date,date)
  TO postgres,service_role;

ALTER TABLE public.pokemon_market_standard_performance_adjustments_v1
  ADD COLUMN IF NOT EXISTS variant_change_count integer NOT NULL DEFAULT 0;

ALTER TABLE public.pokemon_market_standard_performance_adjustments_v1
  DROP CONSTRAINT IF EXISTS pokemon_market_standard_performance_variant_change_count_check;
ALTER TABLE public.pokemon_market_standard_performance_adjustments_v1
  ADD CONSTRAINT pokemon_market_standard_performance_variant_change_count_check
  CHECK (variant_change_count>=0);

ALTER TABLE public.pokemon_market_standard_performance_adjustments_v1
  DROP CONSTRAINT IF EXISTS pokemon_market_standard_performance_adjust_classification_check;
ALTER TABLE public.pokemon_market_standard_performance_adjustments_v1
  ADD CONSTRAINT pokemon_market_standard_performance_adjust_classification_check
  CHECK (classification IN (
    'COHORT_CHANGE',
    'VARIANT_IDENTITY_CHANGE',
    'STALE_TO_FRESH_REPRICE',
    'MIXED_STRUCTURAL',
    'FRESH_PRICE_MOVE',
    'NO_COMPARABLE_COHORT'
  ));

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
  v_variant_changes integer:=0;
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
        h.set_id,h.market_date,h.set_value,h.priced_card_count,
        lag(h.market_date) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_market_date,
        lag(h.set_value) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_set_value,
        lag(h.priced_card_count) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_priced_card_count
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
      WHERE h.market_scope='standard'
        AND h.market_date>=date '2026-04-23'
        AND h.market_date<=p_through_date
        AND EXISTS (
          SELECT 1 FROM public.pokemon_market_date_quality q
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
      SELECT a.*,(a.set_value/nullif(a.previous_set_value,0)-1)::numeric AS raw_return
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
        AND x.methodology_version='standard_common_cohort_variant_identity_v2'
    )
    ORDER BY c.market_date,c.set_id
    LIMIT p_limit
  LOOP
    WITH previous_prices AS MATERIALIZED (
      SELECT * FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
        r.set_id,r.previous_market_date
      )
    ),
    current_prices AS MATERIALIZED (
      SELECT * FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
        r.set_id,r.market_date
      )
    ),
    merged AS (
      SELECT
        coalesce(p.canonical_card_id,c.canonical_card_id) AS canonical_card_id,
        p.card_variant_id AS previous_variant_id,
        c.card_variant_id AS current_variant_id,
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
          AND p.card_variant_id IS DISTINCT FROM c.card_variant_id
        ) AS variant_changed,
        (
          p.canonical_card_id IS NOT NULL
          AND c.canonical_card_id IS NOT NULL
          AND p.card_variant_id=c.card_variant_id
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
        WHERE is_common AND NOT variant_changed AND NOT stale_to_fresh_reprice
      )::integer,
      count(*) FILTER (WHERE previous_price IS NULL AND current_price IS NOT NULL)::integer,
      count(*) FILTER (WHERE previous_price IS NOT NULL AND current_price IS NULL)::integer,
      count(*) FILTER (WHERE stale_to_fresh_reprice)::integer,
      count(*) FILTER (WHERE variant_changed)::integer,
      coalesce(sum(previous_price) FILTER (
        WHERE is_common AND NOT variant_changed AND NOT stale_to_fresh_reprice
      ),0)::numeric,
      coalesce(sum(current_price) FILTER (
        WHERE is_common AND NOT variant_changed AND NOT stale_to_fresh_reprice
      ),0)::numeric
    INTO
      v_common,v_comparable,v_entries,v_exits,v_stale,v_variant_changes,
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
      WHEN (v_entries>0 OR v_exits>0) AND (v_stale>0 OR v_variant_changes>0)
        THEN 'MIXED_STRUCTURAL'
      WHEN v_stale>0 AND v_variant_changes>0
        THEN 'MIXED_STRUCTURAL'
      WHEN v_variant_changes>0
        THEN 'VARIANT_IDENTITY_CHANGE'
      WHEN v_entries>0 OR v_exits>0
        THEN 'COHORT_CHANGE'
      WHEN v_stale>0
        THEN 'STALE_TO_FRESH_REPRICE'
      ELSE 'FRESH_PRICE_MOVE'
    END;

    INSERT INTO public.pokemon_market_standard_performance_adjustments_v1(
      set_id,previous_market_date,market_date,raw_return,adjusted_return,
      classification,common_card_count,comparable_card_count,
      entry_count,exit_count,stale_reprice_excluded_count,variant_change_count,
      evidence,methodology_version,updated_at
    ) VALUES (
      r.set_id,r.previous_market_date,r.market_date,r.raw_return,v_adjusted,
      v_classification,v_common,v_comparable,
      v_entries,v_exits,v_stale,v_variant_changes,
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
        'variantChangeCount',v_variant_changes,
        'previousComparableValue',round(v_prev_common,2),
        'currentComparableValue',round(v_curr_common,2),
        'largeMoveThresholdPct',5,
        'staleRepriceGapDays',30,
        'printIdentityStable',true
      ),
      'standard_common_cohort_variant_identity_v2',
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
        variant_change_count=excluded.variant_change_count,
        evidence=excluded.evidence,
        methodology_version=excluded.methodology_version,
        updated_at=excluded.updated_at;

    v_processed:=v_processed+1;
  END LOOP;

  WITH accepted AS (
    SELECT
      h.set_id,h.market_date,h.set_value,h.priced_card_count,
      lag(h.market_date) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_market_date,
      lag(h.set_value) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_set_value,
      lag(h.priced_card_count) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_priced_card_count
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_scope='standard'
      AND h.market_date>=date '2026-04-23'
      AND h.market_date<=p_through_date
      AND EXISTS (
        SELECT 1 FROM public.pokemon_market_date_quality q
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
      AND x.methodology_version='standard_common_cohort_variant_identity_v2'
  );

  RETURN jsonb_build_object(
    'status',CASE WHEN v_remaining=0 THEN 'complete' ELSE 'partial' END,
    'throughDate',p_through_date,
    'processed',v_processed,
    'remaining',v_remaining,
    'methodologyVersion','standard_common_cohort_variant_identity_v2'
  );
END;
$function$;

CREATE OR REPLACE VIEW public.pokemon_market_standard_performance_daily_v1
WITH (security_invoker=true)
AS
WITH accepted AS (
  SELECT
    h.set_id,h.market_date,h.set_value,h.expected_card_count,h.priced_card_count,h.coverage_pct,
    lag(h.market_date) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_market_date,
    lag(h.set_value) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_set_value,
    lag(h.priced_card_count) OVER (PARTITION BY h.set_id ORDER BY h.market_date) AS previous_priced_card_count
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.market_scope='standard'
    AND h.market_date>=date '2026-04-23'
    AND EXISTS (
      SELECT 1 FROM public.pokemon_market_date_quality q
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
      CASE WHEN a.previous_set_value>0 THEN a.set_value/a.previous_set_value-1 ELSE 0 END
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
        sum(pg_catalog.ln((1+e.daily_return)::numeric))
        OVER (
          PARTITION BY e.set_id
          ORDER BY e.market_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )
      )
    )::numeric AS index_value
  FROM effective e
)
SELECT
  set_id,market_date,set_value AS tracked_value,index_value,daily_return,
  expected_card_count,priced_card_count,coverage_pct,previous_market_date,
  adjustment_classification,
  coalesce(adjustment_methodology_version,'standard_common_cohort_variant_identity_v2') AS methodology_version
FROM indexed;

REVOKE ALL ON public.pokemon_market_standard_performance_daily_v1
  FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.pokemon_market_standard_performance_daily_v1 TO service_role;

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(
  p_limit integer DEFAULT 2
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
SET statement_timeout TO '120s'
SET lock_timeout TO '2s'
AS $function$
DECLARE
  r record;
  v_target date;
  v_processed integer:=0;
  v_failed integer:=0;
  v_rows integer:=0;
  v_remaining integer:=0;
  v_failures jsonb:='[]'::jsonb;
BEGIN
  IF p_limit IS NULL OR p_limit<1 OR p_limit>5 THEN
    RAISE EXCEPTION 'STANDARD_IDENTITY_REBUILD_LIMIT_MUST_BE_1_TO_5';
  END IF;

  IF NOT pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-standard-history-identity-v1',0)
  ) THEN
    RETURN jsonb_build_object('status','BLOCKED','errorClass','identity_rebuild_already_running');
  END IF;

  SELECT max(q.market_date) INTO v_target
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED');

  FOR r IN
    SELECT DISTINCT h.set_id
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.market_scope='standard'
      AND h.market_date>=date '2026-04-23'
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=h.set_id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_market_root_set_value_daily_history_v2_shadow done
        WHERE done.set_id=h.set_id
          AND done.market_scope='standard'
          AND done.market_date=v_target
          AND done.source='canonical_price_events_v2_root_standard_print_identity_v3'
      )
    ORDER BY h.set_id
    LIMIT p_limit
  LOOP
    BEGIN
      INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow(
        set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,
        coverage_pct,certified_on_date,source,updated_at
      )
      SELECT
        x.set_id,x.market_scope,x.market_date,x.set_value,x.expected_card_count,x.priced_card_count,
        x.coverage_pct,x.certified_on_date,x.source,pg_catalog.clock_timestamp()
      FROM public.get_pokemon_market_root_set_standard_daily_history_v2_fast_shadow(
        r.set_id,date '2026-04-23',v_target
      ) x
      ON CONFLICT(set_id,market_scope,market_date) DO UPDATE
      SET set_value=excluded.set_value,
          expected_card_count=excluded.expected_card_count,
          priced_card_count=excluded.priced_card_count,
          coverage_pct=excluded.coverage_pct,
          certified_on_date=excluded.certified_on_date,
          source=excluded.source,
          updated_at=excluded.updated_at;
      GET DIAGNOSTICS v_rows=ROW_COUNT;
      v_processed:=v_processed+1;
    EXCEPTION WHEN OTHERS THEN
      v_failed:=v_failed+1;
      v_failures:=v_failures||jsonb_build_array(
        jsonb_build_object('setId',r.set_id,'error',SQLERRM)
      );
    END;
  END LOOP;

  SELECT count(DISTINCT h.set_id)::integer INTO v_remaining
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.market_scope='standard'
    AND h.market_date>=date '2026-04-23'
    AND NOT EXISTS (
      SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=h.set_id
    )
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_set_value_daily_history_v2_shadow done
      WHERE done.set_id=h.set_id
        AND done.market_scope='standard'
        AND done.market_date=v_target
        AND done.source='canonical_price_events_v2_root_standard_print_identity_v3'
    );

  RETURN jsonb_build_object(
    'status',CASE WHEN v_remaining=0 AND v_failed=0 THEN 'COMPLETE' ELSE 'PARTIAL' END,
    'targetDate',v_target,
    'rootsProcessed',v_processed,
    'failedRoots',v_failed,
    'remainingRoots',v_remaining,
    'lastBatchRowsTouched',v_rows,
    'failures',v_failures
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_market_standard_history_identity_batch_v1(integer)
  TO service_role;

COMMIT;
