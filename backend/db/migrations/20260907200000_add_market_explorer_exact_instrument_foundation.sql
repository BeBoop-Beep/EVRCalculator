BEGIN;

ALTER TABLE public.pokemon_market_explorer_query_cache_constituents
  ADD COLUMN IF NOT EXISTS instrument_id uuid;

UPDATE public.pokemon_market_explorer_query_cache_constituents
SET instrument_id = coalesce(
  nullif(item->>'cardVariantId','')::uuid,
  nullif(item->>'sealedProductId','')::uuid,
  nullif(item->>'gradedCardVariantId','')::uuid
)
WHERE instrument_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS pokemon_market_explorer_cache_constituents_instrument_uidx
ON public.pokemon_market_explorer_query_cache_constituents(query_fingerprint, instrument_id);

CREATE INDEX IF NOT EXISTS pokemon_market_explorer_daily_states_variant_date_idx
ON public.pokemon_market_explorer_card_daily_states(card_variant_id, market_date)
INCLUDE (market_price, set_id);

CREATE INDEX IF NOT EXISTS pokemon_market_explorer_daily_states_v2_variant_date_idx
ON public.pokemon_market_explorer_card_daily_states_v2_shadow(card_variant_id, market_date)
INCLUDE (market_price, set_id);

COMMIT;
BEGIN;
DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
);
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
$function$
;
COMMIT;

BEGIN;
DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer);
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
$function$
;
COMMIT;
BEGIN;
DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
);

-- Semantics-preserving planner pushdowns for the daily-candidate scope filters:
--   1. PANEL daily-state scan: push s.market_date BETWEEN p_start_date AND p_end_date
--      down into the join against pokemon_market_explorer_card_daily_states.
--   2. PAYLOAD open-interval metadata scan: push o.set_id = ANY(p_set_ids) down into
--      the join against pokemon_card_variant_market_price_intervals.
-- No result-shape or business-logic change; matches production migration
-- 20260902031454_push_down_market_explorer_daily_scope_filters exactly.

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer,
  p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric, current_constituents jsonb
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET enable_nestloop TO 'off'
SET statement_timeout TO '300s'
AS $function$
WITH coverage_ok AS MATERIALIZED (
  SELECT count(*) = cardinality(p_set_ids) AS ok
  FROM public.pokemon_market_explorer_card_daily_coverage
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
  SELECT o.card_variant_id
  FROM public.pokemon_card_variant_market_price_intervals o
  WHERE o.valid_to IS NULL
    AND (p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 OR o.card_variant_id = ANY(p_card_variant_ids))
    AND o.set_id = ANY(p_set_ids)
    AND (p_card_ids IS NULL OR cardinality(p_card_ids) = 0 OR o.canonical_card_id = ANY(p_card_ids))
    AND (p_segment_ids IS NULL OR cardinality(p_segment_ids) = 0 OR public.market_explorer_rarity_segment(o.rarity) = ANY(p_segment_ids))
    AND (
      p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids) = 0 OR EXISTS (
        SELECT 1
        FROM public.pokemon_card_desirability_links l
        WHERE l.pokemon_canonical_card_id = o.canonical_card_id
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
  JOIN public.pokemon_market_explorer_card_daily_states s
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
        'canonical_card_id', o.canonical_card_id,
        'legacy_card_id', o.legacy_card_id,
        'set_id', o.set_id,
        'card_name', o.card_name,
        'card_number', o.card_number,
        'rarity', o.rarity,
        'edition', o.edition,
        'printing_type', o.printing_type,
        'special_type', o.special_type,
        'image_url', o.image_url,
        'market_date', l.market_date,
        'market_price', l.market_price,
        'rank', l.final_rank
      ) ORDER BY l.final_rank
    ),
    '[]'::jsonb
  ) AS body
  FROM latest l
  JOIN public.pokemon_card_variant_market_price_intervals o
    ON o.card_variant_id = l.card_variant_id
   AND o.valid_to IS NULL
   AND o.set_id = ANY(p_set_ids)
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

create or replace function public.sync_pokemon_market_explorer_query_cache_constituents()
returns trigger
language plpgsql
set search_path to ''
as $$
begin
  if current_setting('market_explorer.skip_constituent_sync', true) = 'on' then
    return new;
  end if;

  delete from public.pokemon_market_explorer_query_cache_constituents
  where query_fingerprint = new.query_fingerprint;

  insert into public.pokemon_market_explorer_query_cache_constituents(
    query_fingerprint, rank, instrument_id, card_variant_id, item
  )
  select
    new.query_fingerprint,
    ordinality::integer,
    coalesce(nullif(value->>'cardVariantId','')::uuid, nullif(value->>'sealedProductId','')::uuid, nullif(value->>'gradedCardVariantId','')::uuid),
    nullif(value->>'cardVariantId','')::uuid,
    value
  from jsonb_array_elements(coalesce(new.current_constituents,'[]'::jsonb))
       with ordinality;

  return new;
end
$$;

