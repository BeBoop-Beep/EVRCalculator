BEGIN;

-- Sep 10+ Market membership is owned exclusively by pokemon_market_root_authority.
-- The optimized materializers introduced on Sep 13 still joined the legacy
-- era-rollout table, so newly admitted canonical roots could keep generic
-- root-only Set Value rows even while the V2 root authority already held the
-- correct composite value. Keep every other part of the proven materializer
-- unchanged and replace only that stale membership source.
DO $migration$
DECLARE
  v_prepare text;
  v_refresh text;
  v_old_prepare text := $old_prepare$  FROM public.sets s
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
    AND prices.market_scope = 'standard';$old_prepare$;
  v_new_prepare text := $new_prepare$  FROM public.pokemon_market_root_authority authority
  JOIN public.sets s ON s.id = authority.set_id
  CROSS JOIN LATERAL public.get_pokemon_market_root_set_card_prices_latest_v1(s.id) prices
  WHERE authority.enabled
    AND authority.activated_market_date <= p_market_date
    AND (authority.deactivated_market_date IS NULL
         OR authority.deactivated_market_date > p_market_date)
    AND prices.root_set_id = s.id
    AND prices.market_scope = 'standard';$new_prepare$;
  v_old_refresh text := $old_refresh$  FROM public.sets s
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
    AND prices.market_scope = 'standard';$old_refresh$;
  v_new_refresh text := $new_refresh$  FROM public.pokemon_market_root_authority authority
  JOIN public.sets s ON s.id = authority.set_id
  CROSS JOIN LATERAL public.get_pokemon_market_root_set_card_prices_latest_v1(s.id) prices
  WHERE authority.enabled
    AND authority.activated_market_date <= v_market_date
    AND (authority.deactivated_market_date IS NULL
         OR authority.deactivated_market_date > v_market_date)
    AND prices.root_set_id = s.id
    AND prices.market_scope = 'standard';$new_refresh$;
BEGIN
  v_prepare := pg_get_functiondef(
    'public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)'::regprocedure
  );
  IF md5(v_prepare) <> '7a091192a64ae902a8490e42753ad4ec' THEN
    RAISE EXCEPTION 'Concurrent change detected: prepare rollout materializer changed; revalidate before migration';
  END IF;
  IF position(v_old_prepare IN v_prepare) = 0 THEN
    RAISE EXCEPTION 'Expected legacy prepare membership fragment not found';
  END IF;
  v_prepare := replace(v_prepare, v_old_prepare, v_new_prepare);
  IF position('pokemon_market_public_era_rollout_v1' IN v_prepare) <> 0
     OR position('pokemon_market_root_authority' IN v_prepare) = 0 THEN
    RAISE EXCEPTION 'Prepare membership replacement failed closed';
  END IF;
  EXECUTE v_prepare;

  v_refresh := pg_get_functiondef(
    'public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date)'::regprocedure
  );
  IF md5(v_refresh) <> '5b6191e3b4ef0127059136bcd04a6488' THEN
    RAISE EXCEPTION 'Concurrent change detected: public rollout materializer changed; revalidate before migration';
  END IF;
  IF position(v_old_refresh IN v_refresh) = 0 THEN
    RAISE EXCEPTION 'Expected legacy refresh membership fragment not found';
  END IF;
  v_refresh := replace(v_refresh, v_old_refresh, v_new_refresh);
  IF position('pokemon_market_public_era_rollout_v1' IN v_refresh) <> 0
     OR position('pokemon_market_root_authority' IN v_refresh) = 0 THEN
    RAISE EXCEPTION 'Refresh membership replacement failed closed';
  END IF;
  EXECUTE v_refresh;
END;
$migration$;

REVOKE ALL ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)
  TO service_role;

REVOKE ALL ON FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date)
  TO service_role;

COMMENT ON FUNCTION public.prepare_pokemon_market_candidate_rollout_set_values_v1(date) IS
'Pre-gate materialization of Standard and Top-10 Set Value rows for the exact active pokemon_market_root_authority cohort on the latest healthy Pokemon scrape candidate date. Does not publish Top Chase or change Market Date Quality.';

COMMENT ON FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date) IS
'Publishes Standard, Top-10, and Top Chase history for the exact active pokemon_market_root_authority cohort using a single explicit-root price materialization.';

COMMIT;
