begin;
set local lock_timeout = '5s';

CREATE OR REPLACE VIEW public.card_market_usd_latest WITH (security_invoker=true) AS
SELECT c.id AS card_id,
    c.name,
    c.set_id,
    c.rarity,
    cv.id AS variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.market_price,
    latest.currency,
    latest.source,
    latest.last_observed_date AS captured_at,
    latest.last_observation_created_at AS created_at
   FROM ((card_variants cv
     JOIN cards c ON ((c.id = cv.card_id)))
     CROSS JOIN LATERAL ( SELECT current_row.card_variant_id,
            current_row.condition_id,
            current_row.source,
            current_row.currency,
            current_row.event_id,
            current_row.effective_date,
            current_row.state,
            current_row.market_price,
            current_row.high_price,
            current_row.low_price,
            current_row.source_observation_id,
            current_row.updated_at,
            current_row.last_observed_date,
            current_row.last_observation_id,
            current_row.last_observation_created_at
           FROM card_variant_price_current_v2 current_row
          WHERE ((current_row.card_variant_id = cv.id) AND (current_row.currency = 'USD'::text AND current_row.source = 'TCGPlayer'::text))
          ORDER BY current_row.last_observed_date DESC NULLS LAST, current_row.last_observation_created_at DESC NULLS LAST, current_row.last_observation_id DESC NULLS LAST
         LIMIT 1) latest);

CREATE OR REPLACE VIEW public.simulation_input_cards_with_near_mint_price WITH (security_invoker=true) AS
SELECT sic.id,
    sic.calculation_run_id,
    sic.card_id,
    sic.card_variant_id,
    sic.condition_id,
    sic.card_name,
    sic.rarity_bucket,
    sic.price_source,
    sic.price_used,
    sic.captured_at,
    sic.effective_pull_rate,
    sic.ev_contribution,
    sic.created_at,
    current_nm.market_price AS current_near_mint_price,
    current_nm.last_observed_date AS current_near_mint_price_captured_at,
    current_nm.source AS current_near_mint_price_source
   FROM (simulation_input_cards sic
     LEFT JOIN LATERAL ( SELECT current_row.market_price,
            current_row.last_observed_date,
            current_row.source,
            current_row.last_observation_created_at,
            current_row.last_observation_id
           FROM card_variant_price_current_v2 current_row
          WHERE ((current_row.card_variant_id = sic.card_variant_id) AND (current_row.condition_id = sic.condition_id) AND (current_row.market_price > (0)::numeric) AND (current_row.currency = 'USD'::text AND current_row.source = 'TCGPlayer'::text))
          ORDER BY current_row.last_observed_date DESC NULLS LAST, current_row.last_observation_created_at DESC NULLS LAST, current_row.last_observation_id DESC NULLS LAST
         LIMIT 1) current_nm ON (true));

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
 SET work_mem TO '64MB'
