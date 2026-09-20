begin;
set local lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v4_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
 SET work_mem TO '64MB'
AS $function$
with requested_roots as materialized (
  select distinct x.set_id
  from unnest(coalesce(p_set_ids,array[]::uuid[])) as x(set_id)
  where x.set_id is not null
), dates as materialized (
  select gs::date as market_date
  from generate_series(p_start_date,p_end_date,interval '1 day') gs
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
), member_map as materialized (
  select r.set_id as root_set_id,r.set_id as member_set_id
  from requested_roots r
  union
  select r.set_id,child.id
  from requested_roots r
  join public.sets child
    on child.parent_opening_set_id=r.set_id
   and child.counts_toward_parent_set_value=true
), expanded_set_ids as materialized (
  select coalesce(array_agg(distinct m.member_set_id order by m.member_set_id),array[]::uuid[]) as ids
  from member_map m
), canonical_root_days as materialized (
  select r.set_id as root_set_id,d.market_date
  from requested_roots r
  cross join dates d
  join public.pokemon_set_value_daily_history h
    on h.set_id=r.set_id
   and h.snapshot_date=d.market_date
   and h.value_scope='standard'
  where h.source in (
    'canonical_root_set_public_rollout_v1',
    'canonical_root_set_public_rollout_candidate_v1',
    'canonical_root_standard_backfill_v1',
    'canonical_root_set_rollout_v1',
    'price_storage_v2_transition_anchor_v1',
    'price_storage_v2_serving_compatibility_v1'
  )
), canonical_member_days as materialized (
  select c.root_set_id,m.member_set_id,c.market_date
  from canonical_root_days c
  join member_map m on m.root_set_id=c.root_set_id
), legacy_chunks as materialized (
  select r.set_id as root_set_id,
         (p_start_date + (g.n*3))::date as from_date,
         least(p_end_date,(p_start_date + (g.n*3) + 2))::date as through_date
  from requested_roots r
  cross join lateral generate_series(
    0,
    greatest(0,((p_end_date-p_start_date)/3))
  ) as g(n)
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
    and exists (
      select 1
      from dates d
      where d.market_date between (p_start_date + (g.n*3))::date
                              and least(p_end_date,(p_start_date + (g.n*3) + 2))::date
        and not exists (
          select 1
          from canonical_root_days c
          where c.root_set_id=r.set_id
            and c.market_date=d.market_date
        )
    )
), legacy_member_chunks as materialized (
  select lc.root_set_id,lc.from_date,lc.through_date,
         array_agg(m.member_set_id order by m.member_set_id) as member_ids
  from legacy_chunks lc
  join member_map m on m.root_set_id=lc.root_set_id
  group by lc.root_set_id,lc.from_date,lc.through_date
), legacy_base as materialized (
  select b.*
  from legacy_member_chunks lc
  cross join lateral public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    lc.member_ids,lc.from_date,lc.through_date,p_card_ids
  ) b
), near_mint as materialized (
  select c.id
  from public.conditions c
  where c.name='Near Mint'
  order by c.id
  limit 1
), exception_variants as materialized (
  select e.canonical_card_id,e.set_id,e.card_variant_id
  from public.pokemon_cards_daily_constituent_variant_exceptions_v1 e
  cross join expanded_set_ids a
  where e.enabled
    and e.set_id=any(a.ids)
    and (p_card_ids is null or e.canonical_card_id=any(p_card_ids))
), exception_intervals as materialized (
  select ev.canonical_card_id,ev.set_id,price.card_variant_id,
         price.condition_id,price.source,price.currency,price.market_price,
         price.effective_date as valid_from,
         lead(price.effective_date) over(
           partition by price.card_variant_id,price.condition_id,price.source,price.currency
           order by price.effective_date,price.id
         ) as valid_to
  from exception_variants ev
  join public.card_variant_price_events_v2 price
    on price.card_variant_id=ev.card_variant_id
  cross join near_mint nm
  where price.condition_id=nm.id
    and price.currency='USD'
     and price.source='TCGPlayer'
), exception_source_daily as materialized (
  select d.market_date,ei.canonical_card_id,ei.set_id,ei.card_variant_id,
         ei.source,ei.market_price,observed.latest_observed_date,
         row_number() over(
           partition by d.market_date,ei.canonical_card_id
           order by observed.latest_observed_date desc nulls last,
                    ei.source desc,ei.card_variant_id
         ) as source_rank
  from dates d
  join exception_intervals ei
    on ei.valid_from<=d.market_date
   and (ei.valid_to is null or d.market_date<ei.valid_to)
   and ei.market_price>0
  cross join near_mint nm
  join lateral (
    select max(least(r.observed_through,d.market_date)) as latest_observed_date
    from public.card_variant_price_observation_ranges_v2 r
    where r.card_variant_id=ei.card_variant_id
      and r.condition_id=nm.id
      and r.source=ei.source
      and r.currency='USD'
      and r.observed_from<=d.market_date
  ) observed on observed.latest_observed_date is not null
), exception_overlay as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.latest_observed_date as captured_at
  from exception_source_daily x
  where x.source_rank=1
), legacy_compatible as materialized (
  select b.canonical_card_id,b.set_id,b.market_date,b.market_price,
         b.card_variant_id,b.source,b.captured_at
  from legacy_base b
  union all
  select o.canonical_card_id,o.set_id,o.market_date,o.market_price,
         o.card_variant_id,o.source,o.captured_at
  from exception_overlay o
  where not exists (
    select 1
    from legacy_base b
    where b.canonical_card_id=o.canonical_card_id
      and b.market_date=o.market_date
  )
), canonical_raw as materialized (
  select cmd.root_set_id,
         p.canonical_card_id,p.set_id,cmd.market_date,
         p.market_price,p.card_variant_id,p.source,p.captured_at
  from canonical_member_days cmd
  cross join lateral public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(
    cmd.member_set_id,cmd.market_date
  ) p
  where p_card_ids is null or p.canonical_card_id=any(p_card_ids)
), canonical_rows as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.captured_at
  from (
    select c.*,
           row_number() over(
             partition by c.canonical_card_id,c.market_date
             order by c.root_set_id,c.set_id,c.card_variant_id
           ) as rn
    from canonical_raw c
  ) x
  where x.rn=1
)
select l.canonical_card_id,l.set_id,l.market_date,l.market_price,
       l.card_variant_id,l.source,l.captured_at
from legacy_compatible l
where not exists (
  select 1
  from canonical_member_days c
  where c.member_set_id=l.set_id
    and c.market_date=l.market_date
)
union all
select c.canonical_card_id,c.set_id,c.market_date,c.market_price,
       c.card_variant_id,c.source,c.captured_at
from canonical_rows c
order by market_date,canonical_card_id,set_id;
$function$;


-- Preserve existing function shape and selection rules; lock only the source.

CREATE OR REPLACE FUNCTION public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(p_set_id uuid, p_start_date date DEFAULT NULL::date, p_end_date date DEFAULT NULL::date)
 RETURNS TABLE(set_id uuid, snapshot_date date, value_scope text, set_value numeric, priced_card_count integer, total_card_count integer, canonical_card_count integer, linked_card_count integer, included_card_count integer, coverage_pct numeric, source text)
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
     AND r.source='TCGPlayer'
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

commit;
