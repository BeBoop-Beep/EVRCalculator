begin;
set local lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.refresh_card_variant_market_metrics_latest()
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
declare
  v_rows integer := 0;
begin
  truncate table public.card_variant_market_metrics_latest;

  insert into public.card_variant_market_metrics_latest (
    card_variant_id,
    card_id,
    set_id,
    condition_id,
    current_market_price,
    current_captured_at,
    delta_1d,
    delta_7d,
    delta_30d,
    delta_3m,
    delta_6m,
    delta_1y,
    delta_lifetime,
    delta_pct_1d,
    delta_pct_7d,
    delta_pct_30d,
    delta_pct_3m,
    delta_pct_6m,
    delta_pct_1y,
    delta_pct_lifetime,
    base_price_1d,
    base_price_7d,
    base_price_30d,
    base_price_3m,
    base_price_6m,
    base_price_1y,
    base_price_lifetime,
    refreshed_at
  )
  with near_mint_condition as (
    select id
    from public.conditions
    where id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'
    limit 1
  ),
  current_rows as (
    select distinct on (h.card_variant_id, h.condition_id)
      h.card_variant_id,
      h.condition_id,
      h.market_price as current_market_price,
      h.captured_at as current_captured_at
    from public.card_variant_price_observations h
    join near_mint_condition nmc
      on nmc.id = h.condition_id
    where h.currency = 'USD'
      and h.source = 'TCGPlayer'
      and h.market_price is not null
    order by
      h.card_variant_id,
      h.condition_id,
      h.captured_at desc,
      h.created_at desc
  ),
  enriched as (
    select
      cr.card_variant_id,
      cv.card_id,
      c.set_id,
      cr.condition_id,
      cr.current_market_price,
      cr.current_captured_at,

      b1d.market_price as base_price_1d,
      b7d.market_price as base_price_7d,
      b30d.market_price as base_price_30d,
      b3m.market_price as base_price_3m,
      b6m.market_price as base_price_6m,
      b1y.market_price as base_price_1y,
      blife.market_price as base_price_lifetime

    from current_rows cr
    join public.card_variants cv
      on cv.id = cr.card_variant_id
    join public.cards c
      on c.id = cv.card_id

    -- 1D: latest price strictly before current observation date
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at < cr.current_captured_at
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b1d on true

    -- 7D: latest price at or before current observation date minus 7 days
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= (cr.current_captured_at - 7)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b7d on true

    -- 30D
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= (cr.current_captured_at - 30)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b30d on true

    -- 3M
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '3 months')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b3m on true

    -- 6M
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '6 months')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b6m on true

    -- 1Y
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
        and h.captured_at <= ((cr.current_captured_at::timestamp - interval '1 year')::date)
      order by h.captured_at desc, h.created_at desc
      limit 1
    ) b1y on true

    -- lifetime earliest known price
    left join lateral (
      select h.market_price
      from public.card_variant_price_observations h
      where h.card_variant_id = cr.card_variant_id
        and h.condition_id = cr.condition_id
        and h.currency = 'USD'
      and h.source = 'TCGPlayer'
        and h.market_price is not null
      order by h.captured_at asc, h.created_at asc
      limit 1
    ) blife on true
  )
  select
    e.card_variant_id,
    e.card_id,
    e.set_id,
    e.condition_id,
    e.current_market_price,
    e.current_captured_at,

    case when e.base_price_1d is null then null else round((e.current_market_price - e.base_price_1d)::numeric, 2) end,
    case when e.base_price_7d is null then null else round((e.current_market_price - e.base_price_7d)::numeric, 2) end,
    case when e.base_price_30d is null then null else round((e.current_market_price - e.base_price_30d)::numeric, 2) end,
    case when e.base_price_3m is null then null else round((e.current_market_price - e.base_price_3m)::numeric, 2) end,
    case when e.base_price_6m is null then null else round((e.current_market_price - e.base_price_6m)::numeric, 2) end,
    case when e.base_price_1y is null then null else round((e.current_market_price - e.base_price_1y)::numeric, 2) end,
    case when e.base_price_lifetime is null then null else round((e.current_market_price - e.base_price_lifetime)::numeric, 2) end,

    case when e.base_price_1d is null or e.base_price_1d = 0 then null else round((((e.current_market_price - e.base_price_1d) / e.base_price_1d) * 100)::numeric, 4) end,
    case when e.base_price_7d is null or e.base_price_7d = 0 then null else round((((e.current_market_price - e.base_price_7d) / e.base_price_7d) * 100)::numeric, 4) end,
    case when e.base_price_30d is null or e.base_price_30d = 0 then null else round((((e.current_market_price - e.base_price_30d) / e.base_price_30d) * 100)::numeric, 4) end,
    case when e.base_price_3m is null or e.base_price_3m = 0 then null else round((((e.current_market_price - e.base_price_3m) / e.base_price_3m) * 100)::numeric, 4) end,
    case when e.base_price_6m is null or e.base_price_6m = 0 then null else round((((e.current_market_price - e.base_price_6m) / e.base_price_6m) * 100)::numeric, 4) end,
    case when e.base_price_1y is null or e.base_price_1y = 0 then null else round((((e.current_market_price - e.base_price_1y) / e.base_price_1y) * 100)::numeric, 4) end,
    case when e.base_price_lifetime is null or e.base_price_lifetime = 0 then null else round((((e.current_market_price - e.base_price_lifetime) / e.base_price_lifetime) * 100)::numeric, 4) end,

    e.base_price_1d,
    e.base_price_7d,
    e.base_price_30d,
    e.base_price_3m,
    e.base_price_6m,
    e.base_price_1y,
    e.base_price_lifetime,
    now()
  from enriched e;

  get diagnostics v_rows = row_count;

  return jsonb_build_object(
    'refreshed_rows', v_rows,
    'table_name', 'card_variant_market_metrics_latest'
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history(p_set_id uuid DEFAULT NULL::uuid, p_start_date date DEFAULT NULL::date, p_end_date date DEFAULT NULL::date)
 RETURNS integer
 LANGUAGE plpgsql
 SET "TimeZone" TO 'America/Phoenix'
 SET search_path TO ''
AS $function$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_rows_upserted INTEGER := 0;
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RAISE NOTICE 'Near Mint condition not found; pokemon_set_value_daily_history refresh skipped.';
        RETURN 0;
    END IF;

    WITH requested_sets AS (
        SELECT id
        FROM public.sets
        WHERE p_set_id IS NULL OR id = p_set_id
    ),
    canonical_checklist AS (
        SELECT
            pcc.set_id,
            pcc.id AS pokemon_canonical_card_id,
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        JOIN requested_sets s ON s.id = pcc.set_id
        WHERE pcc.set_value_eligible = true
    ),
    canonical_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS canonical_card_count
        FROM canonical_checklist
        GROUP BY set_id
    ),
    canonical_card_links AS (
        SELECT DISTINCT cc.set_id, cc.pokemon_canonical_card_id, c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = cc.set_id
         AND (
             c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
             OR (
                 lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) = lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                 AND (
                     coalesce(cc.number, '') = coalesce(c.card_number, '')
                     OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                     OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') = ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                     OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') = ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                 )
             )
         )
        UNION
        SELECT DISTINCT cc.set_id, cc.pokemon_canonical_card_id, link.legacy_card_id AS card_id
        FROM canonical_checklist cc
        JOIN public.pokemon_canonical_card_legacy_identity_links link
          ON link.canonical_card_id = cc.pokemon_canonical_card_id
    ),
    canonical_variant_links AS (
        SELECT DISTINCT ccl.set_id, ccl.pokemon_canonical_card_id, ccl.card_id, cv.id AS card_variant_id
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
    linked_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS linked_card_count
        FROM canonical_variant_links
        GROUP BY set_id
    ),
    canonical_scope_flags AS (
        SELECT
            cc.set_id,
            cc.pokemon_canonical_card_id,
            EXISTS (
                SELECT 1
                FROM public.pokemon_card_desirability_links link
                WHERE link.pokemon_canonical_card_id = cc.pokemon_canonical_card_id
                  AND link.is_hit_eligible = true
            ) AS is_hit_eligible
        FROM canonical_checklist cc
    ),
    hit_counts AS (
        SELECT set_id, count(DISTINCT pokemon_canonical_card_id)::integer AS hit_card_count
        FROM canonical_scope_flags
        WHERE is_hit_eligible = true
        GROUP BY set_id
    ),
    observed_bounds AS (
        SELECT
            cvl.set_id,
            min(o.captured_at) AS first_observation_date,
            max(o.captured_at) AS latest_observation_date
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl.card_variant_id
          AND o.source = 'TCGPlayer'
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
        GROUP BY cvl.set_id
    ),
    set_dates AS (
        SELECT b.set_id, generated_day::date AS snapshot_date
        FROM observed_bounds b
        CROSS JOIN LATERAL generate_series(
            greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date)),

