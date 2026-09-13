BEGIN;

-- Keep the existing RPC contracts, but avoid the global root-price views. Each
-- RPC resolves the eligible rollout roots structurally and evaluates the
-- explicit-root price function once per root into a transaction-local table.
CREATE OR REPLACE FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(
  p_market_date date
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $function$
DECLARE
  v_candidate_date date;
  v_standard_rows integer := 0;
  v_top10_rows integer := 0;
BEGIN
  WITH approved_date AS (
    SELECT max(q.market_date)::date AS market_date
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg = 'pokemon'
      AND q.status IN ('READY','LEGACY_VERIFIED')
  ), healthy_scrape_date AS (
    SELECT max(b.market_date)::date AS market_date
    FROM public.pokemon_scrape_batches b
    WHERE b.status = 'complete'
      AND b.promoted_at IS NOT NULL
      AND coalesce(b.expected_set_count, 0) > 0
      AND coalesce(b.failed_set_count, 0) = 0
      AND coalesce(b.missing_set_count, 0) = 0
      AND b.succeeded_set_count = b.expected_set_count
  )
  SELECT CASE
           WHEN s.market_date IS NULL THEN a.market_date
           WHEN a.market_date IS NULL THEN s.market_date
           ELSE greatest(s.market_date, a.market_date)
         END
    INTO v_candidate_date
  FROM approved_date a
  CROSS JOIN healthy_scrape_date s;

  IF p_market_date IS NULL OR v_candidate_date IS NULL THEN
    RAISE EXCEPTION 'Pokemon Market candidate date is unavailable';
  END IF;
  IF p_market_date IS DISTINCT FROM v_candidate_date THEN
    RAISE EXCEPTION 'Candidate rollout Set Value preparation is current-date only: requested %, candidate %',
      p_market_date, v_candidate_date;
  END IF;

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_prices_work_v1 (
    root_set_id uuid,
    root_set_name text,
    member_set_id uuid,
    member_set_name text,
    member_type text,
    market_scope text,
    canonical_card_id uuid,
    card_name text,
    card_number text,
    rarity text,
    canonical_review_status text,
    card_variant_id uuid,
    edition text,
    printing_type text,
    special_type text,
    identity_basis text,
    market_price numeric,
    captured_at date,
    source text,
    price_selection_reason text
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_prices_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_prices_work_v1
  SELECT prices.*
  FROM public.sets s
  JOIN public.pokemon_market_public_era_rollout_v1 rollout
    ON rollout.era_id = s.era_id
   AND rollout.enabled
   AND rollout.activated_market_date <= p_market_date
  CROSS JOIN LATERAL public.get_pokemon_market_root_set_card_prices_latest_v1(s.id) prices
  WHERE s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only, false) = false
    AND coalesce(s.ready_for_daily_scrape, false) = true
    AND (s.release_date IS NULL OR s.release_date <= p_market_date)
    AND prices.root_set_id = s.id
    AND prices.market_scope = 'standard';

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_values_work_v1 (
    set_id uuid PRIMARY KEY,
    set_value numeric,
    expected_card_count integer,
    resolved_variant_count integer,
    priced_card_count integer,
    coverage_pct numeric,
    publishable_100pct boolean
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_values_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_values_work_v1
  SELECT p.root_set_id,
         round(coalesce(sum(p.market_price), 0::numeric), 2),
         count(*)::integer,
         count(p.card_variant_id)::integer,
         count(p.market_price)::integer,
         round(count(p.market_price)::numeric / nullif(count(*), 0)::numeric * 100, 2),
         (count(*) > 0
          AND count(*) FILTER (WHERE p.canonical_review_status = 'needs_review') = 0
          AND count(p.card_variant_id) = count(*)
          AND count(p.market_price) = count(*))
  FROM pg_temp.pokemon_market_rollout_prices_work_v1 p
  GROUP BY p.root_set_id;

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_ranked_work_v1 (
    root_set_id uuid,
    canonical_card_id uuid,
    card_variant_id uuid,
    card_name text,
    rarity text,
    market_price numeric,
    captured_at date,
    source text,
    rank integer,
    publishable_100pct boolean
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_ranked_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_ranked_work_v1
  SELECT p.root_set_id,
         p.canonical_card_id,
         p.card_variant_id,
         p.card_name,
         p.rarity,
         p.market_price,
         p.captured_at,
         p.source,
         row_number() OVER (
           PARTITION BY p.root_set_id
           ORDER BY p.market_price DESC NULLS LAST, p.canonical_card_id
         )::integer,
         v.publishable_100pct
  FROM pg_temp.pokemon_market_rollout_prices_work_v1 p
  JOIN pg_temp.pokemon_market_rollout_values_work_v1 v ON v.set_id = p.root_set_id
  WHERE p.market_price IS NOT NULL;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT v.set_id, p_market_date, 'standard', v.set_value,
         v.priced_card_count, v.expected_card_count,
         'canonical_root_set_public_rollout_candidate_v1',
         v.expected_card_count, v.expected_card_count, v.priced_card_count,
         v.coverage_pct, now(), now()
  FROM pg_temp.pokemon_market_rollout_values_work_v1 v
  WHERE coalesce(v.coverage_pct, 0) >= 95
  ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
  SET set_value = EXCLUDED.set_value,
      priced_card_count = EXCLUDED.priced_card_count,
      total_card_count = EXCLUDED.total_card_count,
      source = EXCLUDED.source,
      canonical_card_count = EXCLUDED.canonical_card_count,
      linked_card_count = EXCLUDED.linked_card_count,
      included_card_count = EXCLUDED.included_card_count,
      coverage_pct = EXCLUDED.coverage_pct,
      updated_at = now();
  GET DIAGNOSTICS v_standard_rows = ROW_COUNT;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT r.root_set_id, p_market_date, 'top10', sum(r.market_price)::numeric,
         count(*)::integer, 10,
         'canonical_root_top10_public_rollout_candidate_v1',
         10, 10, count(*)::integer, 100.00, now(), now()
  FROM pg_temp.pokemon_market_rollout_ranked_work_v1 r
  WHERE r.publishable_100pct
    AND r.rank BETWEEN 1 AND 10
  GROUP BY r.root_set_id
  HAVING count(*) = 10
  ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
  SET set_value = EXCLUDED.set_value,
      priced_card_count = EXCLUDED.priced_card_count,
      total_card_count = EXCLUDED.total_card_count,
      source = EXCLUDED.source,
      canonical_card_count = EXCLUDED.canonical_card_count,
      linked_card_count = EXCLUDED.linked_card_count,
      included_card_count = EXCLUDED.included_card_count,
      coverage_pct = EXCLUDED.coverage_pct,
      updated_at = now();
  GET DIAGNOSTICS v_top10_rows = ROW_COUNT;

  RETURN jsonb_build_object(
    'status', 'complete',
    'marketDate', p_market_date,
    'candidateDate', v_candidate_date,
    'rolloutRootCount', (
      SELECT count(*)
      FROM pg_temp.pokemon_market_rollout_values_work_v1 v
      WHERE coalesce(v.coverage_pct, 0) >= 95
    ),
    'standardRowsUpserted', v_standard_rows,
    'top10RowsUpserted', v_top10_rows
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)
  TO service_role;

COMMENT ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date) IS
'Pre-gate materialization of Standard and Top-10 Set Value rows for public rollout roots on the latest healthy Pokemon scrape candidate date. Does not publish Top Chase or change Market Date Quality.';

CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(
  p_market_date date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $function$
DECLARE
  v_market_date date;
  v_latest_approved date;
  v_standard_rows integer := 0;
  v_top10_value_rows integer := 0;
  v_top10_deleted integer := 0;
  v_top10_rows integer := 0;
BEGIN
  SELECT max(q.market_date)::date
    INTO v_latest_approved
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
    AND q.status IN ('READY','LEGACY_VERIFIED');

  v_market_date := coalesce(p_market_date, v_latest_approved);
  IF v_market_date IS NULL THEN
    RAISE EXCEPTION 'No approved Pokemon market date exists';
  END IF;
  IF v_market_date IS DISTINCT FROM v_latest_approved THEN
    RAISE EXCEPTION 'Public rollout snapshot refresh is current-date only: requested %, latest approved %',
      v_market_date, v_latest_approved;
  END IF;

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_prices_work_v1 (
    root_set_id uuid,
    root_set_name text,
    member_set_id uuid,
    member_set_name text,
    member_type text,
    market_scope text,
    canonical_card_id uuid,
    card_name text,
    card_number text,
    rarity text,
    canonical_review_status text,
    card_variant_id uuid,
    edition text,
    printing_type text,
    special_type text,
    identity_basis text,
    market_price numeric,
    captured_at date,
    source text,
    price_selection_reason text
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_prices_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_prices_work_v1
  SELECT prices.*
  FROM public.sets s
  JOIN public.pokemon_market_public_era_rollout_v1 rollout
    ON rollout.era_id = s.era_id
   AND rollout.enabled
   AND rollout.activated_market_date <= v_market_date
  CROSS JOIN LATERAL public.get_pokemon_market_root_set_card_prices_latest_v1(s.id) prices
  WHERE s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only, false) = false
    AND coalesce(s.ready_for_daily_scrape, false) = true
    AND (s.release_date IS NULL OR s.release_date <= v_market_date)
    AND prices.root_set_id = s.id
    AND prices.market_scope = 'standard';

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_values_work_v1 (
    set_id uuid PRIMARY KEY,
    set_value numeric,
    expected_card_count integer,
    resolved_variant_count integer,
    priced_card_count integer,
    coverage_pct numeric,
    publishable_100pct boolean
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_values_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_values_work_v1
  SELECT p.root_set_id,
         round(coalesce(sum(p.market_price), 0::numeric), 2),
         count(*)::integer,
         count(p.card_variant_id)::integer,
         count(p.market_price)::integer,
         round(count(p.market_price)::numeric / nullif(count(*), 0)::numeric * 100, 2),
         (count(*) > 0
          AND count(*) FILTER (WHERE p.canonical_review_status = 'needs_review') = 0
          AND count(p.card_variant_id) = count(*)
          AND count(p.market_price) = count(*))
  FROM pg_temp.pokemon_market_rollout_prices_work_v1 p
  GROUP BY p.root_set_id;

  CREATE TEMP TABLE IF NOT EXISTS pokemon_market_rollout_ranked_work_v1 (
    root_set_id uuid,
    canonical_card_id uuid,
    card_variant_id uuid,
    card_name text,
    rarity text,
    market_price numeric,
    captured_at date,
    source text,
    rank integer,
    publishable_100pct boolean
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.pokemon_market_rollout_ranked_work_v1;

  INSERT INTO pg_temp.pokemon_market_rollout_ranked_work_v1
  SELECT p.root_set_id,
         p.canonical_card_id,
         p.card_variant_id,
         p.card_name,
         p.rarity,
         p.market_price,
         p.captured_at,
         p.source,
         row_number() OVER (
           PARTITION BY p.root_set_id
           ORDER BY p.market_price DESC NULLS LAST, p.canonical_card_id
         )::integer,
         v.publishable_100pct
  FROM pg_temp.pokemon_market_rollout_prices_work_v1 p
  JOIN pg_temp.pokemon_market_rollout_values_work_v1 v ON v.set_id = p.root_set_id
  WHERE p.market_price IS NOT NULL;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT v.set_id, v_market_date, 'standard', v.set_value,
         v.priced_card_count, v.expected_card_count,
         'canonical_root_set_public_rollout_v1',
         v.expected_card_count, v.expected_card_count, v.priced_card_count,
         v.coverage_pct, now(), now()
  FROM pg_temp.pokemon_market_rollout_values_work_v1 v
  WHERE coalesce(v.coverage_pct, 0) >= 95
  ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
  SET set_value = EXCLUDED.set_value,
      priced_card_count = EXCLUDED.priced_card_count,
      total_card_count = EXCLUDED.total_card_count,
      source = EXCLUDED.source,
      canonical_card_count = EXCLUDED.canonical_card_count,
      linked_card_count = EXCLUDED.linked_card_count,
      included_card_count = EXCLUDED.included_card_count,
      coverage_pct = EXCLUDED.coverage_pct,
      updated_at = now();
  GET DIAGNOSTICS v_standard_rows = ROW_COUNT;

  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT r.root_set_id, v_market_date, 'top10', sum(r.market_price)::numeric,
         count(*)::integer, 10, 'canonical_root_top10_public_rollout_v1',
         10, 10, count(*)::integer, 100.00, now(), now()
  FROM pg_temp.pokemon_market_rollout_ranked_work_v1 r
  WHERE r.publishable_100pct
    AND r.rank BETWEEN 1 AND 10
  GROUP BY r.root_set_id
  HAVING count(*) = 10
  ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
  SET set_value = EXCLUDED.set_value,
      priced_card_count = EXCLUDED.priced_card_count,
      total_card_count = EXCLUDED.total_card_count,
      source = EXCLUDED.source,
      canonical_card_count = EXCLUDED.canonical_card_count,
      linked_card_count = EXCLUDED.linked_card_count,
      included_card_count = EXCLUDED.included_card_count,
      coverage_pct = EXCLUDED.coverage_pct,
      updated_at = now();
  GET DIAGNOSTICS v_top10_value_rows = ROW_COUNT;

  DELETE FROM public.pokemon_set_top_chase_card_daily_history h
  WHERE h.snapshot_date = v_market_date
    AND h.set_id IN (
      SELECT v.set_id
      FROM pg_temp.pokemon_market_rollout_values_work_v1 v
      WHERE coalesce(v.coverage_pct, 0) >= 95
    );
  GET DIAGNOSTICS v_top10_deleted = ROW_COUNT;

  INSERT INTO public.pokemon_set_top_chase_card_daily_history(
    set_id, snapshot_date, card_id, card_variant_id, rank,
    name, rarity, image_url, image_small_url, image_large_url,
    market_price, source, source_date, created_at, updated_at
  )
  SELECT r.root_set_id,
         v_market_date,
         r.canonical_card_id,
         r.card_variant_id,
         r.rank,
         r.card_name,
         r.rarity,
         coalesce(pcc.image_small_url, pcc.image_large_url),
         pcc.image_small_url,
         pcc.image_large_url,
         r.market_price,
         r.source,
         r.captured_at,
         now(), now()
  FROM pg_temp.pokemon_market_rollout_ranked_work_v1 r
  JOIN public.pokemon_canonical_cards pcc ON pcc.id = r.canonical_card_id
  WHERE r.publishable_100pct
    AND r.rank BETWEEN 1 AND 10
  ON CONFLICT (set_id, snapshot_date, rank) DO UPDATE
  SET card_id = EXCLUDED.card_id,
      card_variant_id = EXCLUDED.card_variant_id,
      name = EXCLUDED.name,
      rarity = EXCLUDED.rarity,
      image_url = EXCLUDED.image_url,
      image_small_url = EXCLUDED.image_small_url,
      image_large_url = EXCLUDED.image_large_url,
      market_price = EXCLUDED.market_price,
      source = EXCLUDED.source,
      source_date = EXCLUDED.source_date,
      updated_at = now();
  GET DIAGNOSTICS v_top10_rows = ROW_COUNT;

  RETURN jsonb_build_object(
    'marketDate', v_market_date,
    'rolloutRootCount', (
      SELECT count(*)
      FROM pg_temp.pokemon_market_rollout_values_work_v1 v
      WHERE coalesce(v.coverage_pct, 0) >= 95
    ),
    'standardRowsUpserted', v_standard_rows,
    'top10ValueRowsUpserted', v_top10_value_rows,
    'top10RowsDeleted', v_top10_deleted,
    'top10RowsInserted', v_top10_rows
  );
END;
$function$;

-- CREATE OR REPLACE preserves the finalizer's existing ACL. The historical
-- function was granted to service_role without revoking PUBLIC; changing that
-- boundary is intentionally outside this performance-only migration.
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date)
  TO service_role;

COMMENT ON FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date) IS
'Publishes approved rollout-root Standard, Top-10, and Top Chase history using a single explicit-root price materialization.';

COMMIT;