AS $function$
WITH near_mint AS MATERIALIZED (
    SELECT id FROM public.conditions
    WHERE name='Near Mint' AND abbreviation='NM'
    ORDER BY id LIMIT 1
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
    JOIN public.pokemon_canonical_card_legacy_identity_links link ON link.canonical_card_id=pcc.id
), parent_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
    FROM base_cards pcc
    JOIN public.cards c ON c.set_id=pcc.set_id AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity AS (
    SELECT pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
    FROM base_cards pcc
    JOIN public.card_variants matched_variant ON matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    JOIN public.cards c ON c.id=matched_variant.card_id AND c.set_id=pcc.set_id
    WHERE NOT EXISTS (SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id)
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
    WHERE NOT EXISTS (SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.id)
      AND NOT EXISTS (SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.id)
), resolved AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), variants AS MATERIALIZED (
    SELECT DISTINCT r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,r.legacy_card_id,
           cv.id card_variant_id,cv.printing_type,cv.special_type
    FROM resolved r
    JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
    WHERE (cv.special_type IS NULL OR cv.special_type=''
           OR EXISTS (
               SELECT 1 FROM public.cards c_name
               WHERE c_name.id=r.legacy_card_id
                 AND lower(regexp_replace(coalesce(c_name.name,''),'[^a-zA-Z0-9]+','','g'))='pokeball'
           ))
      AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo','non-holo'))
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
    WHERE e.condition_id=nm.id AND e.currency='USD' AND e.source='TCGPlayer'
), dates AS MATERIALIZED (
    SELECT gs::date market_date
    FROM generate_series(p_start_date,p_end_date,interval '1 day') gs
    WHERE p_start_date IS NOT NULL AND p_end_date IS NOT NULL AND p_end_date>=p_start_date
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
                      CASE WHEN s.special_type IS NULL OR s.special_type='' THEN 0 ELSE 1 END,
                      CASE
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='non-holo' THEN 0
                        WHEN s.rarity IN ('Common','Uncommon') AND s.printing_type='holo' THEN 1
                        WHEN s.printing_type='holo' THEN 0
                        WHEN s.printing_type='non-holo' THEN 1
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

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_resolved_universe(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE plpgsql
 STABLE
 SET "TimeZone" TO 'America/Phoenix'
 SET plan_cache_mode TO 'force_custom_plan'
 SET search_path TO ''
AS $function$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
BEGIN
    IF p_set_ids IS NULL OR array_length(p_set_ids, 1) IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a bounded p_start_date/p_end_date';
    END IF;
    IF p_start_date > p_end_date THEN
        RAISE EXCEPTION 'p_start_date (%) must not be after p_end_date (%)', p_start_date, p_end_date;
    END IF;

    SELECT id INTO v_near_mint_condition_id
    FROM public.conditions WHERE lower(name) = 'near mint' ORDER BY id LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH canonical_checklist AS (
        SELECT pcc.id AS pokemon_canonical_card_id, pcc.set_id AS pokemon_set_id,
               pcc.pokemon_tcg_api_card_id, pcc.name, pcc.number, pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = ANY(p_set_ids)
          AND (p_card_ids IS NULL OR pcc.id = ANY(p_card_ids))
    ),
    canonical_card_links AS (
        SELECT DISTINCT cc.pokemon_canonical_card_id, cc.pokemon_set_id, c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c ON c.set_id = cc.pokemon_set_id
         AND (c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
              OR (lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) =
                      lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                  AND (coalesce(cc.number, '') = coalesce(c.card_number, '')
                       OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                       OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                       OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') =
                           ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0'))))
        UNION
        SELECT DISTINCT cc.pokemon_canonical_card_id, cc.pokemon_set_id, link.legacy_card_id AS card_id
        FROM canonical_checklist cc
        JOIN public.pokemon_canonical_card_legacy_identity_links link
          ON link.canonical_card_id = cc.pokemon_canonical_card_id
    ),
    canonical_variant_links AS (
        SELECT DISTINCT ccl.pokemon_canonical_card_id, ccl.pokemon_set_id, ccl.card_id, cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = ''
               OR EXISTS (
                   SELECT 1 FROM public.cards c_name
                   WHERE c_name.id = ccl.card_id
                     AND lower(regexp_replace(coalesce(c_name.name, ''), '[^a-zA-Z0-9]+', '', 'g')) = 'pokeball'
               ))
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id, pokemon_set_id FROM canonical_variant_links
    ),
    -- Observations that fall INSIDE the requested window.
    in_range AS (
        SELECT cvl.pokemon_canonical_card_id, cvl.pokemon_set_id, cvl.card_variant_id,
               o.id AS observation_id, o.market_price, o.source, o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
              AND o.source = 'TCGPlayer'
          AND o.market_price IS NOT NULL AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at >= p_start_date AND o.captured_at <= p_end_date
    ),
    -- The single observation still in force ON p_start_date. Exactly ONE
    -- lookup per card, where the old implementation did one per card per DAY.
    -- Without it a window opening mid-history would lose every card whose last
    -- price predates it.
    carry_in AS (
        SELECT lc.pokemon_canonical_card_id, lc.pokemon_set_id, prior.card_variant_id,
               prior.observation_id, prior.market_price, prior.source, prior.captured_at
        FROM linked_cards lc
        JOIN LATERAL (
            SELECT cvl.card_variant_id, o.id AS observation_id, o.market_price, o.source, o.captured_at
            FROM canonical_variant_links cvl
            JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
            WHERE cvl.pokemon_canonical_card_id = lc.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.source = 'TCGPlayer'
              AND o.market_price IS NOT NULL AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < p_start_date
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) prior ON true
    ),
    observations AS (
        SELECT * FROM in_range
        UNION ALL
        SELECT * FROM carry_in
    ),
    validity AS (
        SELECT ob.*,
               lead(ob.captured_at) OVER (
                   PARTITION BY ob.pokemon_canonical_card_id
                   ORDER BY ob.captured_at, ob.observation_id
               ) AS superseded_from
        FROM observations ob
    )
    SELECT v.pokemon_canonical_card_id AS canonical_card_id,
           v.pokemon_set_id AS set_id,
           d.market_date, v.market_price, v.card_variant_id, v.source, v.captured_at
    FROM validity v
    JOIN LATERAL (
        SELECT generate_series(
            greatest(v.captured_at, p_start_date),
            least(coalesce(v.superseded_from - 1, p_end_date), p_end_date),
            interval '1 day'
        )::date AS market_date
    ) d ON true
    WHERE coalesce(v.superseded_from - 1, p_end_date) >= p_start_date
    ORDER BY d.market_date, v.pokemon_canonical_card_id;
END;
$function$;

commit;
