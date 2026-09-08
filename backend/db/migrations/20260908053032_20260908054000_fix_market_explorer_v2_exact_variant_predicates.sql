BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[], p_pokemon_ids bigint[] DEFAULT NULL::bigint[], p_price_segment_ids text[] DEFAULT NULL::text[], p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer, p_card_variant_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(market_date date, constituent_count bigint, eligible_universe_count bigint, basket_value numeric, common_count bigint, common_current_value numeric, common_previous_value numeric, current_constituents jsonb)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET work_mem TO '64MB'
 SET statement_timeout TO '300s'
AS $function$
with market_dates as materialized (
  select distinct q.market_date
  from public.pokemon_market_date_quality q
  where q.tcg='pokemon' and q.status in ('READY','LEGACY_VERIFIED') and q.market_date between p_start_date and p_end_date
), dates as materialized (
  select d.market_date,
         lag(d.market_date) over(order by d.market_date) previous_market_date,
         max(d.market_date) over() latest_market_date
  from market_dates d
), static_variants as materialized (
  select m.card_variant_id,m.canonical_card_id,m.legacy_card_id,m.set_id,m.card_name,m.card_number,m.rarity,m.edition,m.printing_type,m.special_type,m.image_url
  from public.pokemon_market_explorer_card_current_metadata m
  where m.set_id=any(p_set_ids)
    and (p_card_variant_ids is null or cardinality(p_card_variant_ids)=0 or m.card_variant_id=any(p_card_variant_ids))
    and (p_card_ids is null or cardinality(p_card_ids)=0 or m.canonical_card_id=any(p_card_ids))
    and (p_segment_ids is null or cardinality(p_segment_ids)=0 or public.market_explorer_rarity_segment(m.rarity)=any(p_segment_ids))
    and (
      p_pokemon_ids is null or cardinality(p_pokemon_ids)=0 or exists(
        select 1 from public.pokemon_card_desirability_links l
        where l.pokemon_canonical_card_id=m.canonical_card_id and l.pokemon_reference_id=any(p_pokemon_ids)
      )
    )
), panel as materialized (
  select d.market_date,d.previous_market_date,i.card_variant_id,i.market_price
  from dates d
  join public.pokemon_market_price_intervals_v2_shadow i
    on i.set_id=any(p_set_ids)
   and i.valid_from<=d.market_date
   and (i.valid_to is null or d.market_date<i.valid_to)
  join static_variants v on v.card_variant_id=i.card_variant_id
  join public.sets sr on sr.id=i.set_id
  where (
      p_price_segment_ids is null or cardinality(p_price_segment_ids)=0
      or ('obtainable'=any(p_price_segment_ids) and i.market_price<10)
      or ('intermediate'=any(p_price_segment_ids) and i.market_price>=10 and i.market_price<100)
      or ('premium'=any(p_price_segment_ids) and i.market_price>=100)
    )
    and (
      p_release_age_cohort_ids is null or cardinality(p_release_age_cohort_ids)=0
      or (
        sr.release_date is not null and d.market_date>=sr.release_date and (
          ('new'=any(p_release_age_cohort_ids) and d.market_date-sr.release_date<=180)
          or ('recent'=any(p_release_age_cohort_ids) and d.market_date-sr.release_date between 181 and 730)
          or ('established'=any(p_release_age_cohort_ids) and d.market_date-sr.release_date between 731 and 1825)
          or ('legacy'=any(p_release_age_cohort_ids) and d.market_date-sr.release_date>1825)
        )
      )
    )
), eligible as materialized (
  select market_date,count(*)::bigint n from panel group by market_date
), ranked as materialized (
  select p.*,row_number() over(partition by market_date order by market_price desc,card_variant_id) market_rank
  from panel p where p_top_n is not null
), selected as materialized (
  select p.*,null::bigint market_rank from panel p where p_top_n is null
  union all
  select r.* from ranked r where r.market_rank<=p_top_n
), series as materialized (
  select cur.market_date,
         count(*)::bigint constituent_count,
         e.n::bigint eligible_universe_count,
         sum(cur.market_price)::numeric basket_value,
         count(prev.card_variant_id)::bigint common_count,
         coalesce(sum(cur.market_price) filter(where prev.card_variant_id is not null),0)::numeric common_current_value,
         coalesce(sum(prev.market_price),0)::numeric common_previous_value
  from selected cur
  join eligible e on e.market_date=cur.market_date
  left join selected prev on prev.market_date=cur.previous_market_date and prev.card_variant_id=cur.card_variant_id
  group by cur.market_date,e.n
), latest as materialized (
  select s.*,
         case when s.market_rank is null then row_number() over(order by s.market_price desc,s.card_variant_id) else s.market_rank end final_rank
  from selected s
  join dates d on d.market_date=s.market_date and d.market_date=d.latest_market_date
), payload as materialized (
  select coalesce(jsonb_agg(jsonb_build_object(
      'card_variant_id',l.card_variant_id,
      'canonical_card_id',m.canonical_card_id,
      'legacy_card_id',m.legacy_card_id,
      'set_id',m.set_id,
      'card_name',m.card_name,
      'card_number',m.card_number,
      'rarity',m.rarity,
      'edition',m.edition,
      'printing_type',m.printing_type,
      'special_type',m.special_type,
      'image_url',m.image_url,
      'market_date',l.market_date,
      'market_price',l.market_price,
      'rank',l.final_rank
    ) order by l.final_rank),'[]'::jsonb) body
  from latest l join static_variants m on m.card_variant_id=l.card_variant_id
)
select s.market_date,s.constituent_count,s.eligible_universe_count,s.basket_value,
       s.common_count,s.common_current_value,s.common_previous_value,
       case when s.market_date=d.latest_market_date then p.body else null end current_constituents
