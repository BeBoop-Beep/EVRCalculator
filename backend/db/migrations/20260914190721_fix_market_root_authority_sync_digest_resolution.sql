-- Qualify pgcrypto because the authority sync intentionally runs with an empty
-- search_path. The initial Sep-14 expansion is already complete; this only
-- repairs the reusable current-day sync function for future publication runs.

CREATE OR REPLACE FUNCTION public.sync_pokemon_market_root_authority_v1(
  p_market_date date
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  v_latest_healthy_date date;
  v_inserted integer := 0;
  v_structural_count integer := 0;
  v_active_count integer := 0;
  v_missing_count integer := 0;
  v_structural_fp text;
BEGIN
  SELECT max(b.market_date)::date
    INTO v_latest_healthy_date
  FROM public.pokemon_scrape_batches b
  WHERE b.status = 'complete'
    AND b.promoted_at IS NOT NULL
    AND coalesce(b.expected_set_count, 0) > 0
    AND coalesce(b.failed_set_count, 0) = 0
    AND coalesce(b.missing_set_count, 0) = 0
    AND b.succeeded_set_count = b.expected_set_count;

  IF p_market_date IS NULL OR v_latest_healthy_date IS NULL THEN
    RAISE EXCEPTION 'Pokemon Market authority sync date is unavailable';
  END IF;
  IF p_market_date IS DISTINCT FROM v_latest_healthy_date THEN
    RAISE EXCEPTION 'Pokemon Market authority sync is current-date only: requested %, latest healthy %',
      p_market_date, v_latest_healthy_date;
  END IF;

  WITH eligible AS (
    SELECT s.id AS set_id
    FROM public.sets s
    WHERE coalesce(s.catalog_only, false) = false
      AND s.parent_opening_set_id IS NULL
      AND coalesce(s.ready_for_daily_scrape, false) = true
      AND (s.release_date IS NULL OR s.release_date <= p_market_date)
  )
  INSERT INTO public.pokemon_market_root_authority(
    set_id, activated_market_date, enabled, source, notes
  )
  SELECT e.set_id, p_market_date, true,
         'structural_market_root_sync_v1',
         'Activated from released, ready_for_daily_scrape, non-catalog parent/root membership. Certification remains annotation only.'
  FROM eligible e
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_root_authority a
    WHERE a.set_id = e.set_id
      AND a.enabled
      AND a.activated_market_date <= p_market_date
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date > p_market_date)
  )
  ON CONFLICT (set_id, activated_market_date) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;

  WITH eligible AS (
    SELECT s.id AS set_id
    FROM public.sets s
    WHERE coalesce(s.catalog_only, false) = false
      AND s.parent_opening_set_id IS NULL
      AND coalesce(s.ready_for_daily_scrape, false) = true
      AND (s.release_date IS NULL OR s.release_date <= p_market_date)
  ), active AS (
    SELECT DISTINCT a.set_id
    FROM public.pokemon_market_root_authority a
    WHERE a.enabled
      AND a.activated_market_date <= p_market_date
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date > p_market_date)
  )
  SELECT
    (SELECT count(*) FROM eligible),
    (SELECT count(*) FROM active),
    (SELECT count(*) FROM eligible e WHERE NOT EXISTS (SELECT 1 FROM active a WHERE a.set_id=e.set_id)),
    (SELECT encode(extensions.digest(replace(json_agg(e.set_id::text ORDER BY e.set_id::text)::text, ', ', ','), 'sha256'),'hex') FROM eligible e)
  INTO v_structural_count, v_active_count, v_missing_count, v_structural_fp;

  IF v_structural_count < 1 THEN
    RAISE EXCEPTION 'Pokemon Market structural root cohort is empty for %', p_market_date;
  END IF;
  IF v_missing_count <> 0 THEN
    RAISE EXCEPTION 'Pokemon Market authority sync left % structural root(s) missing for %',
      v_missing_count, p_market_date;
  END IF;

  RETURN jsonb_build_object(
    'status','complete',
    'marketDate',p_market_date,
    'rowsActivated',v_inserted,
    'structuralRootCount',v_structural_count,
    'activeAuthorityRootCount',v_active_count,
    'missingStructuralRootCount',v_missing_count,
    'structuralFingerprint',v_structural_fp
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.sync_pokemon_market_root_authority_v1(date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sync_pokemon_market_root_authority_v1(date)
  TO service_role;