least(
                CASE
                    WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                        THEN p_end_date
                    ELSE b.latest_observation_date
                END,
                timezone(v_set_value_market_day_timezone, now())::date
            )
,
            interval '1 day'
        ) AS generated_day
        WHERE greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date))
              <=
least(
                CASE
                    WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL
                        THEN p_end_date
                    ELSE b.latest_observation_date
                END,
                timezone(v_set_value_market_day_timezone, now())::date
            )

    ),
    latest_priced_cards AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            cvl.pokemon_canonical_card_id,
            csf.is_hit_eligible,
            latest_price.market_price,
            latest_price.captured_at
        FROM set_dates sd
        JOIN (SELECT DISTINCT set_id, pokemon_canonical_card_id FROM canonical_variant_links) linked_cards
          ON linked_cards.set_id = sd.set_id
        JOIN canonical_scope_flags csf
          ON csf.set_id = linked_cards.set_id
         AND csf.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        JOIN LATERAL (
            SELECT o.market_price, o.captured_at
            FROM canonical_variant_links cvl_inner
            JOIN public.card_variant_price_observations o ON o.card_variant_id = cvl_inner.card_variant_id
              AND o.source = 'TCGPlayer'
            WHERE cvl_inner.set_id = linked_cards.set_id
              AND cvl_inner.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL
              AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at <= sd.snapshot_date
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) latest_price ON true
        JOIN canonical_variant_links cvl
          ON cvl.set_id = linked_cards.set_id
         AND cvl.pokemon_canonical_card_id = linked_cards.pokemon_canonical_card_id
        GROUP BY sd.set_id, sd.snapshot_date, cvl.pokemon_canonical_card_id, csf.is_hit_eligible, latest_price.market_price, latest_price.captured_at
    ),
    standard_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'standard'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(cc.canonical_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT lpc.pokemon_canonical_card_id)::numeric / nullif(max(cc.canonical_card_count), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = lpc.set_id
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    hits_aggregated AS (
        SELECT
            lpc.set_id,
            lpc.snapshot_date,
            'hits'::text AS value_scope,
            round(sum(lpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            max(hc.hit_card_count)::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT lpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT lpc.pokemon_canonical_card_id)::numeric / nullif(max(hc.hit_card_count), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:hits:canonical_checklist' AS source
        FROM latest_priced_cards lpc
        JOIN canonical_counts cc ON cc.set_id = lpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = lpc.set_id
        LEFT JOIN hit_counts hc ON hc.set_id = lpc.set_id
        WHERE lpc.is_hit_eligible = true
        GROUP BY lpc.set_id, lpc.snapshot_date
    ),
    ranked_priced_cards AS (
        SELECT lpc.*, row_number() OVER (PARTITION BY lpc.set_id, lpc.snapshot_date ORDER BY lpc.market_price DESC, lpc.pokemon_canonical_card_id) AS price_rank
        FROM latest_priced_cards lpc
    ),
    top10_aggregated AS (
        SELECT
            rpc.set_id,
            rpc.snapshot_date,
            'top10'::text AS value_scope,
            round(sum(rpc.market_price)::numeric, 2) AS set_value,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS priced_card_count,
            least(10, max(cc.canonical_card_count))::integer AS total_card_count,
            max(cc.canonical_card_count)::integer AS canonical_card_count,
            coalesce(max(lc.linked_card_count), 0)::integer AS linked_card_count,
            count(DISTINCT rpc.pokemon_canonical_card_id)::integer AS included_card_count,
            round((count(DISTINCT rpc.pokemon_canonical_card_id)::numeric / nullif(least(10, max(cc.canonical_card_count)), 0)) * 100, 2) AS coverage_pct,
            'card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist' AS source
        FROM ranked_priced_cards rpc
        JOIN canonical_counts cc ON cc.set_id = rpc.set_id
        LEFT JOIN linked_counts lc ON lc.set_id = rpc.set_id
        WHERE rpc.price_rank <= 10
        GROUP BY rpc.set_id, rpc.snapshot_date
    ),
    aggregated AS (
        SELECT * FROM standard_aggregated
        UNION ALL SELECT * FROM hits_aggregated
        UNION ALL SELECT * FROM top10_aggregated
    ),
    scope_candidates AS (
        SELECT sd.set_id, sd.snapshot_date, scope.value_scope
        FROM set_dates sd
        CROSS JOIN (VALUES ('standard'::text), ('hits'::text), ('top10'::text)) AS scope(value_scope)
    ),
    stale_deleted AS (
        DELETE FROM public.pokemon_set_value_daily_history h
        USING scope_candidates sc
        WHERE h.set_id = sc.set_id
          AND h.snapshot_date = sc.snapshot_date
          AND h.value_scope = sc.value_scope
          AND NOT EXISTS (
              SELECT 1
              FROM aggregated a
              WHERE a.set_id = h.set_id
                AND a.snapshot_date = h.snapshot_date
                AND a.value_scope = h.value_scope
          )
        RETURNING 1
    ),
    upserted AS (
        INSERT INTO public.pokemon_set_value_daily_history (
            set_id, snapshot_date, value_scope, set_value, priced_card_count, total_card_count,
            canonical_card_count, linked_card_count, included_card_count, coverage_pct, source
        )
        SELECT
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            coalesce(total_card_count, 0),
            coalesce(canonical_card_count, total_card_count, 0),
            coalesce(linked_card_count, 0),
            coalesce(included_card_count, priced_card_count, 0),
            coverage_pct,
            source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            canonical_card_count = EXCLUDED.canonical_card_count,
            linked_card_count = EXCLUDED.linked_card_count,
            included_card_count = EXCLUDED.included_card_count,
            coverage_pct = EXCLUDED.coverage_pct,
            source = EXCLUDED.source,
            updated_at = timezone('utc', now())
        RETURNING 1
    )
    SELECT count(*) INTO v_rows_upserted FROM upserted;

    RETURN coalesce(v_rows_upserted, 0);
END;
$function$;

commit;
