CREATE OR REPLACE FUNCTION public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(
    p_set_id uuid,
    p_start_date date DEFAULT NULL::date,
    p_end_date date DEFAULT NULL::date
)
RETURNS TABLE(
    set_id uuid,
    snapshot_date date,
    value_scope text,
    set_value numeric,
    priced_card_count integer,
    total_card_count integer,
    canonical_card_count integer,
    linked_card_count integer,
    included_card_count integer,
    coverage_pct numeric,
    source text
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH near_mint AS MATERIALIZED (
    SELECT id
    FROM public.conditions
    WHERE lower(name)='near mint'
    ORDER BY id
    LIMIT 1
), canonical_checklist AS MATERIALIZED (
    SELECT pcc.set_id,
           pcc.id AS canonical_card_id,
           pcc.pokemon_tcg_api_card_id,
           pcc.name,
           pcc.number,
           pcc.printed_number
    FROM public.pokemon_canonical_cards pcc
    WHERE pcc.set_id=p_set_id
      AND pcc.set_value_eligible=true
), canonical_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS canonical_card_count
    FROM canonical_checklist
    GROUP BY set_id
), canonical_card_links AS MATERIALIZED (
    SELECT DISTINCT cc.set_id,cc.canonical_card_id,c.id AS card_id
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
           OR ltrim(split_part(coalesce(cc.number,''),'/',1),'0')=ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
           OR ltrim(split_part(coalesce(cc.printed_number,''),'/',1),'0')=ltrim(split_part(coalesce(c.card_number,''),'/',1),'0')
         )
       )
     )
    UNION
    SELECT DISTINCT cc.set_id,cc.canonical_card_id,link.legacy_card_id
    FROM canonical_checklist cc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id=cc.canonical_card_id
), canonical_variant_links AS MATERIALIZED (
    SELECT DISTINCT ccl.set_id,ccl.canonical_card_id,ccl.card_id,cv.id AS card_variant_id
    FROM canonical_card_links ccl
    JOIN public.card_variants cv ON cv.card_id=ccl.card_id
    WHERE (
      cv.special_type IS NULL OR cv.special_type=''
      OR EXISTS (
        SELECT 1 FROM public.cards c_name
        WHERE c_name.id=ccl.card_id
          AND lower(regexp_replace(coalesce(c_name.name,''),'[^a-zA-Z0-9]+','','g'))='pokeball'
      )
    )
      AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo','non-holo'))
), linked_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS linked_card_count
    FROM canonical_variant_links
    GROUP BY set_id
), scope_flags AS MATERIALIZED (
    SELECT cc.set_id,cc.canonical_card_id,
           EXISTS (
             SELECT 1
             FROM public.pokemon_card_desirability_links l
             WHERE l.pokemon_canonical_card_id=cc.canonical_card_id
               AND l.is_hit_eligible=true
           ) AS is_hit_eligible
    FROM canonical_checklist cc
), hit_counts AS (
    SELECT set_id,count(DISTINCT canonical_card_id)::integer AS hit_card_count
    FROM scope_flags
    WHERE is_hit_eligible=true
    GROUP BY set_id
), observed_bounds AS (
    SELECT cvl.set_id,
           min(r.observed_from) AS first_observation_date,
           max(r.observed_through) AS latest_observation_date
    FROM canonical_variant_links cvl
    JOIN near_mint nm ON true
    JOIN public.card_variant_price_observation_ranges_v2 r
      ON r.card_variant_id=cvl.card_variant_id
     AND r.condition_id=nm.id
     AND r.currency='USD'
    WHERE EXISTS (
      SELECT 1
      FROM public.card_variant_price_events_v2 e
      WHERE e.card_variant_id=r.card_variant_id
        AND e.condition_id=r.condition_id
        AND e.source=r.source
        AND e.currency=r.currency
        AND e.market_price>0
    )
    GROUP BY cvl.set_id
), requested_bounds AS (
    SELECT b.set_id,
           greatest(b.first_observation_date,coalesce(p_start_date,b.first_observation_date)) AS start_date,
           least(
             CASE WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                  THEN p_end_date ELSE b.latest_observation_date END,
             timezone('America/Phoenix',now())::date
           ) AS end_date
    FROM observed_bounds b
), constituents AS MATERIALIZED (
    SELECT c.canonical_card_id,c.set_id,c.market_date,c.market_price,c.card_variant_id,c.source,c.captured_at,
           sf.is_hit_eligible
    FROM requested_bounds b
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
      ARRAY[b.set_id],b.start_date,b.end_date,NULL::uuid[]
    ) c
    JOIN scope_flags sf
      ON sf.set_id=c.set_id
     AND sf.canonical_card_id=c.canonical_card_id
    WHERE b.start_date<=b.end_date
), standard_aggregated AS (
    SELECT c.set_id,c.market_date AS snapshot_date,'standard'::text AS value_scope,
           round(sum(c.market_price)::numeric,2) AS set_value,
           count(DISTINCT c.canonical_card_id)::integer AS priced_card_count,
           max(cc.canonical_card_count)::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT c.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT c.canonical_card_id)::numeric/nullif(max(cc.canonical_card_count),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:standard:canonical_checklist'::text AS source
    FROM constituents c
    JOIN canonical_counts cc ON cc.set_id=c.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=c.set_id
    GROUP BY c.set_id,c.market_date
), hits_aggregated AS (
    SELECT c.set_id,c.market_date AS snapshot_date,'hits'::text AS value_scope,
           round(sum(c.market_price)::numeric,2) AS set_value,
           count(DISTINCT c.canonical_card_id)::integer AS priced_card_count,
           max(hc.hit_card_count)::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT c.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT c.canonical_card_id)::numeric/nullif(max(hc.hit_card_count),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:hits:canonical_checklist'::text AS source
    FROM constituents c
    JOIN canonical_counts cc ON cc.set_id=c.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=c.set_id
    LEFT JOIN hit_counts hc ON hc.set_id=c.set_id
    WHERE c.is_hit_eligible=true
    GROUP BY c.set_id,c.market_date
), ranked AS MATERIALIZED (
    SELECT c.*,
           row_number() OVER (
             PARTITION BY c.set_id,c.market_date
             ORDER BY c.market_price DESC,c.canonical_card_id
           ) AS price_rank
    FROM constituents c
), top10_aggregated AS (
    SELECT r.set_id,r.market_date AS snapshot_date,'top10'::text AS value_scope,
           round(sum(r.market_price)::numeric,2) AS set_value,
           count(DISTINCT r.canonical_card_id)::integer AS priced_card_count,
           least(10,max(cc.canonical_card_count))::integer AS total_card_count,
           max(cc.canonical_card_count)::integer AS canonical_card_count,
           coalesce(max(lc.linked_card_count),0)::integer AS linked_card_count,
           count(DISTINCT r.canonical_card_id)::integer AS included_card_count,
           round(count(DISTINCT r.canonical_card_id)::numeric/nullif(least(10,max(cc.canonical_card_count)),0)*100,2) AS coverage_pct,
           'price_storage_v2_hybrid_constituents:top10:canonical_checklist'::text AS source
    FROM ranked r
    JOIN canonical_counts cc ON cc.set_id=r.set_id
    LEFT JOIN linked_counts lc ON lc.set_id=r.set_id
    WHERE r.price_rank<=10
    GROUP BY r.set_id,r.market_date
)
SELECT * FROM standard_aggregated
UNION ALL SELECT * FROM hits_aggregated
UNION ALL SELECT * FROM top10_aggregated
ORDER BY snapshot_date,value_scope;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(uuid,date,date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(uuid,date,date) TO postgres, service_role;