create or replace function public.stage_pokemon_market_explorer_query_cache_build(
  p_query_fingerprint text,
  p_build_token uuid,
  p_computed_from date,
  p_computed_through date,
  p_series_payload jsonb,
  p_current_value numeric,
  p_constituent_count bigint,
  p_eligible_universe_count bigint,
  p_current_constituents jsonb
)
returns boolean
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  staged_fingerprint text;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or p_constituent_count is null
     or p_constituent_count < 0
     or jsonb_typeof(coalesce(p_current_constituents,'[]'::jsonb)) <> 'array' then
    return false;
  end if;

  perform set_config('market_explorer.skip_constituent_sync','on', true);

  update public.pokemon_market_explorer_query_cache
  set computed_from = p_computed_from,
      computed_through = p_computed_through,
      series_payload = p_series_payload,
      current_value = p_current_value,
      constituent_count = p_constituent_count,
      eligible_universe_count = p_eligible_universe_count,
      current_constituents = coalesce(p_current_constituents,'[]'::jsonb),
      updated_at = clock_timestamp()
  where query_fingerprint = p_query_fingerprint
    and status = 'building'
    and build_token = p_build_token
    and build_expires_at > clock_timestamp()
  returning query_fingerprint into staged_fingerprint;

  return staged_fingerprint is not null;
end
$$;

create or replace function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(
  p_query_fingerprint text,
  p_build_token uuid,
  p_items jsonb
)
returns integer
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  affected integer := 0;
  item_count integer := 0;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or jsonb_typeof(coalesce(p_items,'[]'::jsonb)) <> 'array' then
    return -1;
  end if;

  item_count := jsonb_array_length(coalesce(p_items,'[]'::jsonb));
  if item_count < 1 or item_count > 1000 then
    return -1;
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_query_cache c
    where c.query_fingerprint = p_query_fingerprint
      and c.status = 'building'
      and c.build_token = p_build_token
      and c.build_expires_at > clock_timestamp()
  ) then
    return -1;
  end if;

  if exists (
    select 1
    from (
      select (value->>'rank')::integer as rank
      from jsonb_array_elements(p_items)
    ) x
    where x.rank is null or x.rank <= 0
  ) then
    return -1;
  end if;

  if exists (
    select 1
    from (
      select (value->>'rank')::integer as rank, count(*) as n
      from jsonb_array_elements(p_items)
      group by 1
      having count(*) > 1
    ) d
  ) then
    return -1;
  end if;

  insert into public.pokemon_market_explorer_query_cache_constituents(
    query_fingerprint, rank, instrument_id, card_variant_id, item
  )
  select
    p_query_fingerprint,
    (value->>'rank')::integer,
    coalesce(nullif(value->>'cardVariantId','')::uuid, nullif(value->>'sealedProductId','')::uuid, nullif(value->>'gradedCardVariantId','')::uuid),
    nullif(value->>'cardVariantId','')::uuid,
    value
  from jsonb_array_elements(p_items)
  on conflict (query_fingerprint, rank) do update
  set instrument_id = excluded.instrument_id,
      card_variant_id = excluded.card_variant_id,
      item = excluded.item;

  get diagnostics affected = row_count;
  return affected;
end
$$;

create or replace function public.trim_pokemon_market_explorer_query_cache_constituent_batch(
  p_query_fingerprint text,
  p_build_token uuid,
  p_keep_through_rank integer,
  p_limit integer default 1000
)
returns integer
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  affected integer := 0;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or p_keep_through_rank < 0
     or p_limit < 1
     or p_limit > 5000 then
    return -1;
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_query_cache c
    where c.query_fingerprint = p_query_fingerprint
      and c.status = 'building'
      and c.build_token = p_build_token
      and c.build_expires_at > clock_timestamp()
  ) then
    return -1;
  end if;

  with doomed as (
    select ctid
    from public.pokemon_market_explorer_query_cache_constituents
    where query_fingerprint = p_query_fingerprint
      and rank > p_keep_through_rank
    order by rank
    limit p_limit
  )
  delete from public.pokemon_market_explorer_query_cache_constituents d
  using doomed
  where d.ctid = doomed.ctid;

  get diagnostics affected = row_count;
  return affected;
end
$$;

create or replace function public.finalize_pokemon_market_explorer_query_cache_build(
  p_query_fingerprint text,
  p_build_token uuid
)
returns boolean
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  expected_count bigint;
  detail_count bigint;
  nonnull_instrument_count bigint;
  unique_instrument_count bigint;
  min_rank integer;
  max_rank integer;
  published_fingerprint text;
