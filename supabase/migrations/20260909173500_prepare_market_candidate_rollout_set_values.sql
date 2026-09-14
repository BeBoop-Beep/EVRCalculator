BEGIN;

-- Materialize only the Set Value inputs needed by Market Date Quality for the
-- newest healthy scrape candidate. Full public rollout publication (including
-- Top Chase history) remains behind the approved Market Date Quality gate.
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

  WITH roots AS MATERIALIZED (
    SELECT r.set_id
    FROM public.pokemon_market_public_rollout_root_sets_v1 r
    WHERE r.activated_market_date <= p_market_date
      AND (r.release_date IS NULL OR r.release_date <= p_market_date)
  ), canonical AS MATERIALIZED (
    SELECT v.set_id,
           v.set_value,
           v.expected_card_count,
           v.priced_card_count,
           v.coverage_pct
    FROM public.pokemon_market_root_set_value_latest_v1 v
    JOIN roots r ON r.set_id = v.set_id
    WHERE v.market_scope = 'standard'
      AND coalesce(v.coverage_pct, 0) >= 95
  )
  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT c.set_id, p_market_date, 'standard', c.set_value,
         c.priced_card_count, c.expected_card_count,
         'canonical_root_set_public_rollout_candidate_v1',
         c.expected_card_count, c.expected_card_count, c.priced_card_count,
         c.coverage_pct, now(), now()
  FROM canonical c
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

  WITH roots AS MATERIALIZED (
    SELECT r.set_id
    FROM public.pokemon_market_public_rollout_root_sets_v1 r
    WHERE r.activated_market_date <= p_market_date
      AND (r.release_date IS NULL OR r.release_date <= p_market_date)
  ), grouped AS MATERIALIZED (
    SELECT t.set_id,
           sum(t.market_price)::numeric AS set_value,
           count(*)::integer AS card_count
    FROM public.pokemon_market_root_set_top10_latest_v1 t
    JOIN roots r ON r.set_id = t.set_id
    WHERE t.market_scope = 'standard'
      AND t.publishable_100pct
      AND t.rank BETWEEN 1 AND 10
    GROUP BY t.set_id
    HAVING count(*) = 10
  )
  INSERT INTO public.pokemon_set_value_daily_history(
    set_id, snapshot_date, value_scope, set_value,
    priced_card_count, total_card_count, source,
    canonical_card_count, linked_card_count, included_card_count,
    coverage_pct, created_at, updated_at
  )
  SELECT g.set_id, p_market_date, 'top10', g.set_value,
         g.card_count, 10,
         'canonical_root_top10_public_rollout_candidate_v1',
         10, 10, g.card_count, 100.00, now(), now()
  FROM grouped g
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
      FROM public.pokemon_market_public_rollout_root_sets_v1 r
      WHERE r.activated_market_date <= p_market_date
        AND (r.release_date IS NULL OR r.release_date <= p_market_date)
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

COMMIT;
