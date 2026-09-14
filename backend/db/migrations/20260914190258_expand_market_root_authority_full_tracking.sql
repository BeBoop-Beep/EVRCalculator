-- Expand current Pokemon Market membership from the frozen Sep-10 incident cohort
-- to every released, daily-scraped, non-catalog root set. Historical Sep-10..13
-- membership remains unchanged because the added roots activate on Sep-14.

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
    (SELECT encode(digest(replace(json_agg(e.set_id::text ORDER BY e.set_id::text)::text, ', ', ','), 'sha256'),'hex') FROM eligible e)
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

COMMENT ON FUNCTION public.sync_pokemon_market_root_authority_v1(date) IS
'Insert-only current-day Market root authority sync. Membership is structural: released + ready_for_daily_scrape + non-catalog + parent/root. Never removes roots because certification/freshness fails.';

DO $$
DECLARE
  v_hist_count integer;
  v_hist_fp text;
  v_structural_count integer;
  v_structural_fp text;
  v_current_count integer;
  v_current_fp text;
BEGIN
  SELECT count(*),
         encode(digest(replace(json_agg(a.set_id::text ORDER BY a.set_id::text)::text, ', ', ','), 'sha256'),'hex')
    INTO v_hist_count, v_hist_fp
  FROM (
    SELECT DISTINCT a.set_id
    FROM public.pokemon_market_root_authority a
    WHERE a.enabled
      AND a.activated_market_date <= DATE '2026-09-13'
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date > DATE '2026-09-13')
  ) a;

  IF v_hist_count <> 106 OR v_hist_fp <> '470c8e49e083ca29c7df4d075175b62fb5dd69311b67ca48fec6baf76cd6e892' THEN
    RAISE EXCEPTION 'Sep-13 historical Market authority changed unexpectedly: count=%, fingerprint=%',
      v_hist_count, v_hist_fp;
  END IF;

  SELECT count(*),
         encode(digest(replace(json_agg(s.id::text ORDER BY s.id::text)::text, ', ', ','), 'sha256'),'hex')
    INTO v_structural_count, v_structural_fp
  FROM public.sets s
  WHERE coalesce(s.catalog_only, false) = false
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.ready_for_daily_scrape, false) = true
    AND (s.release_date IS NULL OR s.release_date <= DATE '2026-09-14');

  IF v_structural_count <> 155 OR v_structural_fp <> 'f61c619e1f346924b55eb288cffaff6c3802e1c2519cb42426e10b1d8e3b24eb' THEN
    RAISE EXCEPTION 'Sep-14 structural Market root source mismatch: count=%, fingerprint=%',
      v_structural_count, v_structural_fp;
  END IF;

  INSERT INTO public.pokemon_market_root_authority(
    set_id, activated_market_date, enabled, source, notes
  )
  SELECT s.id, DATE '2026-09-14', true,
         'structural_market_root_expansion_20260914',
         'Full tracked-root expansion: released + ready_for_daily_scrape + non-catalog + parent/root. Preserves Sep-10..13 106-root history.'
  FROM public.sets s
  WHERE coalesce(s.catalog_only, false) = false
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.ready_for_daily_scrape, false) = true
    AND (s.release_date IS NULL OR s.release_date <= DATE '2026-09-14')
    AND NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_root_authority a
      WHERE a.set_id = s.id
        AND a.enabled
        AND a.activated_market_date <= DATE '2026-09-14'
        AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date > DATE '2026-09-14')
    )
  ON CONFLICT (set_id, activated_market_date) DO NOTHING;

  SELECT count(*),
         encode(digest(replace(json_agg(a.set_id::text ORDER BY a.set_id::text)::text, ', ', ','), 'sha256'),'hex')
    INTO v_current_count, v_current_fp
  FROM (
    SELECT DISTINCT a.set_id
    FROM public.pokemon_market_root_authority a
    WHERE a.enabled
      AND a.activated_market_date <= DATE '2026-09-14'
      AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date > DATE '2026-09-14')
  ) a;

  IF v_current_count <> 155 OR v_current_fp <> 'f61c619e1f346924b55eb288cffaff6c3802e1c2519cb42426e10b1d8e3b24eb' THEN
    RAISE EXCEPTION 'Sep-14 expanded Market authority mismatch: count=%, fingerprint=%',
      v_current_count, v_current_fp;
  END IF;
END
$$;