begin
  select c.constituent_count
  into expected_count
  from public.pokemon_market_explorer_query_cache c
  where c.query_fingerprint = p_query_fingerprint
    and c.status = 'building'
    and c.build_token = p_build_token
    and c.build_expires_at > clock_timestamp()
  for update;

  if expected_count is null or expected_count < 0 then
    return false;
  end if;

  select count(*)::bigint,
         count(instrument_id)::bigint,
         count(distinct instrument_id)::bigint,
         min(rank),
         max(rank)
  into detail_count, nonnull_instrument_count, unique_instrument_count, min_rank, max_rank
  from public.pokemon_market_explorer_query_cache_constituents
  where query_fingerprint = p_query_fingerprint;

  if expected_count = 0 then
    if detail_count <> 0 then
      return false;
    end if;
  else
    if detail_count <> expected_count
       or nonnull_instrument_count <> expected_count
       or unique_instrument_count <> expected_count
       or min_rank <> 1
       or max_rank <> expected_count then
      return false;
    end if;
  end if;

  update public.pokemon_market_explorer_query_cache
  set status = 'ready',
      last_built_at = clock_timestamp(),
      updated_at = clock_timestamp(),
      build_token = null,
      build_started_at = null,
      build_expires_at = null
  where query_fingerprint = p_query_fingerprint
    and status = 'building'
    and build_token = p_build_token
    and build_expires_at > clock_timestamp()
  returning query_fingerprint into published_fingerprint;

  return published_fingerprint is not null;
end
$$;

revoke all on function public.stage_pokemon_market_explorer_query_cache_build(text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) from public, anon, authenticated;
revoke all on function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,jsonb) from public, anon, authenticated;
revoke all on function public.trim_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,integer,integer) from public, anon, authenticated;
revoke all on function public.finalize_pokemon_market_explorer_query_cache_build(text,uuid) from public, anon, authenticated;

grant execute on function public.stage_pokemon_market_explorer_query_cache_build(text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) to service_role;
grant execute on function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,jsonb) to service_role;
grant execute on function public.trim_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,integer,integer) to service_role;
grant execute on function public.finalize_pokemon_market_explorer_query_cache_build(text,uuid) to service_role;

BEGIN;

DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_filtered_cohort_materialized_series(uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer);
CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  p_set_ids uuid[], p_start_date date, p_end_date date, p_use_v2 boolean,
  p_card_ids uuid[] DEFAULT NULL::uuid[], p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[], p_top_n integer DEFAULT NULL::integer,
  p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
  market_date date, constituent_count bigint, eligible_universe_count bigint,
  basket_value numeric, common_count bigint, common_current_value numeric,
  common_previous_value numeric
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET enable_nestloop TO 'off'
SET statement_timeout TO '300s'
AS $function$
WITH dates AS MATERIALIZED (
  SELECT q.market_date,
         lag(q.market_date) OVER (ORDER BY q.market_date) AS previous_market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
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
        SELECT 1 FROM public.pokemon_card_desirability_links l
        WHERE l.pokemon_canonical_card_id = m.canonical_card_id
          AND l.pokemon_reference_id = ANY(p_pokemon_ids)
      )
    )
),
states AS MATERIALIZED (
  SELECT s.market_date, s.set_id, s.card_variant_id, s.market_price
  FROM public.pokemon_market_explorer_card_daily_states_v2_shadow s
  WHERE p_use_v2 AND s.set_id = ANY(p_set_ids)
    AND s.market_date BETWEEN p_start_date AND p_end_date
  UNION ALL
  SELECT s.market_date, s.set_id, s.card_variant_id, s.market_price
  FROM public.pokemon_market_explorer_card_daily_states s
  WHERE NOT p_use_v2 AND s.set_id = ANY(p_set_ids)
    AND s.market_date BETWEEN p_start_date AND p_end_date
),
panel AS MATERIALIZED (
  SELECT d.market_date, d.previous_market_date, s.card_variant_id, s.market_price
  FROM dates d
  JOIN states s ON s.market_date = d.market_date
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
      OR (sr.release_date IS NOT NULL AND d.market_date >= sr.release_date AND (
        ('new' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date <= 180)
        OR ('recent' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 181 AND 730)
        OR ('established' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date BETWEEN 731 AND 1825)
        OR ('legacy' = ANY(p_release_age_cohort_ids) AND d.market_date - sr.release_date > 1825)
      ))
    )
),
eligible AS MATERIALIZED (
  SELECT p.market_date, count(*)::bigint AS n FROM panel p GROUP BY p.market_date
),
ranked AS MATERIALIZED (
  SELECT p.*, row_number() OVER (
    PARTITION BY p.market_date ORDER BY p.market_price DESC, p.card_variant_id
  ) AS market_rank
  FROM panel p WHERE p_top_n IS NOT NULL
),
selected AS MATERIALIZED (
  SELECT p.*, NULL::bigint AS market_rank FROM panel p WHERE p_top_n IS NULL
  UNION ALL
  SELECT r.* FROM ranked r WHERE r.market_rank <= p_top_n
)
SELECT cur.market_date,
       count(*)::bigint,
       e.n::bigint,
       sum(cur.market_price)::numeric,
       count(prev.card_variant_id)::bigint,
       coalesce(sum(cur.market_price) FILTER (WHERE prev.card_variant_id IS NOT NULL), 0)::numeric,
       coalesce(sum(prev.market_price), 0)::numeric
FROM selected cur
JOIN eligible e ON e.market_date = cur.market_date
LEFT JOIN selected prev
  ON prev.market_date = cur.previous_market_date
 AND prev.card_variant_id = cur.card_variant_id
GROUP BY cur.market_date, e.n
ORDER BY cur.market_date
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) TO service_role;

COMMIT;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]
) TO service_role;