from series s join dates d on d.market_date=s.market_date cross join payload p
order by s.market_date;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[], p_pokemon_ids bigint[] DEFAULT NULL::bigint[], p_price_segment_ids text[] DEFAULT NULL::text[], p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer, p_card_variant_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(market_date date, constituent_count bigint, eligible_universe_count bigint, basket_value numeric, common_count bigint, common_current_value numeric, common_previous_value numeric, current_constituents jsonb)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET work_mem TO '64MB'
 SET enable_nestloop TO 'off'
 SET statement_timeout TO '300s'
AS $function$
WITH coverage_ok AS MATERIALIZED (
  SELECT count(*) = cardinality(p_set_ids) AS ok
  FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow
  WHERE set_id = ANY(p_set_ids)
    AND computed_through >= p_end_date
),
dates AS MATERIALIZED (
  SELECT q.market_date,
         lag(q.market_date) OVER (ORDER BY q.market_date) AS previous_market_date,
         max(q.market_date) OVER () AS latest_market_date
  FROM public.pokemon_market_date_quality q
  CROSS JOIN coverage_ok c
  WHERE c.ok
    AND q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED')
    AND q.market_date BETWEEN p_start_date AND p_end_date
),
static_variants AS MATERIALIZED (
  SELECT m.card_variant_id
  FROM public.pokemon_market_explorer_card_current_metadata m
  WHERE m.set_id = ANY(p_set_ids)
    AND (p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 OR m.card_variant_id = ANY(p_card_variant_ids))
    AND (p_card_ids IS NULL OR cardinality(p_card_ids) = 0 OR m.canonical_card_id = ANY(p_card_ids))
    AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0 OR public.market_explorer_rarity_segment(m.rarity) = ANY(p_segment_ids))
    AND (
      p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1
        FROM public.pokemon_card_desirability_links l
        WHERE l.pokemon_canonical_card_id = m.canonical_card_id
          AND l.pokemon_reference_id = ANY(p_pokemon_ids)
      )
    )
),
panel AS MATERIALIZED (
  SELECT d.market_date,
         d.previous_market_date,
         s.card_variant_id,
         s.market_price
  FROM dates d
  JOIN public.pokemon_market_explorer_card_daily_states_v2_shadow s
    ON s.market_date = d.market_date
   AND s.set_id = ANY(p_set_ids)
   AND s.market_date BETWEEN p_start_date AND p_end_date
  JOIN static_variants v ON v.card_variant_id = s.card_variant_id
  JOIN public.sets sr ON sr.id = s.set_id
  WHERE (
      p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids) = 0
      OR ('obtainable' = ANY(p_price_segment_ids) AND s.market_price < 10)
      OR ('intermediate' = ANY(p_price_segment_ids) AND s.market_price >= 10 AND s.market_price < 100)
      OR ('premium' = ANY(p_price_segment_ids) AND s.market_price >= 100)
    )
    AND (
      p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids) = 0
      OR (
        sr.release_date IS NOT NULL
        AND d.market_date >= sr.release_date
        AND (
          ('new' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date <= 180)
          OR ('recent' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 181 AND 730)
          OR ('established' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 731 AND 1825)
          OR ('legacy' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date > 1825)
        )
      )
    )
),
eligible AS MATERIALIZED (
  SELECT market_date, count(*)::bigint AS n
  FROM panel
  GROUP BY market_date
),
ranked AS MATERIALIZED (
  SELECT p.*,
         row_number() OVER (PARTITION BY market_date ORDER BY market_price DESC, card_variant_id) AS market_rank
  FROM panel p
  WHERE p_top_n IS NOT NULL
),
selected AS MATERIALIZED (
  SELECT p.*, NULL::bigint AS market_rank
  FROM panel p
  WHERE p_top_n IS NULL
  UNION ALL
  SELECT r.*
  FROM ranked r
  WHERE r.market_rank <= p_top_n
),
series AS MATERIALIZED (
  SELECT cur.market_date,
         count(*)::bigint AS constituent_count,
         e.n::bigint AS eligible_universe_count,
         sum(cur.market_price)::numeric AS basket_value,
         count(prev.card_variant_id)::bigint AS common_count,
         coalesce(sum(cur.market_price) FILTER (WHERE prev.card_variant_id IS NOT NULL), 0)::numeric AS common_current_value,
         coalesce(sum(prev.market_price), 0)::numeric AS common_previous_value
  FROM selected cur
  JOIN eligible e ON e.market_date = cur.market_date
  LEFT JOIN selected prev
    ON prev.market_date = cur.previous_market_date
   AND prev.card_variant_id = cur.card_variant_id
  GROUP BY cur.market_date, e.n
),
latest AS MATERIALIZED (
  SELECT s.*,
         CASE
           WHEN s.market_rank IS NULL THEN row_number() OVER (ORDER BY s.market_price DESC, s.card_variant_id)
           ELSE s.market_rank
         END AS final_rank
  FROM selected s
  JOIN dates d
    ON d.market_date = s.market_date
   AND d.market_date = d.latest_market_date
),
payload AS MATERIALIZED (
  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'card_variant_id', l.card_variant_id,
        'canonical_card_id', m.canonical_card_id,
        'legacy_card_id', m.legacy_card_id,
        'set_id', m.set_id,
        'card_name', m.card_name,
        'card_number', m.card_number,
        'rarity', m.rarity,
        'edition', m.edition,
        'printing_type', m.printing_type,
        'special_type', m.special_type,
        'image_url', m.image_url,
        'market_date', l.market_date,
        'market_price', l.market_price,
        'rank', l.final_rank
      ) ORDER BY l.final_rank
    ),
    '[]'::jsonb
  ) AS body
  FROM latest l
  JOIN public.pokemon_market_explorer_card_current_metadata m
    ON m.card_variant_id = l.card_variant_id
   AND m.set_id = ANY(p_set_ids)
)
SELECT s.market_date,
       s.constituent_count,
       s.eligible_universe_count,
       s.basket_value,
       s.common_count,
       s.common_current_value,
       s.common_previous_value,
       CASE WHEN s.market_date = d.latest_market_date THEN p.body ELSE NULL END
FROM series s
JOIN dates d ON d.market_date = s.market_date
CROSS JOIN payload p
ORDER BY s.market_date
$function$;

COMMIT;
