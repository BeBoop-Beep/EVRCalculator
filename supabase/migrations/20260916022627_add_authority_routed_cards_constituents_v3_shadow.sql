CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v3_shadow(
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
SECURITY INVOKER
SET search_path = ''
SET "TimeZone" = 'America/Phoenix'
SET work_mem = '64MB'
AS $function$
WITH requested_roots AS MATERIALIZED (
  SELECT DISTINCT x.set_id
  FROM unnest(coalesce(p_set_ids, ARRAY[]::uuid[])) AS x(set_id)
  WHERE x.set_id IS NOT NULL
), dates AS MATERIALIZED (
  SELECT gs::date AS market_date
  FROM generate_series(p_start_date, p_end_date, interval '1 day') gs
  WHERE p_start_date IS NOT NULL
    AND p_end_date IS NOT NULL
    AND p_end_date >= p_start_date
), member_map AS MATERIALIZED (
  SELECT r.set_id AS root_set_id, r.set_id AS member_set_id
  FROM requested_roots r
  UNION
  SELECT r.set_id, child.id
  FROM requested_roots r
  JOIN public.sets child
    ON child.parent_opening_set_id = r.set_id
   AND child.counts_toward_parent_set_value = true
), expanded_set_ids AS MATERIALIZED (
  SELECT coalesce(array_agg(DISTINCT m.member_set_id ORDER BY m.member_set_id), ARRAY[]::uuid[]) AS ids
  FROM member_map m
), legacy_base AS MATERIALIZED (
  SELECT b.*
  FROM expanded_set_ids a
  CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    a.ids, p_start_date, p_end_date, p_card_ids
  ) b
), near_mint AS MATERIALIZED (
  SELECT c.id
  FROM public.conditions c
  WHERE c.name = 'Near Mint'
  ORDER BY c.id
  LIMIT 1
), exception_variants AS MATERIALIZED (
  SELECT e.canonical_card_id, e.set_id, e.card_variant_id
  FROM public.pokemon_cards_daily_constituent_variant_exceptions_v1 e
  CROSS JOIN expanded_set_ids a
  WHERE e.enabled
    AND e.set_id = ANY(a.ids)
    AND (p_card_ids IS NULL OR e.canonical_card_id = ANY(p_card_ids))
), exception_intervals AS MATERIALIZED (
  SELECT ev.canonical_card_id, ev.set_id, price.card_variant_id,
         price.condition_id, price.source, price.currency, price.market_price,
         price.effective_date AS valid_from,
         lead(price.effective_date) OVER (
           PARTITION BY price.card_variant_id, price.condition_id, price.source, price.currency
           ORDER BY price.effective_date, price.id
         ) AS valid_to
  FROM exception_variants ev
  JOIN public.card_variant_price_events_v2 price
    ON price.card_variant_id = ev.card_variant_id
  CROSS JOIN near_mint nm
  WHERE price.condition_id = nm.id
    AND price.currency = 'USD'
), exception_source_daily AS MATERIALIZED (
  SELECT d.market_date, ei.canonical_card_id, ei.set_id, ei.card_variant_id,
         ei.source, ei.market_price, observed.latest_observed_date,
         row_number() OVER (
           PARTITION BY d.market_date, ei.canonical_card_id
           ORDER BY observed.latest_observed_date DESC NULLS LAST,
                    ei.source DESC, ei.card_variant_id
         ) AS source_rank
  FROM dates d
  JOIN exception_intervals ei
    ON ei.valid_from <= d.market_date
   AND (ei.valid_to IS NULL OR d.market_date < ei.valid_to)
   AND ei.market_price > 0
  CROSS JOIN near_mint nm
  JOIN LATERAL (
    SELECT max(least(r.observed_through, d.market_date)) AS latest_observed_date
    FROM public.card_variant_price_observation_ranges_v2 r
    WHERE r.card_variant_id = ei.card_variant_id
      AND r.condition_id = nm.id
      AND r.source = ei.source
      AND r.currency = 'USD'
      AND r.observed_from <= d.market_date
  ) observed ON observed.latest_observed_date IS NOT NULL
), exception_overlay AS MATERIALIZED (
  SELECT x.canonical_card_id, x.set_id, x.market_date, x.market_price,
         x.card_variant_id, x.source, x.latest_observed_date AS captured_at
  FROM exception_source_daily x
  WHERE x.source_rank = 1
), legacy_compatible AS MATERIALIZED (
  SELECT b.canonical_card_id, b.set_id, b.market_date, b.market_price,
         b.card_variant_id, b.source, b.captured_at
  FROM legacy_base b
  UNION ALL
  SELECT o.canonical_card_id, o.set_id, o.market_date, o.market_price,
         o.card_variant_id, o.source, o.captured_at
  FROM exception_overlay o
  WHERE NOT EXISTS (
    SELECT 1
    FROM legacy_base b
    WHERE b.canonical_card_id = o.canonical_card_id
      AND b.market_date = o.market_date
  )
), canonical_root_days AS MATERIALIZED (
  SELECT r.set_id AS root_set_id, d.market_date
  FROM requested_roots r
  CROSS JOIN dates d
  JOIN public.pokemon_set_value_daily_history h
    ON h.set_id = r.set_id
   AND h.snapshot_date = d.market_date
   AND h.value_scope = 'standard'
  WHERE h.source IN (
    'canonical_root_set_public_rollout_v1',
    'canonical_root_set_public_rollout_candidate_v1',
    'canonical_root_standard_backfill_v1',
    'canonical_root_set_rollout_v1',
    'price_storage_v2_transition_anchor_v1',
    'price_storage_v2_serving_compatibility_v1'
  )
), canonical_member_days AS MATERIALIZED (
  SELECT c.root_set_id, m.member_set_id, c.market_date
  FROM canonical_root_days c
  JOIN member_map m ON m.root_set_id = c.root_set_id
), canonical_raw AS MATERIALIZED (
  SELECT cmd.root_set_id,
         p.canonical_card_id, p.set_id, cmd.market_date,
         p.market_price, p.card_variant_id, p.source, p.captured_at
  FROM canonical_member_days cmd
  CROSS JOIN LATERAL public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(
    cmd.member_set_id, cmd.market_date
  ) p
  WHERE p_card_ids IS NULL OR p.canonical_card_id = ANY(p_card_ids)
), canonical_rows AS MATERIALIZED (
  SELECT x.canonical_card_id, x.set_id, x.market_date, x.market_price,
         x.card_variant_id, x.source, x.captured_at
  FROM (
    SELECT c.*,
           row_number() OVER (
             PARTITION BY c.canonical_card_id, c.market_date
             ORDER BY c.root_set_id, c.set_id, c.card_variant_id
           ) AS rn
    FROM canonical_raw c
  ) x
  WHERE x.rn = 1
)
SELECT l.canonical_card_id, l.set_id, l.market_date, l.market_price,
       l.card_variant_id, l.source, l.captured_at
FROM legacy_compatible l
WHERE NOT EXISTS (
  SELECT 1
  FROM canonical_member_days c
  WHERE c.member_set_id = l.set_id
    AND c.market_date = l.market_date
)
UNION ALL
SELECT c.canonical_card_id, c.set_id, c.market_date, c.market_price,
       c.card_variant_id, c.source, c.captured_at
FROM canonical_rows c
ORDER BY market_date, canonical_card_id, set_id;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_shadow(uuid[],date,date,uuid[]) TO service_role;
COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_shadow(uuid[],date,date,uuid[]) IS
'Non-serving acceptance shadow. Preserves the existing legacy constituent path, but on root-days whose persisted standard Set Value has accepted canonical-root provenance it substitutes the same root+eligible-subset canonical as-of price authority used by Set Value. Intended to restore the documented Set Value/Cards Index single-basket invariant before any public reader cutover.';
