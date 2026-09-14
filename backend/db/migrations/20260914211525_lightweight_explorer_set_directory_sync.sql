CREATE OR REPLACE FUNCTION public.sync_pokemon_market_explorer_set_directory_v1()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  v_payload jsonb;
  v_market_date date;
  v_snapshot_set_count integer;
  v_payload_set_count integer;
  v_existing_min_comparison date;
  v_existing_max_comparison date;
  v_generation_id uuid;
  v_generated_at timestamptz;
  v_upserted integer := 0;
  v_directory_set_count integer := 0;
BEGIN
  SELECT s.payload_json, s.market_date, s.set_count
    INTO v_payload, v_market_date, v_snapshot_set_count
  FROM public.pokemon_explore_set_value_snapshot_latest s
  WHERE s.tcg = 'pokemon' AND s.scope = 'market'
  LIMIT 1;

  IF v_payload IS NULL OR v_market_date IS NULL OR coalesce(v_snapshot_set_count, 0) < 1 THEN
    RAISE EXCEPTION 'Global Set Market snapshot unavailable for Explorer Set-directory sync';
  END IF;

  v_payload_set_count := jsonb_array_length(coalesce(v_payload->'sets', '[]'::jsonb));
  IF v_payload_set_count <> v_snapshot_set_count THEN
    RAISE EXCEPTION 'Global Set Market snapshot count mismatch: payload=% row=%',
      v_payload_set_count, v_snapshot_set_count;
  END IF;

  SELECT min(d.comparison_as_of), max(d.comparison_as_of)
    INTO v_existing_min_comparison, v_existing_max_comparison
  FROM public.pokemon_market_explorer_prepared_directory_v1 d;

  IF v_existing_min_comparison IS NULL OR v_existing_max_comparison IS NULL
     OR v_existing_min_comparison IS DISTINCT FROM v_existing_max_comparison THEN
    RAISE EXCEPTION 'Prepared Explorer directory has no single comparison watermark';
  END IF;

  SELECT d.generation_id, d.generated_at
    INTO v_generation_id, v_generated_at
  FROM public.pokemon_market_explorer_prepared_directory_v1 d
  ORDER BY d.generated_at DESC, d.market_key
  LIMIT 1;

  v_generation_id := coalesce(v_generation_id, extensions.gen_random_uuid());
  v_generated_at := coalesce(v_generated_at, clock_timestamp());

  INSERT INTO public.pokemon_market_explorer_prepared_directory_v1 (
    market_key, market_type, label, asset, set_id, era_id, parent_era_id,
    prepared_series_key, comparison_as_of, source_as_of, current_value,
    screen_group, screen_eligible, source_kind, source_status, metadata,
    generation_id, generated_at
  )
  SELECT
    'set:' || (e->>'setId'),
    'set',
    e->>'name',
    'cards',
    (e->>'setId')::uuid,
    NULL::uuid,
    s.era_id,
    'set-cards-market-index:' || (e->>'setId'),
    v_existing_min_comparison,
    nullif(e->>'setValueAsOf', '')::date,
    nullif(e->>'currentSetValue', '')::numeric,
    NULL,
    false,
    'public_set_snapshot',
    e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey', e->>'canonicalKey',
      'eraName', er.name,
      'logoUrl', e->>'logoUrl',
      'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus'
    )),
    v_generation_id,
    v_generated_at
  FROM jsonb_array_elements(v_payload->'sets') e
  JOIN public.sets s ON s.id = (e->>'setId')::uuid
  LEFT JOIN public.eras er ON er.id = s.era_id
  ON CONFLICT (market_key) DO UPDATE
  SET label = EXCLUDED.label,
      asset = EXCLUDED.asset,
      set_id = EXCLUDED.set_id,
      era_id = EXCLUDED.era_id,
      parent_era_id = EXCLUDED.parent_era_id,
      prepared_series_key = EXCLUDED.prepared_series_key,
      source_as_of = EXCLUDED.source_as_of,
      current_value = EXCLUDED.current_value,
      source_kind = EXCLUDED.source_kind,
      source_status = EXCLUDED.source_status,
      metadata = EXCLUDED.metadata;
  GET DIAGNOSTICS v_upserted = ROW_COUNT;

  SELECT count(*)::integer
    INTO v_directory_set_count
  FROM public.pokemon_market_explorer_prepared_directory_v1 d
  WHERE d.market_type = 'set';

  IF v_directory_set_count <> v_snapshot_set_count THEN
    RAISE EXCEPTION 'Prepared Explorer Set-directory count mismatch after sync: directory=% snapshot=%',
      v_directory_set_count, v_snapshot_set_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_prepared_directory_v1 s
    WHERE s.market_type = 'set'
      AND (
        s.parent_era_id IS NULL
        OR NOT EXISTS (
          SELECT 1
          FROM public.pokemon_market_explorer_prepared_directory_v1 e
          WHERE e.market_type = 'era' AND e.era_id = s.parent_era_id
        )
      )
  ) THEN
    RAISE EXCEPTION 'Prepared Explorer Set directory contains a Set without its parent Era';
  END IF;

  RETURN jsonb_build_object(
    'status', 'complete',
    'marketDate', v_market_date,
    'snapshotSetCount', v_snapshot_set_count,
    'directorySetCount', v_directory_set_count,
    'rowsUpserted', v_upserted,
    'comparisonAsOf', v_existing_min_comparison
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.sync_pokemon_market_explorer_set_directory_v1()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sync_pokemon_market_explorer_set_directory_v1()
  TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_market_explorer_directory_after_set_market_v1()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
  IF TG_OP = 'UPDATE'
     AND OLD.market_date IS NOT DISTINCT FROM NEW.market_date
     AND OLD.set_count IS NOT DISTINCT FROM NEW.set_count
     AND OLD.source_generation_fingerprint IS NOT DISTINCT FROM NEW.source_generation_fingerprint
     AND OLD.payload_json IS NOT DISTINCT FROM NEW.payload_json THEN
    RETURN NEW;
  END IF;

  PERFORM public.sync_pokemon_market_explorer_set_directory_v1();
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_market_explorer_directory_after_set_market_v1()
  FROM PUBLIC, anon, authenticated, service_role;

COMMENT ON FUNCTION public.sync_pokemon_market_explorer_set_directory_v1() IS
'Lightweight Set-directory synchronizer. Mirrors Global Set Market membership/current values into the prepared Explorer directory while preserving the existing common comparison generation/history; full analytical-history refresh remains a separate maintenance operation.';

COMMENT ON FUNCTION public.refresh_market_explorer_directory_after_set_market_v1() IS
'Keeps prepared Explorer Set discovery synchronized transactionally with changed Global Set Market snapshots using the lightweight Set-directory sync, avoiding the heavy full Phase-5 history rebuild in the publication transaction.';
