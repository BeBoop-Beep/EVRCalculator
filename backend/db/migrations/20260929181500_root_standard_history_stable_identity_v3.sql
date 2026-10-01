BEGIN;

-- Lock historical Standard Set Market identity to the same reviewed legacy
-- identity used by the canonical current-price authority. The prior as-of
-- resolver could match multiple legacy rows sharing one Pokemon TCG API id
-- (for example Holo and Non-Holo records with the same API id) and then switch
-- between those identities based on which one had the freshest observation.
-- That makes historical set values and the Raw parent vulnerable to structural
-- jumps that are not market performance.
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
        CASE
          WHEN pref.preferred_card_variant_id=v.card_variant_id THEN 0
          ELSE 1
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
  'canonical_price_events_v2_root_standard_stable_identity_v2'::text
FROM candidate c
WHERE c.rn=1
ORDER BY c.canonical_card_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_standard_card_prices_as_of_v2(uuid,date)
  TO service_role;

COMMIT;
