CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_shadow(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date,
    p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
    canonical_card_id uuid,
    set_id uuid,
    market_date date,
    market_price numeric,
    card_variant_id uuid,
    source text,
    captured_at date
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
SET work_mem TO '64MB'
AS $function$
WITH near_mint AS MATERIALIZED (
    SELECT id
    FROM public.conditions
    WHERE name='Near Mint' AND abbreviation='NM'
    ORDER BY id
    LIMIT 1
), base_cards AS MATERIALIZED (
    SELECT pcc.*
    FROM public.pokemon_canonical_cards pcc
    WHERE p_set_ids IS NOT NULL
      AND cardinality(p_set_ids)>0
      AND pcc.set_id=ANY(p_set_ids)
      AND pcc.set_value_eligible=true
      AND (p_card_ids IS NULL OR cardinality(p_card_ids)=0 OR pcc.id=ANY(p_card_ids))
), manual_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 identity_rank
    FROM base_cards pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id=pcc.id
), parent_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
    FROM base_cards pcc
    JOIN public.cards c
      ON c.set_id=pcc.set_id
     AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
    FROM base_cards pcc
    JOIN public.card_variants matched_variant
      ON matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    JOIN public.cards c
      ON c.id=matched_variant.card_id
     AND c.set_id=pcc.set_id
    WHERE NOT EXISTS (
        SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id
    )
), name_number_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,2 identity_rank
    FROM base_cards pcc
    JOIN public.cards c
      ON c.set_id=pcc.set_id
     AND lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
     )
    WHERE NOT EXISTS (
        SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id
    )
      AND NOT EXISTS (
        SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.id
    )
), resolved AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), variants AS MATERIALIZED (
    SELECT DISTINCT r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,
           cv.id card_variant_id,cv.printing_type,cv.special_type
    FROM resolved r
    JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
), event_intervals AS MATERIALIZED (
    SELECT e.card_variant_id,e.condition_id,e.source,e.currency,e.market_price,
           e.effective_date valid_from,
           lead(e.effective_date) OVER (
             PARTITION BY e.card_variant_id,e.condition_id,e.source,e.currency
             ORDER BY e.effective_date,e.id
           ) valid_to
    FROM public.card_variant_price_events_v2 e
    JOIN variants v ON v.card_variant_id=e.card_variant_id
    CROSS JOIN near_mint nm
    WHERE e.condition_id=nm.id
      AND e.currency='USD'
), dates AS MATERIALIZED (
    SELECT gs::date market_date
    FROM generate_series(p_start_date,p_end_date,interval '1 day') gs
    WHERE p_start_date IS NOT NULL
      AND p_end_date IS NOT NULL
      AND p_end_date>=p_start_date
), source_daily AS MATERIALIZED (
    SELECT d.market_date,v.canonical_card_id,v.set_id,v.rarity,v.identity_rank,
           v.card_variant_id,v.printing_type,v.special_type,
           ei.source,ei.market_price,obs.latest_observed_date,
           row_number() OVER (
             PARTITION BY d.market_date,v.card_variant_id
             ORDER BY obs.latest_observed_date DESC NULLS LAST,ei.source DESC
           ) source_rank
    FROM dates d
    JOIN variants v ON true
    JOIN event_intervals ei
      ON ei.card_variant_id=v.card_variant_id
     AND ei.valid_from<=d.market_date
     AND (ei.valid_to IS NULL OR d.market_date<ei.valid_to)
     AND ei.market_price>0
    CROSS JOIN near_mint nm
    JOIN LATERAL (
      SELECT max(least(r.observed_through,d.market_date)) latest_observed_date
      FROM public.card_variant_price_observation_ranges_v2 r
      WHERE r.card_variant_id=v.card_variant_id
        AND r.condition_id=nm.id
        AND r.source=ei.source
        AND r.currency='USD'
        AND r.observed_from<=d.market_date
    ) obs ON obs.latest_observed_date IS NOT NULL
), candidate_daily AS MATERIALIZED (
    SELECT s.*,
           row_number() OVER (
             PARTITION BY s.market_date,s.canonical_card_id
             ORDER BY s.identity_rank,
                      s.latest_observed_date DESC NULLS LAST,
                      CASE WHEN s.special_type IS NULL THEN 0 ELSE 1 END,
                      CASE
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='non-holo' THEN 0
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='holo' THEN 1
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='reverse-holo' AND s.special_type IS NULL THEN 2
                        WHEN s.printing_type='holo' THEN 0
                        WHEN s.printing_type='non-holo' THEN 1
                        WHEN s.printing_type='reverse-holo' AND s.special_type IS NULL THEN 2
                        ELSE 9
                      END,
                      CASE WHEN pref.preferred_card_variant_id=s.card_variant_id THEN 0 ELSE 1 END,
                      s.card_variant_id
           ) selection_rank
    FROM source_daily s
    LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
      ON pref.canonical_card_id=s.canonical_card_id
    WHERE s.source_rank=1
)
SELECT c.canonical_card_id,c.set_id,c.market_date,c.market_price,
       c.card_variant_id,c.source,c.latest_observed_date AS captured_at
FROM candidate_daily c
WHERE c.selection_rank=1
ORDER BY c.market_date,c.canonical_card_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[]) TO postgres, service_role;